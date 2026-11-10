"""Dongle flashdisk: server menyimpan SHA-256(token) + serial volume, bukan token-nya."""
import base64
import hashlib
import hmac
import os
import re
import uuid
from datetime import datetime, timezone

from ..extensions import db
from ..models.security import Dongle

SERIAL_RE = re.compile(r"^[0-9A-F]{8}$")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class DongleService:
    def register(self, label: str, volume_serial: str, admin=None) -> tuple[str, str]:
        """Buat dongle baru. Token hanya dikembalikan sekali (untuk ditulis ke flashdisk)."""
        label = str(label or "").strip()
        serial = str(volume_serial or "").strip().upper()
        if not label or len(label) > 100:
            raise ValueError("Label dongle wajib diisi (maks. 100 karakter).")
        if not SERIAL_RE.match(serial):
            raise ValueError("Serial volume harus 8 digit heksadesimal.")
        dongle_id = str(uuid.uuid4())
        token = base64.b64encode(os.urandom(32)).decode()
        db.session.add(Dongle(id=dongle_id, label=label, token_hash=_hash(token), volume_serial=serial,
                              registered_by=admin.id if admin else None))
        db.session.commit()
        return dongle_id, token

    def verify(self, dongle_id, token, volume_serial):
        """Dongle bila aktif, token cocok, dan serial cocok; selain itu None."""
        if not all(isinstance(v, str) for v in (dongle_id, token, volume_serial)):
            return None
        d = db.session.get(Dongle, dongle_id)
        if d is None or not d.is_active:
            return None
        if not hmac.compare_digest(_hash(token), d.token_hash) or volume_serial.upper() != d.volume_serial:
            return None
        d.last_used_at = datetime.now(timezone.utc)
        db.session.commit()
        return d

    def deactivate(self, dongle_id: str) -> None:
        d = db.session.get(Dongle, dongle_id)
        if d is not None:
            d.is_active = False
            db.session.commit()

    def list(self) -> list[Dongle]:
        return Dongle.query.order_by(Dongle.created_at.desc()).all()
