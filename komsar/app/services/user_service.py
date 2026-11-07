"""Manajemen pengguna: tambah, ubah, hapus, daftar, cari, resolusi username -> User ID."""
import re

from sqlalchemy import or_

from ..auth.password import hash_password
from ..errors import DuplicateUserError, UserNotFoundError, ValidationError
from ..extensions import db
from ..models.user import User

_USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,32}$")
_USER_ID_RE = re.compile(r"^[A-Z0-9]{2,16}$")


def _clean(value: str, field: str, max_len: int) -> str:
    value = (value or "").strip()
    if not value or len(value) > max_len:
        raise ValidationError(f"{field} wajib diisi (maks {max_len} karakter).")
    return value


def _validate_password(password: str) -> None:
    if not password or len(password) < 8:
        raise ValidationError("Password minimal 8 karakter.")


def create_user(username, user_id, full_name, unit, password, is_admin=False) -> User:
    username = (username or "").strip().lower()
    user_id = (user_id or "").strip().upper()
    if not _USERNAME_RE.match(username):
        raise ValidationError("Username 3-32 karakter: huruf kecil, angka, titik, underscore.")
    if not _USER_ID_RE.match(user_id):
        raise ValidationError("User ID 2-16 karakter: huruf/angka (mis. B001).")
    full_name = _clean(full_name, "Nama lengkap", 100)
    unit = _clean(unit, "Unit/Satuan", 60)
    _validate_password(password)

    if User.query.filter_by(username=username).first():
        raise DuplicateUserError("Username sudah dipakai.")
    if User.query.filter_by(user_id=user_id).first():
        raise DuplicateUserError("User ID sudah dipakai.")

    user = User(username=username, user_id=user_id, full_name=full_name, unit=unit,
                password_hash=hash_password(password), is_admin=is_admin)
    db.session.add(user)
    db.session.commit()
    return user


def get_user(pk: int) -> User:
    user = db.session.get(User, pk)
    if user is None:
        raise UserNotFoundError("Pengguna tidak ditemukan.")
    return user


def get_by_username(username: str) -> User:
    user = User.query.filter_by(username=(username or "").strip().lower()).first()
    if user is None:
        raise UserNotFoundError(f"Pengguna '{username}' tidak ditemukan.")
    return user


def resolve_user_id(username: str) -> str:
    """Pengirim memasukkan username; sistem mencari User ID (tidak diinput manual)."""
    user = get_by_username(username)
    if not user.is_active:
        raise UserNotFoundError(f"Pengguna '{username}' tidak aktif.")
    return user.user_id


def update_user(pk: int, full_name=None, unit=None, password=None, is_active=None, is_admin=None) -> User:
    """Username & User ID tidak dapat diubah (dipakai pada kunci & riwayat)."""
    user = get_user(pk)
    if full_name is not None:
        user.full_name = _clean(full_name, "Nama lengkap", 100)
    if unit is not None:
        user.unit = _clean(unit, "Unit/Satuan", 60)
    if password is not None:
        _validate_password(password)
        user.password_hash = hash_password(password)
    if is_active is not None:
        user.is_active = bool(is_active)
    if is_admin is not None:
        user.is_admin = bool(is_admin)
    db.session.commit()
    return user


def delete_user(pk: int) -> None:
    db.session.delete(get_user(pk))
    db.session.commit()


def list_users() -> list[User]:
    return User.query.order_by(User.username).all()


def search_users(query: str) -> list[User]:
    q = f"%{(query or '').strip()}%"
    return (User.query
            .filter(or_(User.username.ilike(q), User.full_name.ilike(q), User.unit.ilike(q)))
            .order_by(User.username).all())
