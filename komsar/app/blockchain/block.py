"""Struktur blok. Hash = SHA-256 atas isi blok (JSON kanonik) tanpa field `hash` itu sendiri.

Blok TIDAK menyimpan plaintext aset, kunci, maupun file; hanya hash ciphertext + metadata.
"""
import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS_PREV_HASH = "0" * 64


@dataclass
class Block:
    index: int
    timestamp: str                      # ISO-8601 UTC
    asset_id: str
    ciphertext_hash: str                # SHA-256 ciphertext aset (hex)
    metadata: dict = field(default_factory=dict)
    sender: dict = field(default_factory=dict)
    recipients: list = field(default_factory=list)
    previous_hash: str = GENESIS_PREV_HASH
    hash: str = ""

    def compute_hash(self) -> str:
        payload = {
            "index": self.index, "timestamp": self.timestamp, "asset_id": self.asset_id,
            "ciphertext_hash": self.ciphertext_hash, "metadata": self.metadata,
            "sender": self.sender, "recipients": self.recipients, "previous_hash": self.previous_hash,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def seal(self) -> "Block":
        self.hash = self.compute_hash()
        return self

    def to_record(self) -> dict:
        """Bentuk dict siap disimpan ke database / diekspor."""
        return asdict(self)
