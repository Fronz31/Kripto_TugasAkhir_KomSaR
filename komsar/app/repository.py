"""Akses record pesan/pengiriman/file di database (SQLAlchemy)."""
from typing import Optional

from .extensions import db
from .models.records import (FILE_KINDS, KIND_ASSET, STATUS_FAILED, DeliveryRecord, FileRecord,
                             MessageRecord)


class SqlRepository:
    def add_message(self, message: MessageRecord, deliveries: list[DeliveryRecord],
                    file: Optional[FileRecord] = None) -> None:
        """Simpan satu pengiriman secara utuh (pesan + paket tiap penerima + file) dalam satu transaksi."""
        try:
            db.session.add(message)
            db.session.add_all(deliveries)
            if file is not None:
                db.session.add(file)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def get_message(self, message_id: str) -> Optional[MessageRecord]:
        return db.session.get(MessageRecord, message_id)

    def get_delivery(self, delivery_id: str) -> Optional[DeliveryRecord]:
        return db.session.get(DeliveryRecord, delivery_id)

    def get_file(self, file_id: str) -> Optional[FileRecord]:
        return db.session.get(FileRecord, file_id)

    def deliveries_for_message(self, message_id: str) -> list[DeliveryRecord]:
        return DeliveryRecord.query.filter_by(message_id=message_id).order_by(DeliveryRecord.created_at).all()

    def inbox(self, recipient_pk: int) -> list[DeliveryRecord]:
        return DeliveryRecord.query.filter_by(recipient_pk=recipient_pk).order_by(DeliveryRecord.created_at).all()

    def sent_messages(self, sender_pk: int) -> list[MessageRecord]:
        return MessageRecord.query.filter_by(sender_pk=sender_pk).order_by(MessageRecord.created_at).all()

    def conversation(self, me_pk: int, other_pk: int) -> list[DeliveryRecord]:
        """Paket dua arah antara dua pengguna, urut waktu. Paket gagal untuk `me` tidak ikut (tidak bisa dibuka)."""
        return (DeliveryRecord.query.join(MessageRecord)
                .filter(db.or_(db.and_(MessageRecord.sender_pk == me_pk, DeliveryRecord.recipient_pk == other_pk),
                               db.and_(MessageRecord.sender_pk == other_pk, DeliveryRecord.recipient_pk == me_pk,
                                       DeliveryRecord.status != STATUS_FAILED)))
                .order_by(MessageRecord.created_at).all())

    def file_messages(self, user_pk: int) -> list[MessageRecord]:
        """Kiriman file/gambar/aset yang dikirim atau diterima user, terbaru dulu."""
        received = db.select(DeliveryRecord.message_id).filter(DeliveryRecord.recipient_pk == user_pk,
                                                               DeliveryRecord.status != STATUS_FAILED)
        return (MessageRecord.query
                .filter(MessageRecord.kind.in_(FILE_KINDS),
                        db.or_(MessageRecord.sender_pk == user_pk, MessageRecord.id.in_(received)))
                .order_by(MessageRecord.created_at.desc()).all())

    def asset_files(self, user_pk: int) -> list[FileRecord]:
        """Aset penting yang dikirim atau diterima user tersebut."""
        received = db.select(DeliveryRecord.message_id).filter_by(recipient_pk=user_pk)
        return (FileRecord.query.join(MessageRecord)
                .filter(MessageRecord.kind == KIND_ASSET,
                        db.or_(MessageRecord.sender_pk == user_pk, MessageRecord.id.in_(received)))
                .order_by(MessageRecord.created_at).all())
