"""Penyimpanan blok sementara (in-memory). Diganti tabel database nanti dengan method yang sama."""
import threading
from typing import Optional

from .block import Block


class InMemoryBlockStore:
    def __init__(self):
        self._blocks: list[Block] = []
        self.lock = threading.RLock()

    def all(self) -> list[Block]:
        return list(self._blocks)

    def append(self, block: Block) -> None:
        self._blocks.append(block)

    def last(self) -> Optional[Block]:
        return self._blocks[-1] if self._blocks else None
