"""Pengiriman pesan teks (biasa/penting), file, gambar, dan aset penting ke satu/banyak penerima.

Kunci: satu CEK acak per pengiriman -> isi dienkripsi SEKALI.
Per penerima: CEK dibungkus dengan KDF(kunci_rahasia, ID_penerima, salt) dan kunci_rahasia
disisipkan ke gambar steganografi yang dikunci dengan ID penerima tersebut.
"""
import io
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ..crypto import file_cipher
from ..crypto.db_layer import encrypt_for_db
from ..crypto.kdf import derive_content_keys
from ..crypto.key_wrap import generate_cek, wrap_cek
from ..crypto.text import encrypt_text
from ..errors import FileTooLargeError, UserNotFoundError, ValidationError
from ..extensions import db
from ..models.records import (KIND_ASSET, KIND_FILE, KIND_IMAGE, KIND_IMPORTANT_TEXT, KIND_TEXT,
                              STATUS_DELIVERED, STATUS_SENT, DeliveryRecord, FileRecord,
                              MessageRecord)
from ..models.user import User
from ..stego.cover import pick_random_cover
from ..stego.embed import embed_key
from . import user_service, validators as v

KIND_LABELS = {
    KIND_TEXT: "Pesan Biasa", KIND_IMPORTANT_TEXT: "Pesan Penting",
    KIND_FILE: "File", KIND_IMAGE: "Gambar", KIND_ASSET: "Aset Penting",
}


def _now():
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex


class MessagingService:
    def __init__(self, repo, master_key: bytes, covers_dir, files_dir, stego_dir,
                 max_file_bytes: int, file_algo=file_cipher.ALGO_CHACHA20, asset_algo=file_cipher.ALGO_AESGCM,
                 asset_service=None):
        self.repo, self.master_key = repo, master_key
        self.covers_dir, self.files_dir, self.stego_dir = Path(covers_dir), Path(files_dir), Path(stego_dir)
        self.max_file_bytes, self.file_algo, self.asset_algo = max_file_bytes, file_algo, asset_algo
        self.asset_service = asset_service      # pencatatan blockchain untuk aset penting
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.stego_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_app(cls, app, repo, asset_service=None):
        c = app.config
        return cls(repo, c["DB_MASTER_KEY"], c["COVER_IMAGES_DIR"], c["ENCRYPTED_FILES_DIR"],
                   c["STEGO_IMAGES_DIR"], c["MAX_FILE_BYTES"], c["FILE_ALGO"], c["ASSET_ALGO"], asset_service)

    # ---- pesan teks --------------------------------------------------------
    def send_text(self, sender: User, recipient_usernames, text: str, secret, important: bool = False) -> MessageRecord:
        text = v.validate_text(text)
        secret_b = v.validate_secret(secret)
        recipients = self._resolve_recipients(sender, recipient_usernames)

        cek = generate_cek()
        ciphertext = encrypt_text(text, cek)                       # Vigenère -> AES-GCM
        if important:
            ciphertext = encrypt_for_db(self.master_key, ciphertext)   # lapisan AES tambahan untuk DB

        message = MessageRecord(id=_new_id(), kind=KIND_IMPORTANT_TEXT if important else KIND_TEXT,
                                sender_pk=sender.id, created_at=_now(),
                                recipient_pks=[r.id for r in recipients], ciphertext=ciphertext)
        deliveries = self._build_deliveries(message.id, recipients, secret_b, cek)
        self.repo.add_message(message, deliveries)
        return message

    # ---- file / gambar / aset penting -------------------------------------
    def send_file(self, sender: User, recipient_usernames, filename: str, source, secret,
                  kind: str = KIND_FILE) -> MessageRecord:
        if kind not in (KIND_FILE, KIND_IMAGE, KIND_ASSET):
            raise ValidationError("Jenis kiriman tidak valid.")
        secret_b = v.validate_secret(secret)
        name = v.safe_filename(filename)
        allowed = v.IMAGE_EXT if kind == KIND_IMAGE else (v.DOCUMENT_EXT | v.IMAGE_EXT)
        v.validate_extension(name, allowed)
        data = self._read_source(source)
        if kind == KIND_IMAGE:
            self._validate_image(data)
        recipients = self._resolve_recipients(sender, recipient_usernames)

        message_id, file_id = _new_id(), _new_id()
        cek = generate_cek()
        algo = self.asset_algo if kind == KIND_ASSET else self.file_algo
        enc_path = self.files_dir / f"{file_id}.enc"
        stego_paths: list[Path] = []
        try:
            with open(enc_path, "wb") as out:
                res = file_cipher.encrypt_stream(
                    derive_content_keys(cek).file_key, io.BytesIO(data), out, algo=algo,
                    aad=message_id.encode(), max_size=self.max_file_bytes)
            message = MessageRecord(id=message_id, kind=kind, sender_pk=sender.id, created_at=_now(),
                                    recipient_pks=[r.id for r in recipients], file_id=file_id)
            deliveries = self._build_deliveries(message_id, recipients, secret_b, cek, stego_paths)
            file_rec = FileRecord(id=file_id, message_id=message_id, original_name=name,
                                  mime=v.guess_mime(name), plaintext_size=res.plaintext_size,
                                  enc_path=str(enc_path), algo=res.algo, ciphertext_sha256=res.ciphertext_sha256)
            if kind == KIND_ASSET and self.asset_service is not None:
                file_rec.block_index = self.asset_service.register(message, file_rec, sender, recipients).index
        except Exception:
            enc_path.unlink(missing_ok=True)
            for p in stego_paths:
                p.unlink(missing_ok=True)
            raise
        self.repo.add_message(message, deliveries, file_rec)
        return message

    # ---- tampilan chat -----------------------------------------------------
    def inbox(self, user: User) -> list[dict]:
        items = []
        for d in self.repo.inbox(user.id):
            if d.status == STATUS_SENT:
                d.status = STATUS_DELIVERED
            items.append(self.describe_delivery(d))
        return sorted(items, key=lambda i: i["created_at"], reverse=True)

    def sent(self, user: User) -> list[dict]:
        out = []
        for m in sorted(self.repo.sent_messages(user.id), key=lambda m: m.created_at, reverse=True):
            out.append({
                "message_id": m.id, "kind": m.kind, "label": KIND_LABELS[m.kind],
                "is_important": m.kind in (KIND_IMPORTANT_TEXT, KIND_ASSET),
                "created_at": m.created_at.isoformat(), "encrypted": True,
                "recipients": [{"username": db.session.get(User, d.recipient_pk).username, "status": d.status}
                               for d in self.repo.deliveries_for_message(m.id)],
            })
        return out

    def describe_delivery(self, d: DeliveryRecord) -> dict:
        """Data untuk chatbox. Tidak pernah berisi plaintext."""
        m = self.repo.get_message(d.message_id)
        sender = db.session.get(User, m.sender_pk)
        info = {
            "delivery_id": d.id, "message_id": m.id, "kind": m.kind, "label": KIND_LABELS[m.kind],
            "is_important": m.kind in (KIND_IMPORTANT_TEXT, KIND_ASSET), "encrypted": True,
            "sender": {"username": sender.username, "full_name": sender.full_name, "unit": sender.unit},
            "created_at": m.created_at.isoformat(), "status": d.status,
            "attachments": [{"type": "stego_image", "name": Path(d.stego_path).name}],
        }
        if m.file_id:
            f = self.repo.get_file(m.file_id)
            info["file"] = {"name": f.original_name, "size": f.plaintext_size, "mime": f.mime}
            info["attachments"].insert(0, {"type": "ciphertext_file", "name": Path(f.enc_path).name})
        else:
            info["attachments"].insert(0, {"type": "ciphertext", "size": len(m.ciphertext)})
        return info

    # ---- internal ----------------------------------------------------------
    def _resolve_recipients(self, sender: User, usernames) -> list[User]:
        if isinstance(usernames, str):
            usernames = [usernames]
        names, seen = [], set()
        for u in usernames or []:
            u = (u or "").strip().lower()
            if u and u not in seen:
                seen.add(u)
                names.append(u)
        if not names:
            raise ValidationError("Pilih minimal satu penerima.")
        recipients = []
        for n in names:                                    # semua divalidasi dulu sebelum apa pun disimpan
            user = user_service.get_by_username(n)
            if not user.is_active:
                raise UserNotFoundError(f"Pengguna '{n}' tidak aktif.")
            if user.id == sender.id:
                raise ValidationError("Tidak dapat mengirim kepada diri sendiri.")
            recipients.append(user)
        return recipients

    def _build_deliveries(self, message_id, recipients, secret_b, cek, created_paths=None) -> list[DeliveryRecord]:
        deliveries, created = [], created_paths if created_paths is not None else []
        try:
            for r in recipients:
                rid = r.user_id                                        # ID dari database, bukan input pengirim
                wrapped = wrap_cek(secret_b, rid, cek)
                stego_png = embed_key(pick_random_cover(self.covers_dir), rid, secret_b)
                path = self.stego_dir / f"{_new_id()}.png"
                path.write_bytes(stego_png)
                created.append(path)
                deliveries.append(DeliveryRecord(id=_new_id(), message_id=message_id, recipient_pk=r.id,
                                                 kdf_salt=wrapped.salt, wrapped_key=wrapped.blob,
                                                 stego_path=str(path)))
        except Exception:
            for p in created:
                p.unlink(missing_ok=True)
            raise
        return deliveries

    def _read_source(self, source) -> bytes:
        if isinstance(source, (bytes, bytearray)):
            data = bytes(source)
        elif isinstance(source, (str, os.PathLike)):
            if os.path.getsize(source) > self.max_file_bytes:
                raise FileTooLargeError("Ukuran file melebihi batas yang diizinkan.")
            data = Path(source).read_bytes()
        else:
            data = source.read(self.max_file_bytes + 1)
        if len(data) > self.max_file_bytes:
            raise FileTooLargeError("Ukuran file melebihi batas yang diizinkan.")
        if not data:
            raise ValidationError("File kosong.")
        return data

    @staticmethod
    def _validate_image(data: bytes) -> None:
        try:
            Image.open(io.BytesIO(data)).verify()
        except Exception as exc:
            raise ValidationError("File bukan gambar yang valid.") from exc
