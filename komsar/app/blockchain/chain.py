"""Blockchain sederhana: hash chaining SHA-256 (tanpa Proof-of-Work).

Sifat: TAMPER-EVIDENT. Perubahan isi blok, penyisipan, atau penghapusan di tengah rantai terdeteksi
oleh `validate()`. Bukan tamper-proof: pihak yang dapat menulis ke penyimpanan DAN menghitung ulang
seluruh hash setelah blok yang diubah dapat menghasilkan rantai yang tampak konsisten.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..errors import ValidationError
from .block import GENESIS_PREV_HASH, Block
from .store import SqlBlockStore


@dataclass
class ChainValidation:
    valid: bool
    length: int
    errors: list[str] = field(default_factory=list)
    first_invalid_index: Optional[int] = None


class Blockchain:
    def __init__(self, store=None):
        self.store = store or SqlBlockStore()
        with self.store.lock:
            if self.store.last() is None:
                self.store.append(Block(
                    index=0, timestamp=_now(), asset_id="GENESIS", ciphertext_hash=GENESIS_PREV_HASH,
                    metadata={"note": "genesis"}, previous_hash=GENESIS_PREV_HASH).seal())

    def add_block(self, asset_id: str, ciphertext_hash: str, metadata: dict, sender: dict, recipients: list) -> Block:
        if not asset_id or len(ciphertext_hash) != 64:
            raise ValidationError("Data blok tidak valid.")
        with self.store.lock:
            if self.get_block_by_asset(asset_id) is not None:
                raise ValidationError("Aset ini sudah tercatat di blockchain.")
            last = self.store.last()
            block = Block(index=last.index + 1, timestamp=_now(), asset_id=asset_id,
                          ciphertext_hash=ciphertext_hash, metadata=dict(metadata), sender=dict(sender),
                          recipients=list(recipients), previous_hash=last.hash).seal()
            self.store.append(block)
            return block

    def blocks(self) -> list[Block]:
        return self.store.all()

    def get_block(self, index: int) -> Optional[Block]:
        return next((b for b in self.store.all() if b.index == index), None)

    def get_block_by_asset(self, asset_id: str) -> Optional[Block]:
        return next((b for b in self.store.all() if b.asset_id == asset_id), None)

    def validate(self) -> ChainValidation:
        blocks = self.store.all()
        errors: list[str] = []
        first_bad: Optional[int] = None

        def fail(i: int, msg: str):
            nonlocal first_bad
            errors.append(f"Blok #{i}: {msg}")
            if first_bad is None:
                first_bad = i

        if not blocks:
            return ChainValidation(False, 0, ["Rantai kosong."], 0)
        for pos, b in enumerate(blocks):
            if b.index != pos:
                fail(pos, f"nomor blok tidak berurutan (ditemukan {b.index}, seharusnya {pos})")
            if b.hash != b.compute_hash():
                fail(b.index, "hash tidak cocok dengan isi blok (data diubah)")
            expected_prev = GENESIS_PREV_HASH if pos == 0 else blocks[pos - 1].hash
            if b.previous_hash != expected_prev:
                fail(b.index, "previous_hash tidak sesuai dengan blok sebelumnya")
            if pos > 0 and b.timestamp < blocks[pos - 1].timestamp:
                fail(b.index, "timestamp lebih lama dari blok sebelumnya")
        return ChainValidation(not errors, len(blocks), errors, first_bad)

    def export_json(self, path) -> Path:
        """Ekspor rantai ke berkas JSON untuk inspeksi (mis. sebelum database tersedia)."""
        path = Path(path)
        path.write_text(json.dumps([b.to_record() for b in self.store.all()], indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
