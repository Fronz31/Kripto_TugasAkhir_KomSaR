"""Pembungkusan CEK per penerima: wrap_key = KDF(kunci_rahasia, ID_penerima, salt)."""
import os
from dataclasses import dataclass

from . import aes_gcm
from .kdf import derive_master, hkdf

SALT_SIZE = 16
_INFO = b"komsar:wrap:v1"


@dataclass(frozen=True)
class WrappedKey:
    salt: bytes
    blob: bytes


def _to_bytes(secret) -> bytes:
    return secret.encode("utf-8") if isinstance(secret, str) else secret


def generate_cek() -> bytes:
    return os.urandom(32)


def wrap_cek(secret, user_id: str, cek: bytes) -> WrappedKey:
    salt = os.urandom(SALT_SIZE)
    wrap_key = hkdf(derive_master(_to_bytes(secret), user_id, salt), _INFO)
    return WrappedKey(salt=salt, blob=aes_gcm.encrypt(wrap_key, cek, aad=user_id.encode("utf-8")))


def unwrap_cek(secret, user_id: str, salt: bytes, blob: bytes) -> bytes:
    wrap_key = hkdf(derive_master(_to_bytes(secret), user_id, salt), _INFO)
    return aes_gcm.decrypt(wrap_key, blob, aad=user_id.encode("utf-8"))
