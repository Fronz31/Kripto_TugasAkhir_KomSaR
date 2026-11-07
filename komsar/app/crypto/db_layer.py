"""Lapisan enkripsi tambahan untuk penyimpanan database (pesan penting).

Kunci diturunkan dari master key aplikasi (env), sehingga aplikasi dapat membuka kembali lapisan ini.
"""
from . import aes_gcm
from .kdf import hkdf

_INFO = b"komsar:db-layer:v1"
_AAD = b"komsar:db-layer"


def encrypt_for_db(master_key: bytes, blob: bytes) -> bytes:
    return aes_gcm.encrypt(hkdf(master_key, _INFO), blob, aad=_AAD)


def decrypt_from_db(master_key: bytes, stored: bytes) -> bytes:
    return aes_gcm.decrypt(hkdf(master_key, _INFO), stored, aad=_AAD)
