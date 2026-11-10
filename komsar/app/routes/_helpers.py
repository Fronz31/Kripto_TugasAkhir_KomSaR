import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import abort, current_app, flash, g, jsonify, redirect, request, session, url_for

from ..auth.service import SESSION_KEY, current_user

WIB = timezone(timedelta(hours=7))
STATUS_LABELS = {"sent": "Terkirim", "delivered": "Diterima", "decrypted": "Sudah dibuka", "failed": "Gagal"}


def svc():
    return current_app.extensions["komsar"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None or not user.is_active:
            session.clear()
            flash("Silakan login terlebih dahulu.", "info")
            return redirect(url_for("auth.login"))
        g.user = user
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @login_required
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def protect_csrf():
    if request.endpoint == "api.dongle_check":      # dipanggil klien desktop tanpa sesi
        return
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        if not sent or not secrets.compare_digest(sent, session.get("csrf_token", "")):
            abort(400, "Token keamanan formulir tidak valid. Muat ulang halaman lalu coba lagi.")


DONGLE_EXEMPT = {"static", "api.dongle_check", "api.dongle_heartbeat"}


def require_dongle():
    """Akhiri sesi bila KOMSAR_REQUIRE_DONGLE aktif dan heartbeat dongle kedaluwarsa."""
    if not current_app.config.get("KOMSAR_REQUIRE_DONGLE") or request.endpoint in DONGLE_EXEMPT:
        return None
    user_pk = session.get(SESSION_KEY)
    seen = session.get("dongle_seen")
    if user_pk is None:
        return None
    if seen is not None and time.time() - seen <= current_app.config["DONGLE_HEARTBEAT_TIMEOUT"]:
        return None
    svc().cache.clear_user(user_pk)
    session.clear()
    if request.path.startswith("/api/"):
        return jsonify(error="Dongle tidak terdeteksi. Sesi diakhiri."), 401
    flash("Dongle tidak terdeteksi. Colokkan dongle lalu login kembali.", "error")
    return redirect(url_for("auth.login"))


def flash_partial_failure(message) -> None:
    """Peringatan bila paket untuk sebagian penerima gagal dibuat (status `failed`)."""
    failed = sum(d.status == "failed" for d in message.deliveries)
    if failed:
        flash(f"{failed} penerima gagal disiapkan; lihat status di kotak terkirim.", "error")


def fmt_dt(iso) -> str:
    if isinstance(iso, datetime):           # kolom DateTime; SQLite mengembalikan naive (UTC)
        iso = (iso if iso.tzinfo else iso.replace(tzinfo=timezone.utc)).isoformat()
    return datetime.fromisoformat(iso).astimezone(WIB).strftime("%d %b %Y %H:%M WIB")


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def parse_usernames(raw: str) -> list[str]:
    """Pecah input 'budi01, citra01' menjadi daftar username."""
    return [u for u in re.split(r"[,;\s]+", (raw or "").strip()) if u]
