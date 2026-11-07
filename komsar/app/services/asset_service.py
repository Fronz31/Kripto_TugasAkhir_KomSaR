"""Manajemen aset penting + verifikasi integritas berbasis blockchain.

Pengguna hanya melihat aset miliknya dan status integritas (tanpa blok mentah).
Blok mentah dapat dilihat lewat `list_blocks()` (admin/pengecekan) atau di penyimpanan blockchain.
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..errors import AccessDeniedError
from ..extensions import db
from ..models.records import FileRecord, KIND_ASSET
from ..models.user import User

STATUS_VERIFIED = "verified"
STATUS_CIPHERTEXT_MODIFIED = "ciphertext_modified"
STATUS_CIPHERTEXT_MISSING = "ciphertext_missing"
STATUS_BLOCK_MISSING = "block_missing"
STATUS_CHAIN_BROKEN = "chain_broken"
STATUS_METADATA_MISMATCH = "metadata_mismatch"


@dataclass
class IntegrityReport:
    ok: bool
    status: str
    message: str


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def identity(user: User) -> dict:
    return {"user_id": user.user_id, "username": user.username, "unit": user.unit}


class AssetService:
    def __init__(self, repo, chain):
        self.repo, self.chain = repo, chain

    # ---- pencatatan --------------------------------------------------------
    def register(self, message, file_rec: FileRecord, sender: User, recipients: list[User]):
        """Buat SATU blok untuk satu aset (daftar penerima di dalam blok)."""
        return self.chain.add_block(
            asset_id=file_rec.id, ciphertext_hash=file_rec.ciphertext_sha256,
            metadata={"original_name": file_rec.original_name, "mime": file_rec.mime,
                      "size": file_rec.plaintext_size, "algo": file_rec.algo, "message_id": message.id},
            sender=identity(sender), recipients=[identity(r) for r in recipients])

    # ---- verifikasi --------------------------------------------------------
    def check_file(self, f: FileRecord) -> IntegrityReport:
        path = Path(f.enc_path)
        if not path.exists():
            return IntegrityReport(False, STATUS_CIPHERTEXT_MISSING, "File ciphertext aset tidak ditemukan.")
        block = self.chain.get_block_by_asset(f.id)
        if block is None:
            return IntegrityReport(False, STATUS_BLOCK_MISSING, "Catatan blockchain untuk aset ini tidak ditemukan.")
        validation = self.chain.validate()
        if not validation.valid:
            return IntegrityReport(False, STATUS_CHAIN_BROKEN,
                                   "Rantai blockchain tidak valid: " + "; ".join(validation.errors[:3]))
        if sha256_file(path) != block.ciphertext_hash:
            return IntegrityReport(False, STATUS_CIPHERTEXT_MODIFIED,
                                   "Ciphertext aset telah berubah (hash tidak cocok dengan catatan blockchain).")
        md = block.metadata
        if (md.get("original_name"), md.get("size"), md.get("algo")) != (f.original_name, f.plaintext_size, f.algo):
            return IntegrityReport(False, STATUS_METADATA_MISMATCH, "Metadata aset tidak sesuai dengan catatan blockchain.")
        return IntegrityReport(True, STATUS_VERIFIED, "Integritas aset terverifikasi.")

    def verify_integrity(self, user: User, asset_id: str) -> IntegrityReport:
        return self.check_file(self._authorized_file(user, asset_id))

    # ---- tampilan untuk pengguna ------------------------------------------
    def list_assets(self, user: User, check_integrity: bool = False) -> list[dict]:
        items = [self._describe(user, f, check_integrity) for f in self.repo.asset_files(user.id)]
        return sorted(items, key=lambda i: i["sent_at"], reverse=True)

    def asset_metadata(self, user: User, asset_id: str) -> dict:
        return self._describe(user, self._authorized_file(user, asset_id), True)

    # ---- untuk admin / pengecekan -----------------------------------------
    def list_blocks(self) -> list[dict]:
        return [b.to_record() for b in self.chain.blocks()]

    # ---- internal ----------------------------------------------------------
    def _authorized_file(self, user: User, asset_id: str) -> FileRecord:
        f = next((x for x in self.repo.asset_files(user.id) if x.id == asset_id), None)
        if f is None:
            raise AccessDeniedError("Aset tidak ditemukan atau Anda tidak berhak mengaksesnya.")
        return f

    def _describe(self, user: User, f: FileRecord, check_integrity: bool) -> dict:
        m = self.repo.get_message(f.message_id)
        sender = db.session.get(User, m.sender_pk)
        recips = [db.session.get(User, pk) for pk in m.recipient_pks]
        info = {
            "asset_id": f.id, "name": f.original_name, "size": f.plaintext_size, "mime": f.mime, "algo": f.algo,
            "sent_at": m.created_at.isoformat(), "role": "sender" if m.sender_pk == user.id else "recipient",
            "sender": {"username": sender.username, "full_name": sender.full_name, "unit": sender.unit},
            "recipients": [{"username": r.username, "full_name": r.full_name, "unit": r.unit} for r in recips],
        }
        if check_integrity:
            rep = self.check_file(f)
            info["integrity"] = {"ok": rep.ok, "status": rep.status, "message": rep.message}
        return info
