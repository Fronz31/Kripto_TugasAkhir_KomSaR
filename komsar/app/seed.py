"""Akun contoh untuk pengujian (JANGAN dipakai di produksi)."""
from .models.user import User
from .services import user_service as us

DEMO_PASSWORD = "komsar123"
DEMO_USERS = [
    ("admin01", "Administrator", "Pusat", True),
    ("andi01", "Andi", "Unit A", False),
    ("budi01", "Budi", "Unit B", False),
    ("citra01", "Citra", "Unit C", False),
    ("deni01", "Deni", "Unit D", False),
]


def seed_demo_users() -> list[tuple[str, str]]:
    """Mengembalikan [(username, User ID)]; ID acak sehingga perlu dicetak agar bisa dipakai di Decryption Center."""
    if User.query.count() > 0:
        return []
    return [(u.username, u.user_id) for u in
            (us.create_user(username, name, unit, DEMO_PASSWORD, is_admin=admin)
             for username, name, unit, admin in DEMO_USERS)]
