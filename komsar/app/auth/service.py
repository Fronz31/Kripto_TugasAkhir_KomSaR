"""Autentikasi username+password dan pengelolaan session Flask."""
from functools import wraps

from flask import abort, session

from ..extensions import db
from ..models.user import User
from .password import verify_password

SESSION_KEY = "user_pk"


def authenticate(username: str, password: str):
    """Kembalikan User jika kredensial valid dan akun aktif, selain itu None."""
    user = User.query.filter_by(username=(username or "").strip().lower()).first()
    if user is None or not user.is_active:
        return None
    return user if verify_password(user.password_hash, password or "") else None


def login_user(user: User) -> None:
    session.clear()  # cegah session fixation
    session[SESSION_KEY] = user.id


def logout_user() -> None:
    session.clear()


def current_user():
    pk = session.get(SESSION_KEY)
    return db.session.get(User, pk) if pk else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None or not user.is_active:
            abort(401)
        return view(*args, **kwargs)
    return wrapped
