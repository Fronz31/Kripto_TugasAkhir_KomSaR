"""AES-256-GCM. Format blob: nonce(12) || ciphertext || tag(16). Nonce acak per enkripsi."""
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..errors import DecryptionError

NONCE_SIZE = 12
TAG_SIZE = 16


def encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(NONCE_SIZE)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    if len(blob) < NONCE_SIZE + TAG_SIZE:
        raise DecryptionError("Data terenkripsi tidak valid.")
    try:
        return AESGCM(key).decrypt(blob[:NONCE_SIZE], blob[NONCE_SIZE:], aad)
    except (InvalidTag, ValueError) as exc:
        raise DecryptionError("Dekripsi gagal: kunci salah atau data telah diubah.") from exc
