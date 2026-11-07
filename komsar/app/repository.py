"""Penyimpanan record sementara (in-memory). Ganti dengan implementasi database di tahap berikutnya
dengan antarmuka method yang sama."""
import threading
from typing import Optional

from .models.records import KIND_ASSET, DeliveryRecord, FileRecord, MessageRecord


class InMemoryRepository:
    def __init__(self):
        self._lock = threading.RLock()
        self._messages: dict[str, MessageRecord] = {}
        self._deliveries: dict[str, DeliveryRecord] = {}
        self._files: dict[str, FileRecord] = {}

    def add_message(self, message: MessageRecord, deliveries: list[DeliveryRecord],
                    file: Optional[FileRecord] = None) -> None:
        """Simpan satu pengiriman secara utuh (pesan + paket tiap penerima + file)."""
        with self._lock:
            self._messages[message.id] = message
            for d in deliveries:
                self._deliveries[d.id] = d
            if file is not None:
                self._files[file.id] = file

    def get_message(self, message_id: str) -> Optional[MessageRecord]:
        return self._messages.get(message_id)

    def get_delivery(self, delivery_id: str) -> Optional[DeliveryRecord]:
        return self._deliveries.get(delivery_id)

    def get_file(self, file_id: str) -> Optional[FileRecord]:
        return self._files.get(file_id)

    def deliveries_for_message(self, message_id: str) -> list[DeliveryRecord]:
        return [d for d in self._deliveries.values() if d.message_id == message_id]

    def inbox(self, recipient_pk: int) -> list[DeliveryRecord]:
        return [d for d in self._deliveries.values() if d.recipient_pk == recipient_pk]

    def sent_messages(self, sender_pk: int) -> list[MessageRecord]:
        return [m for m in self._messages.values() if m.sender_pk == sender_pk]

    def asset_files(self, user_pk: int) -> list[FileRecord]:
        """Aset penting yang dikirim atau diterima user tersebut."""
        out = []
        for f in self._files.values():
            m = self._messages[f.message_id]
            if m.kind == KIND_ASSET and (m.sender_pk == user_pk or user_pk in m.recipient_pks):
                out.append(f)
        return out
