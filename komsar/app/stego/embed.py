"""Embedding kunci rahasia ke gambar (LSB) yang dikunci dengan ID penerima."""
import os
from itertools import islice

import numpy as np

from ..crypto import aes_gcm
from ..crypto.kdf import derive_id_master, hkdf
from ..errors import StegoCapacityError, ValidationError
from . import _common as c


def embed_key(cover, recipient_id: str, secret) -> bytes:
    """Kembalikan bytes PNG stego berisi `secret`, hanya dapat diekstrak dengan `recipient_id`."""
    secret_b = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
    if not 1 <= len(secret_b) <= 1024:
        raise ValidationError("Kunci rahasia harus 1-1024 byte.")
    if not recipient_id:
        raise ValidationError("ID penerima wajib diisi.")

    flat, hw = c.load_rgb_array(cover)
    salt = os.urandom(c.SALT_SIZE)
    header = c.MAGIC + bytes([c.VERSION]) + salt
    master = derive_id_master(recipient_id, salt)
    blob = aes_gcm.encrypt(hkdf(master, b"stego:enc"), secret_b, aad=header)
    body = len(blob).to_bytes(2, "big") + blob
    body_bits = c.bytes_to_bits(body)

    if len(body_bits) > c.max_body_bits(flat.size):
        raise StegoCapacityError("Gambar cover terlalu kecil untuk menyimpan kunci.")

    hdr_bits = c.bytes_to_bits(header)
    flat[:c.HDR_BITS] = (flat[:c.HDR_BITS] & 0xFE) | hdr_bits

    pos = np.fromiter(
        islice(c.position_stream(hkdf(master, b"stego:pos"), flat.size, c.HDR_BITS), len(body_bits)),
        dtype=np.int64, count=len(body_bits),
    )
    flat[pos] = (flat[pos] & 0xFE) | body_bits
    return c.array_to_png(flat, hw)
