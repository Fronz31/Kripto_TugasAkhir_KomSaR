"""Audit log: siapa melakukan apa, kapan, dari mana.

Pemakaian: `audit(SEND_FILE, target=message.id, kind="file")`. Argumen tambahan disimpan di kolom `meta`.
Log TIDAK BOLEH berisi plaintext, kunci rahasia, User ID, token dongle, atau password; kunci meta
dengan nama terlarang ditolak (ValueError). `target` cukup username / id pesan / id paket / id dongle.
Fase berikutnya (suara, alur login) menambah nama aksi di ACTIONS lalu memanggil `audit(...)`.
"""
from flask import g, has_request_context, request, session

from ..extensions import db
from ..models.security import AuditLog
from ..models.user import User

LOGIN_SUCCESS = "login_success"
LOGIN_FAILED = "login_failed"        # target = username yang dicoba
LOGOUT = "logout"
SEND_TEXT = "send_text"              # meta kind, recipients, failed
SEND_FILE = "send_file"              # file & gambar
SEND_ASSET = "send_asset"
DECRYPT_SUCCESS = "decrypt_success"  # target = id paket (delivery)
DECRYPT_FAILED = "decrypt_failed"    # meta step=extract|open, reason=nama error
INTEGRITY_FAILED = "integrity_failed"
USER_CREATE = "user_create"          # target = username
USER_UPDATE = "user_update"
USER_DELETE = "user_delete"
USER_REGENERATE_ID = "user_regenerate_id"
DONGLE_REGISTER = "dongle_register"  # target = dongle_id (token tidak pernah dicatat)
DONGLE_DEACTIVATE = "dongle_deactivate"

ACTIONS = (LOGIN_SUCCESS, LOGIN_FAILED, LOGOUT, SEND_TEXT, SEND_FILE, SEND_ASSET, DECRYPT_SUCCESS, DECRYPT_FAILED,
           INTEGRITY_FAILED, USER_CREATE, USER_UPDATE, USER_DELETE, USER_REGENERATE_ID, DONGLE_REGISTER,
           DONGLE_DEACTIVATE)

FORBIDDEN_META = {"password", "secret", "secret_key", "key", "user_id", "token", "plaintext", "text", "message"}


def audit(action: str, target=None, user=None, **meta) -> AuditLog:
    """Catat satu kejadian. `user` default = pengguna login (g.user); IP & dongle_id diambil dari request."""
    bad = FORBIDDEN_META & set(meta)
    if bad:
        raise ValueError(f"Data sensitif tidak boleh masuk audit log: {sorted(bad)}")
    ip = dongle_id = None
    if has_request_context():
        ip, dongle_id = request.remote_addr, session.get("dongle_id")
        if user is None:
            user = g.get("user")
    row = AuditLog(action=action, target=None if target is None else str(target)[:255],
                   user_id=user.id if user is not None else None, ip=ip, dongle_id=dongle_id, meta=meta or None)
    db.session.add(row)
    db.session.commit()
    return row


def list_logs(username: str = "", action: str = "", page: int = 1, per_page: int = 50):
    """Terbaru lebih dulu; filter username (persis) dan aksi."""
    q = db.select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if username:
        q = q.join(User, AuditLog.user_id == User.id).where(User.username == username.strip().lower())
    if action:
        q = q.where(AuditLog.action == action)
    return db.paginate(q, page=page, per_page=per_page, error_out=False)
