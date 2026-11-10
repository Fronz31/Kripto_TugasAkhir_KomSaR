"""Tabel untuk dongle, profil suara, dan audit log. Baru model; logikanya dikerjakan di fase berikutnya."""
from datetime import datetime, timezone

from ..extensions import db


def _now():
    return datetime.now(timezone.utc)


class Dongle(db.Model):
    __tablename__ = "dongles"

    id = db.Column(db.String(36), primary_key=True)                      # dongle_id (uuid)
    label = db.Column(db.String(100), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False)                # SHA-256(token), hex
    volume_serial = db.Column(db.String(32), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    registered_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=True)


class VoiceProfile(db.Model):
    __tablename__ = "voice_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    embedding_enc = db.Column(db.LargeBinary, nullable=False)           # embedding terenkripsi db_layer
    nonce = db.Column(db.LargeBinary, nullable=True)
    sample_count = db.Column(db.Integer, default=0, nullable=False)
    enrolled_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    target = db.Column(db.String(255), nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    dongle_id = db.Column(db.String(36), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False, index=True)
