"""Akun contoh untuk pengujian (JANGAN dipakai di produksi)."""
from .models.user import User
from .services import user_service as us

DEMO_PASSWORD = "komsar123"
DEMO_USERS = [
    ("admin01", "ADM1", "Administrator", "Pusat", True),
    ("andi01", "A001", "Andi", "Unit A", False),
    ("budi01", "B001", "Budi", "Unit B", False),
    ("citra01", "C001", "Citra", "Unit C", False),
    ("deni01", "D001", "Deni", "Unit D", False),
]


def seed_demo_users() -> list[str]:
    if User.query.count() > 0:
        return []
    for username, uid, name, unit, admin in DEMO_USERS:
        us.create_user(username, uid, name, unit, DEMO_PASSWORD, is_admin=admin)
    return [u[0] for u in DEMO_USERS]
