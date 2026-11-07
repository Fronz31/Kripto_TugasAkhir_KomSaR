"""Super encryption teks: Vigenère -> AES-GCM (pesan biasa dan pesan penting)."""
from ..errors import DecryptionError
from . import aes_gcm
from .kdf import derive_content_keys
from .vigenere import vigenere_decrypt, vigenere_encrypt

_AAD = b"komsar:text:v1"


def encrypt_text(plaintext: str, cek: bytes) -> bytes:
    keys = derive_content_keys(cek)
    inner = vigenere_encrypt(plaintext.encode("utf-8"), keys.vigenere_key)
    return aes_gcm.encrypt(keys.aes_key, inner, aad=_AAD)


def decrypt_text(blob: bytes, cek: bytes) -> str:
    keys = derive_content_keys(cek)
    inner = aes_gcm.decrypt(keys.aes_key, blob, aad=_AAD)
    try:
        return vigenere_decrypt(inner, keys.vigenere_key).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DecryptionError("Dekripsi gagal: hasil bukan teks valid.") from exc
