"""Enkripsi file/gambar per-chunk (STREAM-style) dengan AEAD.

Algoritma: ChaCha20-Poly1305 (file & gambar biasa) atau AES-256-GCM (aset penting).
Format: MAGIC(4) | algo(1) | nonce_prefix(8) | chunk_size(4) | [chunk_ct + tag(16)]...
Nonce chunk = prefix(8) || counter(4). Chunk terakhir ditandai di AAD (anti-truncation).
Dekripsi menulis ke file sementara dan hanya dipindahkan jika SEMUA chunk valid
(tidak ada plaintext parsial).
"""
import hashlib
import io
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

from ..errors import DecryptionError, FileTooLargeError

MAGIC = b"KSF1"
ALGO_CHACHA20 = "chacha20-poly1305"
ALGO_AESGCM = "aes-256-gcm"
_ALGO_IDS = {ALGO_CHACHA20: 1, ALGO_AESGCM: 2}
_ID_ALGOS = {v: k for k, v in _ALGO_IDS.items()}
TAG_SIZE = 16
DEFAULT_CHUNK = 64 * 1024
HEADER_SIZE = 4 + 1 + 8 + 4
MAX_CHUNK = 16 * 1024 * 1024


@dataclass(frozen=True)
class EncryptResult:
    algo: str
    plaintext_size: int
    ciphertext_size: int
    ciphertext_sha256: str


def _aead(algo: str, key: bytes):
    if algo == ALGO_CHACHA20:
        return ChaCha20Poly1305(key)
    if algo == ALGO_AESGCM:
        return AESGCM(key)
    raise ValueError(f"Algoritma tidak dikenal: {algo}")


def _read_full(src, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        part = src.read(n - len(buf))
        if not part:
            break
        buf += part
    return buf


def _nonce(prefix: bytes, counter: int) -> bytes:
    return prefix + counter.to_bytes(4, "big")


def encrypt_stream(key, src, dst, algo=ALGO_CHACHA20, aad=b"", chunk_size=DEFAULT_CHUNK, max_size=None) -> EncryptResult:
    aead = _aead(algo, key)
    prefix = os.urandom(8)
    header = MAGIC + bytes([_ALGO_IDS[algo]]) + prefix + chunk_size.to_bytes(4, "big")
    sha = hashlib.sha256(header)
    dst.write(header)
    total_plain, total_cipher, counter = 0, len(header), 0
    cur = _read_full(src, chunk_size)
    while True:
        nxt = _read_full(src, chunk_size) if len(cur) == chunk_size else b""
        last = not nxt
        total_plain += len(cur)
        if max_size is not None and total_plain > max_size:
            raise FileTooLargeError("Ukuran file melebihi batas yang diizinkan.")
        ct = aead.encrypt(_nonce(prefix, counter), cur, header + aad + (b"\x01" if last else b"\x00"))
        dst.write(ct)
        sha.update(ct)
        total_cipher += len(ct)
        if last:
            break
        cur, counter = nxt, counter + 1
    return EncryptResult(algo, total_plain, total_cipher, sha.hexdigest())


def decrypt_stream(key, src, dst, aad=b"") -> str:
    header = _read_full(src, HEADER_SIZE)
    if len(header) != HEADER_SIZE or header[:4] != MAGIC or header[4] not in _ID_ALGOS:
        raise DecryptionError("Format file terenkripsi tidak valid.")
    algo = _ID_ALGOS[header[4]]
    prefix = header[5:13]
    chunk_size = int.from_bytes(header[13:17], "big")
    if not 1 <= chunk_size <= MAX_CHUNK:
        raise DecryptionError("Format file terenkripsi tidak valid.")
    aead = _aead(algo, key)
    enc_chunk = chunk_size + TAG_SIZE
    cur = _read_full(src, enc_chunk)
    if len(cur) < TAG_SIZE:
        raise DecryptionError("File terenkripsi terpotong.")
    counter = 0
    while True:
        nxt = _read_full(src, enc_chunk) if len(cur) == enc_chunk else b""
        last = not nxt
        try:
            pt = aead.decrypt(_nonce(prefix, counter), cur, header + aad + (b"\x01" if last else b"\x00"))
        except (InvalidTag, ValueError) as exc:
            raise DecryptionError("Dekripsi gagal: kunci salah atau file telah diubah.") from exc
        dst.write(pt)
        if last:
            break
        cur, counter = nxt, counter + 1
    return algo


# ---- helper bytes & path ---------------------------------------------------

def encrypt_bytes(key, data: bytes, **kw):
    out = io.BytesIO()
    res = encrypt_stream(key, io.BytesIO(data), out, **kw)
    return out.getvalue(), res


def decrypt_bytes(key, blob: bytes, aad=b"") -> bytes:
    out = io.BytesIO()
    decrypt_stream(key, io.BytesIO(blob), out, aad=aad)  # exception -> out tidak dikembalikan
    return out.getvalue()


def encrypt_file(key, src_path, dst_path, **kw) -> EncryptResult:
    """File sumber tidak diubah. Jika gagal, file tujuan dihapus."""
    dst_path = Path(dst_path)
    try:
        with open(src_path, "rb") as s, open(dst_path, "wb") as d:
            return encrypt_stream(key, s, d, **kw)
    except Exception:
        dst_path.unlink(missing_ok=True)
        raise


def decrypt_file(key, src_path, dst_path, aad=b"") -> str:
    """Tulis ke .part dulu; pindahkan ke tujuan hanya jika seluruh chunk terotentikasi."""
    dst_path = Path(dst_path)
    tmp = dst_path.with_name(dst_path.name + ".part")
    try:
        with open(src_path, "rb") as s, open(tmp, "wb") as d:
            algo = decrypt_stream(key, s, d, aad=aad)
        os.replace(tmp, dst_path)
        return algo
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
