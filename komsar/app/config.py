"""Konfigurasi aplikasi. Secret dibaca dari environment/.env, bukan dari source code."""
import base64
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


def database_url(url) -> str:
    """Kosong -> SQLite lokal. `postgres://` / `postgresql://` -> driver psycopg 3."""
    if not url:
        return f"sqlite:///{BASE_DIR / 'instance' / 'komsar.db'}"
    return re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)


class Config:
    SECRET_KEY = os.environ.get("KOMSAR_SECRET_KEY")
    DB_MASTER_KEY_B64 = os.environ.get("KOMSAR_DB_MASTER_KEY")
    SQLALCHEMY_DATABASE_URI = database_url(os.environ.get("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}   # Neon memutus koneksi idle (scale to zero)

    COVER_IMAGES_DIR = BASE_DIR / "assets" / "covers"

    MAX_FILE_BYTES = _int("MAX_FILE_MB", 10) * 1024 * 1024
    FILE_ALGO = "chacha20-poly1305"      # file & gambar biasa
    ASSET_ALGO = "aes-256-gcm"           # aset penting

    ARGON2_TIME_COST = _int("ARGON2_TIME_COST", 3)
    ARGON2_MEMORY_KIB = _int("ARGON2_MEMORY_KIB", 65536)
    ARGON2_PARALLELISM = _int("ARGON2_PARALLELISM", 2)

    # Wajib dongle saat login (langkah 1) dan selama sesi (heartbeat). Matikan (0) hanya untuk development.
    KOMSAR_REQUIRE_DONGLE = _flag("KOMSAR_REQUIRE_DONGLE", "1")
    DONGLE_HEARTBEAT_TIMEOUT = _int("DONGLE_HEARTBEAT_TIMEOUT", 60)    # detik
    DONGLE_CHECK_RATE_PER_MIN = 30                                      # per IP, /api/dongle/check

    # Suara: speechbrain (server, butuh requirements-server.txt) atau fake (khusus test)
    VOICE_BACKEND = os.environ.get("VOICE_BACKEND", "speechbrain")
    VOICE_MODEL_DIR = os.environ.get("VOICE_MODEL_DIR", str(BASE_DIR / "models" / "spkrec-ecapa-voxceleb"))
    VOICE_THRESHOLD = float(os.environ.get("VOICE_THRESHOLD", 0.25))   # kalibrasi dengan suara tim
    ENROLL_WINDOW_HOURS = _int("ENROLL_WINDOW_HOURS", 24)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _flag("KOMSAR_COOKIE_SECURE", "1")      # 0 hanya untuk development lewat http
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    TESTING = False


class TestConfig(Config):
    """Konfigurasi pengujian: kunci dibuat acak saat runtime, KDF diringankan agar cepat."""
    TESTING = True
    SECRET_KEY = secrets.token_hex(16)
    DB_MASTER_KEY_B64 = base64.b64encode(os.urandom(32)).decode()
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    ARGON2_TIME_COST = 1
    ARGON2_MEMORY_KIB = 64
    ARGON2_PARALLELISM = 1
    MAX_FILE_BYTES = 1024 * 1024
    KOMSAR_REQUIRE_DONGLE = False          # test khusus dongle menyalakannya sendiri
    VOICE_BACKEND = "fake"
    SESSION_COOKIE_SECURE = False


def load_db_master_key(config) -> bytes:
    raw = config.get("DB_MASTER_KEY_B64") if hasattr(config, "get") else config.DB_MASTER_KEY_B64
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ValueError("KOMSAR_DB_MASTER_KEY harus 32 byte (base64).")
    return key
