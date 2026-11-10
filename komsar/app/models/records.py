"""Record pesan, paket per penerima, dan file (tabel `messages`, `deliveries`, `files`).

Nama atribut Python dipertahankan dari versi in-memory (mis. `sender_pk`), nama kolom mengikuti
rencana database (mis. `sender_id`). Semua akses lewat `app/repository.py`.
"""
from datetime import datetime, timezone

from ..extensions import db

KIND_TEXT = "text"
KIND_IMPORTANT_TEXT = "important_text"
KIND_FILE = "file"
KIND_IMAGE = "image"
KIND_ASSET = "asset"
ALL_KINDS = (KIND_TEXT, KIND_IMPORTANT_TEXT, KIND_FILE, KIND_IMAGE, KIND_ASSET)
FILE_KINDS = (KIND_FILE, KIND_IMAGE, KIND_ASSET)
IMPORTANT_KINDS = (KIND_IMPORTANT_TEXT, KIND_ASSET)

STATUS_SENT = "sent"
STATUS_DELIVERED = "delivered"
STATUS_DECRYPTED = "decrypted"
STATUS_FAILED = "failed"
ALL_STATUSES = (STATUS_SENT, STATUS_DELIVERED, STATUS_DECRYPTED, STATUS_FAILED)


def _now():
    return datetime.now(timezone.utc)


class MessageRecord(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.String(32), primary_key=True)
    sender_pk = db.Column("sender_id", db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    important = db.Column(db.Boolean, nullable=False, default=False)
    ciphertext = db.Column(db.LargeBinary)          # teks saja; pesan penting sudah berlapis enkripsi DB
    meta = db.Column(db.JSON)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now, index=True)

    deliveries = db.relationship("DeliveryRecord", back_populates="message", order_by="DeliveryRecord.created_at")
    file = db.relationship("FileRecord", back_populates="message", uselist=False)

    @property
    def recipient_pks(self) -> list[int]:
        return [d.recipient_pk for d in self.deliveries]

    @property
    def file_id(self):
        return self.file.id if self.file else None


class DeliveryRecord(db.Model):
    """Paket per penerima: kunci terbungkus + gambar steganografi milik penerima itu."""
    __tablename__ = "deliveries"
    __table_args__ = (db.CheckConstraint(f"status IN {ALL_STATUSES}", name="ck_delivery_status"),)

    id = db.Column(db.String(32), primary_key=True)
    message_id = db.Column(db.String(32), db.ForeignKey("messages.id"), nullable=False, index=True)
    recipient_pk = db.Column("recipient_id", db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    wrapped_key = db.Column("wrapped_cek", db.LargeBinary, nullable=False)
    kdf_salt = db.Column("wrap_salt", db.LargeBinary, nullable=False)
    stego_png = db.Column(db.LargeBinary)
    status = db.Column(db.String(16), nullable=False, default=STATUS_SENT)
    error = db.Column(db.String(255))
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)
    decrypted_at = db.Column(db.DateTime(timezone=True))

    message = db.relationship("MessageRecord", back_populates="deliveries")


class FileRecord(db.Model):
    __tablename__ = "files"

    id = db.Column(db.String(32), primary_key=True)
    message_id = db.Column(db.String(32), db.ForeignKey("messages.id"), nullable=False, unique=True)
    original_name = db.Column(db.String(255), nullable=False)
    plaintext_size = db.Column("size", db.Integer, nullable=False)
    mime = db.Column(db.String(100), nullable=False)
    algo = db.Column(db.String(32), nullable=False)
    ciphertext = db.Column(db.LargeBinary)          # format KSF1 (file_cipher); kosong = ciphertext hilang
    ciphertext_sha256 = db.Column(db.String(64), nullable=False)
    block_index = db.Column(db.Integer)             # nomor blok blockchain (aset penting)

    message = db.relationship("MessageRecord", back_populates="file")
