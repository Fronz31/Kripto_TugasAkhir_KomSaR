"""Hashing password dengan Argon2id."""
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_ph = PasswordHasher()  # default argon2-cffi = Argon2id


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


# Hash tetap untuk username tak dikenal/nonaktif/terkunci: waktu respons setara dengan akun yang ada.
_DUMMY_HASH = _ph.hash("komsar-dummy-password")


def dummy_verify(password: str) -> bool:
    """Verifikasi Argon2 terhadap hash dummy agar username tidak bisa dienumerasi lewat timing. Selalu False."""
    verify_password(_DUMMY_HASH, password)
    return False
