"""Bagian bersama embedding/extraction LSB.

Tata letak gambar (RGB, slot = satu byte warna, bit disimpan di LSB):
  [0 .. HDR_BITS)   : salt acak 16 byte, berurutan (tanpa penanda/MAGIC: tak bisa
                      dibedakan dari derau LSB alami)
  sisanya           : panjang(2) + blob terenkripsi, tersebar di posisi acak
                      yang diturunkan dari ID penerima + salt (ChaCha20 keystream)
ID salah / bukan gambar KomSaR -> posisi salah -> tag AES-GCM gagal -> InvalidIDError.
"""
import io

import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from PIL import Image

from ..errors import StegoError

SALT_SIZE = 16
HDR_BITS = SALT_SIZE * 8
LEN_BITS = 16


def load_rgb_array(source) -> tuple[np.ndarray, tuple[int, int]]:
    """source: bytes | path | file-like. Hasil: array 1D uint8 + (h, w)."""
    try:
        if isinstance(source, (bytes, bytearray)):
            source = io.BytesIO(source)
        img = Image.open(source)
        img.load()
    except Exception as exc:
        raise StegoError("File gambar tidak dapat dibaca.") from exc
    rgb = np.array(img.convert("RGB"), dtype=np.uint8)
    h, w, _ = rgb.shape
    return rgb.reshape(-1).copy(), (h, w)


def array_to_png(flat: np.ndarray, hw: tuple[int, int]) -> bytes:
    h, w = hw
    buf = io.BytesIO()
    Image.fromarray(flat.reshape(h, w, 3), "RGB").save(buf, format="PNG")  # PNG = lossless
    return buf.getvalue()


def bytes_to_bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def bits_to_bytes(bits: np.ndarray) -> bytes:
    return np.packbits(bits.astype(np.uint8)).tobytes()


def position_stream(pos_key: bytes, n_slots: int, start: int):
    """Generator indeks unik deterministik di [start, n_slots)."""
    span = n_slots - start
    enc = Cipher(algorithms.ChaCha20(pos_key, b"\x00" * 16), mode=None).encryptor()
    seen: set[int] = set()
    while True:
        buf = enc.update(b"\x00" * 4096)
        for i in range(0, len(buf), 4):
            idx = start + int.from_bytes(buf[i:i + 4], "big") % span
            if idx not in seen:
                seen.add(idx)
                yield idx


def max_body_bits(n_slots: int) -> int:
    """Batas pemakaian (1/4 slot tersisa) agar sampling posisi tetap efisien."""
    return (n_slots - HDR_BITS) // 4
