"""Validasi input pengiriman: kunci rahasia, nama file, ekstensi, ukuran."""
import mimetypes
import os
import re

from ..errors import ValidationError

DOCUMENT_EXT = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "rtf", "odt", "ods", "odp", "zip"}
IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}


def validate_secret(secret) -> bytes:
    if secret is None:
        raise ValidationError("Kunci rahasia wajib diisi.")
    data = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
    if len(data) < 4:
        raise ValidationError("Kunci rahasia minimal 4 karakter.")
    if len(data) > 1024:
        raise ValidationError("Kunci rahasia maksimal 1024 byte.")
    return data


def validate_text(text: str) -> str:
    if text is None or not text.strip():
        raise ValidationError("Pesan tidak boleh kosong.")
    if len(text.encode("utf-8")) > 64 * 1024:
        raise ValidationError("Pesan terlalu panjang (maks 64 KB).")
    return text


def safe_filename(name: str) -> str:
    """Ambil nama dasar saja (cegah path traversal), pertahankan ekstensi."""
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    base = re.sub(r"[^\w.\- ()]", "_", base)
    if not base or base in {".", ".."} or base.startswith("."):
        raise ValidationError("Nama file tidak valid.")
    return base[:150]


def extension_of(filename: str) -> str:
    return os.path.splitext(filename)[1].lower().lstrip(".")


def validate_extension(filename: str, allowed: set[str]) -> str:
    ext = extension_of(filename)
    if ext not in allowed:
        raise ValidationError(f"Jenis file .{ext or '?'} tidak diizinkan.")
    return ext


def guess_mime(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
