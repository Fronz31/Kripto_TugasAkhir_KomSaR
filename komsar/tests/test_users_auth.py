import pytest

from app.auth.biometric import BiometricAuthenticator
from app.auth.password import hash_password, verify_password
from app.auth.service import authenticate, current_user, login_user, logout_user
from app.errors import DuplicateUserError, UserNotFoundError, ValidationError
from app.services import user_service as us


@pytest.fixture
def users(app):
    return (us.create_user("andi01", "A001", "Andi", "Unit A", "password-andi"),
            us.create_user("budi01", "B001", "Budi", "Unit B", "password-budi"),
            us.create_user("citra01", "C001", "Citra", "Unit C", "password-citra"))


def test_password_hashed_argon2id():
    h = hash_password("rahasia123")
    assert h.startswith("$argon2id$") and "rahasia123" not in h
    assert verify_password(h, "rahasia123") and not verify_password(h, "salah")


def test_create_and_unique(users):
    assert users[0].password_hash != "password-andi"
    with pytest.raises(DuplicateUserError):
        us.create_user("ANDI01", "Z999", "X", "U", "password-x")       # username (case-insensitive)
    with pytest.raises(DuplicateUserError):
        us.create_user("baru01", "a001", "X", "U", "password-x")       # user_id
    with pytest.raises(ValidationError):
        us.create_user("x", "A002", "X", "U", "password-x")
    with pytest.raises(ValidationError):
        us.create_user("ok_user", "A002", "X", "U", "pendek")


def test_resolve_user_id_from_username(users):
    assert us.resolve_user_id("budi01") == "B001"
    assert us.resolve_user_id(" Citra01 ") == "C001"
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
    assert user and user.user_id == "B001"
    with app.test_request_context():
        assert current_user() is None
        login_user(user)
        assert current_user().username == "budi01"
        logout_user()
        assert current_user() is None
    us.update_user(user.id, is_active=False)
    assert authenticate("budi01", "password-budi") is None


def test_placeholders_do_not_simulate():
    assert BiometricAuthenticator.available is False
    with pytest.raises(NotImplementedError):
        BiometricAuthenticator().verify(None, None)
