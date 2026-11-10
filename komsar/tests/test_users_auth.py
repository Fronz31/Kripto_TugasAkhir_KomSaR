import pytest

from app.auth.password import hash_password, verify_password
from app.auth.service import authenticate, current_user, login_user, logout_user
from app.errors import DuplicateUserError, UserNotFoundError, ValidationError
from app.services import user_service as us


@pytest.fixture
def users(app):
    return (us.create_user("andi01", "Andi", "Unit A", "password-andi"),
            us.create_user("budi01", "Budi", "Unit B", "password-budi"),
            us.create_user("citra01", "Citra", "Unit C", "password-citra"))


def test_password_hashed_argon2id():
    h = hash_password("rahasia123")
    assert h.startswith("$argon2id$") and "rahasia123" not in h
    assert verify_password(h, "rahasia123") and not verify_password(h, "salah")


def test_create_and_unique(users):
    assert users[0].password_hash != "password-andi"
    with pytest.raises(DuplicateUserError):
        us.create_user("ANDI01", "X", "U", "password-x")       # username (case-insensitive)
    with pytest.raises(ValidationError):
        us.create_user("x", "X", "U", "password-x")
    with pytest.raises(ValidationError):
        us.create_user("ok_user", "X", "U", "pendek")


def test_resolve_user_id_from_username(users):
    assert us.resolve_user_id("budi01") == users[1].user_id
    assert us.resolve_user_id(" Citra01 ") == users[2].user_id
    with pytest.raises(UserNotFoundError):
        us.resolve_user_id("tidakada")


def test_search_update_delete(users):
    assert [u.username for u in us.search_users("unit b")] == ["budi01"]
    assert [u.username for u in us.search_users("andi")] == ["andi01"]
    assert len(us.list_users()) == 3
    us.update_user(users[0].id, full_name="Andi Baru", is_active=False)
    with pytest.raises(UserNotFoundError):
        us.resolve_user_id("andi01")                                   # nonaktif
    us.delete_user(users[2].id)
    assert len(us.list_users()) == 2


def test_login_logout_session(app, users):
    assert authenticate("budi01", "salah") is None
    assert authenticate("tidakada", "x") is None
    user = authenticate("BUDI01", "password-budi")
    assert user and user.user_id == users[1].user_id
    with app.test_request_context():
        assert current_user() is None
        login_user(user)
        assert current_user().username == "budi01"
        logout_user()
        assert current_user() is None
    us.update_user(user.id, is_active=False)
    assert authenticate("budi01", "password-budi") is None


# ---------------- User ID acak ----------------
def test_user_id_format_and_alphabet(users):
    for u in users:
        parts = u.user_id.split("-")
        assert [len(p) for p in parts] == [4, 4, 4]
        assert set("".join(parts)) <= set(us.USER_ID_ALPHABET)
    assert not set("ILO01") & set(us.USER_ID_ALPHABET)                  # tanpa karakter ambigu


def test_user_id_unique_and_retries_on_collision(users, monkeypatch):
    assert len({u.user_id for u in users}) == 3
    taken = users[0].user_id.replace("-", "")
    seq = iter(taken + "A" * 12)                                         # percobaan pertama bentrok
    monkeypatch.setattr(us.secrets, "choice", lambda _alphabet: next(seq))
    assert us.generate_user_id() == "AAAA-AAAA-AAAA"


def test_normalize_user_id():
    for raw in ("k7qx-92mf-tr4d", "K7QX92MFTR4D", " k7qx 92mf tr4d ", "K7QX-92MFTR4D"):
        assert us.normalize_user_id(raw) == "K7QX-92MF-TR4D"
    assert us.normalize_user_id("") == ""



def test_regenerate_user_id(users):
    old = users[1].user_id
    new = us.regenerate_user_id(users[1].id).user_id
    assert new != old and us.resolve_user_id("budi01") == new
