import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import abort, current_app, flash, g, redirect, request, session, url_for

from ..auth.service import current_user

WIB = timezone(timedelta(hours=7))
STATUS_LABELS = {"sent": "Terkirim", "delivered": "Diterima", "decrypted": "Sudah dibuka"}


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
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        if not sent or not secrets.compare_digest(sent, session.get("csrf_token", "")):
            abort(400, "Token keamanan formulir tidak valid. Muat ulang halaman lalu coba lagi.")


def fmt_dt(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(WIB).strftime("%d %b %Y %H:%M WIB")


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def parse_usernames(raw: str) -> list[str]:
    """Pecah input 'budi01, citra01' menjadi daftar username."""
    return [u for u in re.split(r"[,;\s]+", (raw or "").strip()) if u]
