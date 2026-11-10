"""Penyimpanan blok di tabel `blocks` (SQLAlchemy). Method: all, append, last."""
import threading
from typing import Optional

from ..extensions import db
from .block import Block


class BlockRow(db.Model):
    """Sengaja tanpa foreign key ke `files`: blok genesis bukan file, dan rantai tetap harus bisa
    divalidasi walau baris file terhapus (terdeteksi sebagai ciphertext_missing/block_missing)."""
    __tablename__ = "blocks"

    idx = db.Column(db.Integer, primary_key=True, autoincrement=False)
    timestamp = db.Column(db.String(40), nullable=False)
    asset_id = db.Column(db.String(64), nullable=False, index=True)
    ciphertext_hash = db.Column(db.String(64), nullable=False)
    metadata_json = db.Column(db.JSON, nullable=False)
    sender = db.Column(db.JSON, nullable=False)
    recipients_json = db.Column(db.JSON, nullable=False)
    previous_hash = db.Column(db.String(64), nullable=False)
    hash = db.Column(db.String(64), nullable=False)

    def to_block(self) -> Block:
        return Block(index=self.idx, timestamp=self.timestamp, asset_id=self.asset_id,
                     ciphertext_hash=self.ciphertext_hash, metadata=self.metadata_json, sender=self.sender,
                     recipients=self.recipients_json, previous_hash=self.previous_hash, hash=self.hash)


class SqlBlockStore:
    def __init__(self):
        self.lock = threading.RLock()     # shortcut: kunci per proses, cukup untuk 1 worker gunicorn

    def all(self) -> list[Block]:
        return [r.to_block() for r in BlockRow.query.order_by(BlockRow.idx)]

    def append(self, block: Block) -> None:
        db.session.add(BlockRow(idx=block.index, timestamp=block.timestamp, asset_id=block.asset_id,
                                ciphertext_hash=block.ciphertext_hash, metadata_json=block.metadata,
                                sender=block.sender, recipients_json=block.recipients,
                                previous_hash=block.previous_hash, hash=block.hash))
        db.session.commit()

    def last(self) -> Optional[Block]:
        row = BlockRow.query.order_by(BlockRow.idx.desc()).first()
        return row.to_block() if row else None
