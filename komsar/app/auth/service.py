"""Autentikasi, sesi login sementara (pending), lockout, dan pengelolaan session Flask.

Alur login: (1) username + password + dongle -> sesi pending (3 menit) -> (2) suara, atau
pendaftaran suara + ganti password pada login pertama -> `complete_login`.
"""
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import abort, current_app, session

from ..extensions import db
from ..models.user import User
from .password import verify_password

SESSION_KEY = "user_pk"
PENDING_TTL = 180               # detik antara langkah 1 dan 2
MAX_PASSWORD_FAILS = 5
MAX_VOICE_FAILS = 3
LOCK_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    """SQLite mengembalikan datetime naive (UTC)."""
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def find_user(username: str):
    return User.query.filter_by(username=(username or "").strip().lower()).first()


def authenticate(username: str, password: str):
    """Kembalikan User jika kredensial valid dan akun aktif, selain itu None (tanpa lockout)."""
    user = find_user(username)
    if user is None or not user.is_active:
        return None
    return user if verify_password(user.password_hash, password or "") else None


# ---- lockout ----
def is_locked(user) -> bool:
    until = _aware(user.locked_until)
    return until is not None and until > _now()


def lock(user) -> None:
    user.locked_until = _now() + timedelta(minutes=LOCK_MINUTES)
    user.failed_logins = 0
    db.session.commit()


def record_failure(user) -> bool:
    """Tambah hitungan gagal (password atau suara). Return True bila akun baru saja dikunci."""
    user.failed_logins = (user.failed_logins or 0) + 1
    if user.failed_logins >= MAX_PASSWORD_FAILS:
        lock(user)
        return True
    db.session.commit()
    return False


def enroll_expired(user) -> bool:
    deadline = _aware(user.enroll_deadline)
    return deadline is not None and deadline < _now()


# ---- sesi ----
def start_pending(user, dongle_id) -> None:
    """Langkah 1 lolos: belum login, hanya `pending_user_id` dengan batas waktu."""
    session.clear()
    now = int(time.time())
    session.update(pending_user_id=user.id, pending_since=now, dongle_id=dongle_id, dongle_seen=now)


def pending_state():
    """("ok", user) | ("expired", user) | (None, None) untuk sesi pending saat ini."""
    pk, since = session.get("pending_user_id"), session.get("pending_since")
    if pk is None or since is None:
        return None, None
    user = db.session.get(User, pk)
    if user is None or not user.is_active or is_locked(user):
        return None, None
    return ("expired" if time.time() - since > PENDING_TTL else "ok"), user


def pending_user():
    state, user = pending_state()
    return user if state == "ok" else None


def login_user(user: User) -> None:
    dongle_id = session.get("dongle_id")
    session.clear()  # cegah session fixation
    session.permanent = True
    session[SESSION_KEY] = user.id
    session["login_at"] = int(time.time())
    if dongle_id:
        # Dongle dibuktikan di langkah 1 (<= 3 menit lalu); heartbeat desktop melanjutkan dari sini.
        session["dongle_id"] = dongle_id
        session["dongle_seen"] = int(time.time())


def complete_login(user: User) -> None:
    """Langkah terakhir login: reset hitungan gagal lalu buat sesi penuh."""
    user.failed_logins = 0
    user.locked_until = None
    db.session.commit()
    login_user(user)


def logout_user() -> None:
    session.clear()


def current_user():
    pk = session.get(SESSION_KEY)
    if not pk:
        return None
    login_at = session.get("login_at")
    if login_at is not None and time.time() - login_at > current_app.permanent_session_lifetime.total_seconds():
        return None     # batas umur sesi absolut (8 jam), walau cookie terus diperbarui
    return db.session.get(User, pk)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None or not user.is_active:
            abort(401)
        return view(*args, **kwargs)
    return wrapped
