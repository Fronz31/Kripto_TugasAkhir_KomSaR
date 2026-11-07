"""Exception khusus KomSaR."""


class KomSaRError(Exception):
    """Base error."""


class DecryptionError(KomSaRError):
    """Dekripsi gagal (kunci salah / data rusak / dimodifikasi)."""


class StegoError(KomSaRError):
    """Kesalahan umum steganografi."""


class StegoCapacityError(StegoError):
    """Gambar cover terlalu kecil untuk payload."""


class InvalidIDError(StegoError):
    """User ID salah atau gambar stego rusak sehingga kunci tidak dapat diekstrak."""


class FileTooLargeError(KomSaRError):
    """Ukuran file melebihi batas."""


class ValidationError(KomSaRError):
    """Input tidak valid."""


class DuplicateUserError(ValidationError):
    """Username atau User ID sudah dipakai."""


class UserNotFoundError(KomSaRError):
    """Pengguna tidak ditemukan."""


class AccessDeniedError(KomSaRError):
    """Pengguna tidak berhak mengakses data ini."""


class IntegrityViolationError(KomSaRError):
    """Integritas ciphertext tidak cocok dengan hash yang tercatat."""


class StegoKeyMismatchError(DecryptionError):
    """Kunci hasil steganografi yang dimasukkan penerima tidak sesuai."""
