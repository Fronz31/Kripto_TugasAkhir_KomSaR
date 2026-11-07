"""Key derivation: Argon2id (password/ID -> master) + HKDF-SHA256 (master -> subkey).

Semua kunci turunan memakai label `info` berbeda agar tidak saling tertukar.
"""
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


@dataclass(frozen=True)
class KDFParams:
    time_cost: int = 3
    memory_kib: int = 65536
    parallelism: int = 2


_params = KDFParams()


def set_kdf_params(params: KDFParams) -> None:
    global _params
    _params = params


def get_kdf_params() -> KDFParams:
    return _params


def _length_prefixed(*parts: bytes) -> bytes:
    """Gabungkan bagian-bagian tanpa ambiguitas ("ab"+"c" != "a"+"bc")."""
    return b"".join(len(p).to_bytes(2, "big") + p for p in parts)


def _argon2(ikm: bytes, salt: bytes) -> bytes:
    p = _params
    return hash_secret_raw(
        secret=ikm, salt=salt, time_cost=p.time_cost, memory_cost=p.memory_kib,
        parallelism=p.parallelism, hash_len=32, type=Type.ID,
    )


def derive_master(secret: bytes, user_id: str, salt: bytes) -> bytes:
    """Material kunci dari ID penerima + kunci rahasia (+ salt)."""
    return _argon2(_length_prefixed(secret, user_id.encode("utf-8")), salt)


def derive_id_master(user_id: str, salt: bytes) -> bytes:
    """Material kunci steganografi dari ID penerima saja (+ salt)."""
    return _argon2(_length_prefixed(user_id.encode("utf-8")), salt)


def hkdf(key: bytes, info: bytes, length: int = 32) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(key)


@dataclass(frozen=True)
class ContentKeys:
    vigenere_key: bytes
    aes_key: bytes
    file_key: bytes


def derive_content_keys(cek: bytes) -> ContentKeys:
    """Pecah CEK (content encryption key) menjadi subkey independen."""
    if len(cek) != 32:
        raise ValueError("CEK harus 32 byte.")
    return ContentKeys(
        vigenere_key=hkdf(cek, b"komsar:vigenere:v1"),
        aes_key=hkdf(cek, b"komsar:aes-text:v1"),
        file_key=hkdf(cek, b"komsar:file:v1"),
    )
