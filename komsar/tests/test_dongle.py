"""Uji dongle flashdisk: service, endpoint /api/dongle/*, penegakan heartbeat, halaman admin."""
import base64
import time

import pytest

from app import create_app
from app.auth.dongle import DongleService
from app.config import TestConfig
from app.extensions import db
from app.models.security import Dongle
from app.services import user_service as us
from tests.helpers import login as full_login

SERIAL = "1A2B3C4D"
PW = "komsar123"


@pytest.fixture
def web():
    app = create_app(TestConfig)
    with app.app_context():
        us.create_user("admin01", "Administrator", "Pusat", PW, is_admin=True)
        us.create_user("andi01", "Andi", "Unit A", PW)
        yield app


def login(app, username):
    c = full_login(app, username)
    with c.session_transaction() as s:
        assert "user_pk" in s
    return c


def api(c, url, body, csrf=True):
    headers = {"X-CSRF-Token": "tok-test"} if csrf else {}
    return c.post(url, json=body, headers=headers)


def proof(did, tok, serial=SERIAL):
    return {"dongle_id": did, "token": tok, "volume_serial": serial}


# ---- service ----

def test_register_and_verify(web):
    svc = DongleService()
    admin = us.get_by_username("admin01")
    did, tok = svc.register("Flashdisk A", "1a2b3c4d", admin)
    assert len(base64.b64decode(tok)) == 32
    d = db.session.get(Dongle, did)
    assert d.token_hash != tok and len(d.token_hash) == 64 and d.volume_serial == SERIAL
    assert d.registered_by == admin.id and d.last_used_at is None
    assert svc.verify(did, tok, SERIAL) is d and d.last_used_at is not None
    assert svc.list() == [d]


def test_verify_rejects(web):
    svc = DongleService()
    did, tok = svc.register("A", SERIAL)
    other = base64.b64encode(b"x" * 32).decode()
    assert svc.verify(did, other, SERIAL) is None
    assert svc.verify(did, tok, "DEADBEEF") is None
    assert svc.verify("tidak-ada", tok, SERIAL) is None
    assert svc.verify(did, None, SERIAL) is None
    svc.deactivate(did)
    assert svc.verify(did, tok, SERIAL) is None


@pytest.mark.parametrize("label,serial", [("", SERIAL), ("A", "1234"), ("A", "XYZ12345")])
def test_register_validation(web, label, serial):
    with pytest.raises(ValueError):
        DongleService().register(label, serial)


def test_delete_user_who_registered_dongle(web):
    u = us.create_user("deni01", "Deni", "Unit D", PW, is_admin=True)
    did, _ = DongleService().register("A", SERIAL, u)
    us.delete_user(u.id)
    db.session.expire_all()
    assert db.session.get(Dongle, did).registered_by is None


# ---- endpoint ----

def test_check_needs_no_login(web):
    did, tok = DongleService().register("A", SERIAL)
    c = web.test_client()
    assert c.post("/api/dongle/check", json=proof(did, tok)).get_json() == {"ok": True}
    r = c.post("/api/dongle/check", json=proof(did, tok, "DEADBEEF"))
    assert r.status_code == 403 and r.get_json() == {"ok": False}
    assert c.post("/api/dongle/check", data="bukan json").get_json() == {"ok": False}
    assert c.post("/api/dongle/check", json=[1, 2]).get_json() == {"ok": False}


def test_check_rate_limited(web):
    c = web.test_client()
    codes = [c.post("/api/dongle/check", json={}).status_code for _ in range(31)]
    assert codes[:30] == [403] * 30 and codes[30] == 429


def test_register_admin_only(web):
    body = {"label": "Flashdisk A", "volume_serial": SERIAL}
    assert web.test_client().post("/api/dongle/register", json=body).status_code in (400, 401)
    assert api(login(web, "andi01"), "/api/dongle/register", body).status_code == 403
    admin = login(web, "admin01")
    assert api(admin, "/api/dongle/register", body, csrf=False).status_code == 400
    r = api(admin, "/api/dongle/register", body)
    data = r.get_json()
    assert r.status_code == 200 and DongleService().verify(data["dongle_id"], data["token"], SERIAL)
    assert api(admin, "/api/dongle/register", {"label": "", "volume_serial": SERIAL}).status_code == 400


def test_heartbeat_sets_session(web):
    did, tok = DongleService().register("A", SERIAL)
    c = login(web, "andi01")
    assert api(c, "/api/dongle/heartbeat", proof(did, "salah")).get_json() == {"ok": False}
    assert api(c, "/api/dongle/heartbeat", proof(did, tok)).get_json() == {"ok": True}
    with c.session_transaction() as s:
        assert s["dongle_id"] == did and time.time() - s["dongle_seen"] < 5


# ---- penegakan ----

def test_enforcement_off_by_default(web):
    assert web.config["KOMSAR_REQUIRE_DONGLE"] is False
    assert login(web, "andi01").get("/dashboard").status_code == 200


def test_enforcement_on(web):
    web.config["KOMSAR_REQUIRE_DONGLE"] = True
    did, tok = DongleService().register("A", SERIAL)
    c = login(web, "andi01")                                    # login dengan dongle -> dongle_seen terisi
    assert c.get("/dashboard").status_code == 200
    with c.session_transaction() as s:
        s["dongle_seen"] = time.time() - 61
    r = c.get("/dashboard")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    with c.session_transaction() as s:
        assert "user_pk" not in s                               # sesi diakhiri

    c = login(web, "andi01")
    with c.session_transaction() as s:
        s["dongle_seen"] = time.time() - 61
    assert c.get("/static/app.js").status_code == 200           # static dikecualikan
    assert api(c, "/api/dongle/heartbeat", proof(did, tok)).get_json() == {"ok": True}
    assert c.get("/dashboard").status_code == 200

    c = login(web, "admin01")
    with c.session_transaction() as s:
        del s["dongle_seen"]
    assert api(c, "/api/dongle/register", {"label": "B", "volume_serial": SERIAL}).status_code == 401


# ---- halaman admin ----

def test_admin_page_and_deactivate(web):
    did, tok = DongleService().register("Flashdisk Rahasia", SERIAL)
    assert login(web, "andi01").get("/admin/dongles").status_code == 403
    c = login(web, "admin01")
    page = c.get("/admin/dongles").get_data(as_text=True)
    assert "Flashdisk Rahasia" in page and SERIAL in page and "dongles.js" in page
    c.post(f"/admin/dongles/{did}/deactivate", data={"csrf_token": "tok-test"})
    assert DongleService().verify(did, tok, SERIAL) is None
