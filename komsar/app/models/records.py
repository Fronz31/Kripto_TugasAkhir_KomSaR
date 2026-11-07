"""Record domain pesan/pengiriman (dataclass).

Sengaja belum memakai tabel database: desain database dibahas belakangan.
Semua akses lewat `app/repository.py` sehingga mudah diganti SQLAlchemy nanti.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

KIND_TEXT = "text"
KIND_IMPORTANT_TEXT = "important_text"
KIND_FILE = "file"
KIND_IMAGE = "image"
KIND_ASSET = "asset"
ALL_KINDS = (KIND_TEXT, KIND_IMPORTANT_TEXT, KIND_FILE, KIND_IMAGE, KIND_ASSET)
FILE_KINDS = (KIND_FILE, KIND_IMAGE, KIND_ASSET)

STATUS_SENT = "sent"
STATUS_DELIVERED = "delivered"
STATUS_DECRYPTED = "decrypted"


@dataclass
class MessageRecord:
    id: str
    kind: str
    sender_pk: int
    created_at: datetime
    recipient_pks: list[int] = field(default_factory=list)
    ciphertext: Optional[bytes] = None   # teks saja; pesan penting sudah berlapis enkripsi DB
    file_id: Optional[str] = None


@dataclass
class DeliveryRecord:
    """Paket per penerima: kunci terbungkus + gambar steganografi milik penerima itu."""
    id: str
    message_id: str
    recipient_pk: int
    kdf_salt: bytes
    wrapped_key: bytes
    stego_path: str
    status: str = STATUS_SENT
    failed_attempts: int = 0
    decrypted_at: Optional[datetime] = None


@dataclass
class FileRecord:
    id: str
    message_id: str
    original_name: str
    mime: str
    plaintext_size: int
    enc_path: str
    algo: str
    ciphertext_sha256: str
    block_index: Optional[int] = None   # nomor blok blockchain (aset penting)
