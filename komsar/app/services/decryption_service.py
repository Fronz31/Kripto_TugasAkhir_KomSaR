"""Decryption Center: satu pintu dekripsi untuk semua jenis data.

Urutan: cek hak akses -> ekstrak kunci dari gambar stego dengan ID -> unwrap CEK ->
(aset: verifikasi hash ciphertext) -> dekripsi sesuai jenis.
Jika gagal: error jelas, tanpa plaintext parsial, ciphertext & file sumber tidak diubah.
"""
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..crypto import file_cipher
from ..crypto.db_layer import decrypt_from_db
from ..crypto.kdf import derive_content_keys
from ..crypto.key_wrap import unwrap_cek
from ..crypto.text import decrypt_text
from ..errors import (AccessDeniedError, DecryptionError, IntegrityViolationError, InvalidIDError,
                      StegoError, StegoKeyMismatchError, ValidationError)
from ..models.records import (ALL_KINDS, KIND_ASSET, KIND_IMPORTANT_TEXT, KIND_TEXT, STATUS_DECRYPTED)
from ..models.user import User
from ..stego.extract import extract_key


@dataclass
class DecryptionResult:
    kind: str
    is_important: bool
    text: Optional[str] = None
    filename: Optional[str] = None
    mime: Optional[str] = None
    data: Optional[bytes] = None


class DecryptionCenter:
    def __init__(self, repo, master_key: bytes, asset_service=None):
        self.repo, self.master_key = repo, master_key
        self.asset_service = asset_service

    def extract_secret(self, user: User, delivery_id: str, id_input: str, expected_kind: Optional[str] = None) -> str:
        """LANGKAH 1: ekstrak kunci dari gambar steganografi memakai ID penerima (ID salah -> InvalidIDError)."""
        delivery, _ = self._authorize(user, delivery_id, expected_kind)
        rid = self._normalize_id(id_input)
        try:
            secret = extract_key(self._stego_bytes(delivery), rid)
        except (InvalidIDError, StegoError):
            delivery.failed_attempts += 1
            raise
        try:
            return secret.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StegoError("Kunci pada gambar bukan teks yang dapat ditampilkan.") from exc

    def open(self, user: User, delivery_id: str, id_input: str, expected_kind: Optional[str] = None,
             secret_input: Optional[str] = None) -> DecryptionResult:
        """LANGKAH 2: gabungkan ID + kunci, lalu dekripsi.

        secret_input = kunci yang diketik ulang penerima dari hasil ekstraksi. Jika None, kunci diambil
        langsung dari gambar (jalur otomatis)."""
        delivery, message = self._authorize(user, delivery_id, expected_kind)
        rid = self._normalize_id(id_input)
        try:
            if secret_input is None:
                cek = self._recover_cek(delivery, rid)
            else:
                cek = self._cek_from_entered_key(delivery, rid, secret_input)
            result = self._decrypt(message, cek)
        except (InvalidIDError, DecryptionError, StegoError):
            delivery.failed_attempts += 1
            raise
        delivery.status = STATUS_DECRYPTED
        delivery.decrypted_at = datetime.now(timezone.utc)
        return result

    def _authorize(self, user: User, delivery_id: str, expected_kind: Optional[str]):
        delivery = self.repo.get_delivery(delivery_id)
        if delivery is None or delivery.recipient_pk != user.id:      # pesan sama agar tidak membocorkan keberadaan data
            raise AccessDeniedError("Data tidak ditemukan atau Anda tidak berhak membukanya.")
        message = self.repo.get_message(delivery.message_id)
        if expected_kind is not None:
            if expected_kind not in ALL_KINDS:
                raise ValidationError("Jenis data tidak dikenal.")
            if expected_kind != message.kind:
                raise ValidationError("Jenis data yang dipilih tidak sesuai dengan data ini.")
        return delivery, message

    @staticmethod
    def _normalize_id(id_input: str) -> str:
        rid = (id_input or "").strip().upper()
        if not rid:
            raise ValidationError("User ID wajib diisi.")
        return rid

    @staticmethod
    def _stego_bytes(delivery) -> bytes:
        stego = Path(delivery.stego_path)
        if not stego.exists():
            raise StegoError("Gambar steganografi tidak ditemukan.")
        return stego.read_bytes()

    def _cek_from_entered_key(self, delivery, rid: str, secret_input: str) -> bytes:
        if not secret_input:
            raise ValidationError("Kunci hasil steganografi wajib diisi.")
        try:
            return unwrap_cek(secret_input, rid, delivery.kdf_salt, delivery.wrapped_key)
        except DecryptionError as exc:
            raise StegoKeyMismatchError(
                "Kunci hasil steganografi yang dimasukkan tidak sesuai. Salin persis seperti yang "
                "ditampilkan dari gambar, lalu coba lagi.") from exc

    # ---- internal ----------------------------------------------------------
    def _recover_cek(self, delivery, rid: str) -> bytes:
        secret = extract_key(self._stego_bytes(delivery), rid)          # InvalidIDError jika ID salah
        return unwrap_cek(secret, rid, delivery.kdf_salt, delivery.wrapped_key)

    def _decrypt(self, message, cek: bytes) -> DecryptionResult:
        if message.kind in (KIND_TEXT, KIND_IMPORTANT_TEXT):
            ct = message.ciphertext
            if message.kind == KIND_IMPORTANT_TEXT:
                ct = decrypt_from_db(self.master_key, ct)               # buka lapisan DB dulu
            return DecryptionResult(kind=message.kind, is_important=message.kind == KIND_IMPORTANT_TEXT,
                                    text=decrypt_text(ct, cek))

        f = self.repo.get_file(message.file_id)
        enc = Path(f.enc_path)
        if not enc.exists():
            raise DecryptionError("File terenkripsi tidak ditemukan.")
        if message.kind == KIND_ASSET:                       # verifikasi integritas SEBELUM dekripsi
            if self.asset_service is not None:
                report = self.asset_service.check_file(f)    # blockchain: rantai + hash ciphertext + metadata
                if not report.ok:
                    raise IntegrityViolationError(f"Integritas aset gagal: {report.message}")
            elif hashlib.sha256(enc.read_bytes()).hexdigest() != f.ciphertext_sha256:
                raise IntegrityViolationError("Integritas aset gagal: ciphertext tidak cocok dengan hash tercatat.")
        blob = enc.read_bytes()
        data = file_cipher.decrypt_bytes(derive_content_keys(cek).file_key, blob, aad=message.id.encode())
        return DecryptionResult(kind=message.kind, is_important=message.kind == KIND_ASSET,
                                filename=f.original_name, mime=f.mime, data=data)
