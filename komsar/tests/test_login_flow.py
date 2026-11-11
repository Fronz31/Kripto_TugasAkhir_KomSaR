"""Fase 6: login 3 faktor (password + dongle + suara), login pertama, lockout, CLI bootstrap-admin."""
import json
import re
import time
from datetime import datetime, timedelta, timezone

import pytest

from app import cli as komsar_cli
from app import create_app
from app.auth.dongle import DongleService
from app.auth.service import authenticate
from app.config import TestConfig
from app.models.security import AuditLog
from app.models.user import User
from app.services import user_service as us
from tests.helpers import (ANDI, BUDI, CSRF, PW, SERIAL, api, b64, enroll_voice, login, login_step1, make_wav,
                           set_csrf, voice_verify)

GENERIC = "Username, password, atau dongle tidak valid"


@pytest.fixture
def web():
    app = create_app(TestConfig)
    app.config["KOMSAR_REQUIRE_DONGLE"] = True
    with app.app_context():
        us.create_user("admin01", "Administrator", "Pusat", PW, is_admin=True)
        us.create_user("andi01", "Andi", "Unit A", PW)
        yield app


def actions(target=None):
    q = AuditLog.query.order_by(AuditLog.id)
    return [r.action for r in q if target is None or r.target == target]


def reasons():
    return [r.meta["reason"] for r in AuditLog.query.filter_by(action="login_failed").order_by(AuditLog.id)]


def text(r):
    return r.get_data(as_text=True)


def sess(c):
    with c.session_transaction() as s:
        return dict(s)


def dongle():
    return (*DongleService().register("Dongle", SERIAL), SERIAL)


def enroll_samples(c, freq=ANDI):
    samples = []
    for i in range(3):
        cid = api(c, "/api/voice/challenge", {"purpose": "enroll"}).get_json()["challenge_id"]
        samples.append({"challenge_id": cid, "wav_b64": b64(make_wav(freq, seed=i))})
    return api(c, "/api/voice/enroll", {"samples": samples})


def test_login_page_desktop_only_message(web):
    page = text(web.test_client().get("/login"))
    assert "Gunakan aplikasi desktop KomSaR" in page and "login.js" in page
    assert 'name="dongle_id"' in page and 'data-require-dongle="1"' in page


def test_first_login_then_voice_login(web):
    admin = login(web, "admin01")
    page = text(admin.post("/users/add", data={"username": "deni01", "full_name": "Deni", "unit": "D",
                                               "csrf_token": CSRF}))
    temp = re.search(r'<strong class="mono">([^<]+)</strong>', page).group(1)
    deni = us.get_by_username("deni01")
    assert len(temp) == 12 and deni.must_enroll and deni.enroll_deadline is not None
    assert temp not in text(admin.get("/users/"))                       # hanya ditampilkan sekali

    c = web.test_client()
    r = login_step1(web, c, "deni01", temp, dongle())
    assert r.status_code == 302 and r.headers["Location"].endswith("/login/enroll")
    assert "user_pk" not in sess(c) and sess(c)["pending_user_id"] == deni.id
    assert "Ganti password sementara" in text(c.get("/login/enroll"))
    assert api(c, "/api/voice/challenge", {"purpose": "enroll"}).status_code == 403   # password dulu

    def change(new, confirm=None):
        set_csrf(c)
        return text(c.post("/login/enroll", data={"new": new, "confirm": confirm or new, "csrf_token": CSRF},
                           follow_redirects=True))
    assert "tidak sama" in change("passwordbaru1", "lain12345")
    assert "harus berbeda" in change(temp)
    assert "minimal 8" in change("pendek")
    assert "Daftarkan suara" in change("passwordbaru1")
    assert api(c, "/api/voice/challenge", {"purpose": "verify"}).status_code == 403
    assert enroll_samples(c).get_json() == {"ok": True}
    s = sess(c)
    assert s["user_pk"] == deni.id and "pending_user_id" not in s and s["dongle_seen"] and s["dongle_id"]
    assert c.get("/dashboard").status_code == 200                      # enforcement aktif, dongle_seen terbawa
    assert not us.get_by_username("deni01").must_enroll

    set_csrf(c)
    c.post("/logout", data={"csrf_token": CSRF})
    assert "user_pk" not in sess(c) and "dongle_id" not in sess(c)

    assert GENERIC in text(login_step1(web, c, "deni01", temp, dongle()))     # password sementara tidak berlaku
    r = login_step1(web, c, "deni01", "passwordbaru1", dongle())
    assert r.headers["Location"].endswith("/login/voice")
    assert "Rekam suara" in text(c.get("/login/voice"))
    assert c.get("/login/enroll").status_code == 302                    # tidak bisa daftar ulang sendiri
    assert api(c, "/api/voice/challenge", {"purpose": "enroll"}).status_code == 403
    assert voice_verify(c).get_json() == {"ok": True}
    assert c.get("/dashboard").status_code == 200

    assert actions("deni01") == ["user_create", "login_step1_success", "password_change", "voice_enroll",
                                 "login_success", "logout", "login_failed", "login_step1_success",
                                 "voice_verify_success", "login_success"]
    logs = " ".join(f"{r.target} {r.meta}" for r in AuditLog.query)
    assert temp not in logs and "passwordbaru1" not in logs


def test_pending_user_cannot_open_pages(web):
    enroll_voice(web, us.get_by_username("andi01"))
    c = web.test_client()
    login_step1(web, c, "andi01", PW, dongle())
    assert c.get("/dashboard").status_code == 302                       # belum login penuh
    assert "pending_user_id" not in sess(c)                             # sesi pending dibuang


def test_wrong_dongle_rejected(web):
    did, tok, _ = dongle()
    c = web.test_client()
    for bad in [(did, "x" * 44, SERIAL), (did, tok, "DEADBEEF"), ("", "", "")]:
        assert GENERIC in text(login_step1(web, c, "andi01", PW, bad))
        assert "pending_user_id" not in sess(c)
    DongleService().deactivate(did)
    assert GENERIC in text(login_step1(web, c, "andi01", PW, (did, tok, SERIAL)))
    assert reasons() == ["dongle"] * 4
    assert us.get_by_username("andi01").failed_logins == 0             # dongle salah bukan tebakan password


def test_unknown_inactive_or_locked_user_still_runs_argon2(web, monkeypatch):
    """Cegah enumerasi username lewat timing: cabang tanpa akun valid tetap memverifikasi hash dummy."""
    from app.auth import password as pw_mod
    calls = []
    monkeypatch.setattr(pw_mod, "dummy_verify", lambda p: calls.append(p) or False)
    us.create_user("nonaktif01", "Non", "X", PW)
    u = us.get_by_username("nonaktif01")
    u.is_active = False
    andi = us.get_by_username("andi01")
    andi.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    from app.extensions import db
    db.session.commit()
    c = web.test_client()
    for name in ("tidakada01", "nonaktif01", "andi01"):
        assert GENERIC in text(login_step1(web, c, name, "tebakan", dongle()))
    assert calls == ["tebakan"] * 3
    assert authenticate("tidakada01", "x") is None


def test_password_lockout_after_five(web):
    enroll_voice(web, us.get_by_username("andi01"))
    c = web.test_client()
    d = dongle()
    for _ in range(5):
        assert GENERIC in text(login_step1(web, c, "andi01", "salah-sekali", d))
    andi = us.get_by_username("andi01")
    assert andi.locked_until is not None and "account_locked" in actions("andi01")
    assert GENERIC in text(login_step1(web, c, "andi01", PW, d))        # password benar tetap ditolak
    assert reasons() == ["password"] * 5 + ["locked"]
    andi.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)  # 15 menit berlalu
    assert login_step1(web, c, "andi01", PW, d).status_code == 302


def test_voice_lockout_after_three(web):
    enroll_voice(web, us.get_by_username("andi01"))
    c = web.test_client()
    login_step1(web, c, "andi01", PW, dongle())
    for _ in range(3):
        r = voice_verify(c, BUDI)
        assert r.status_code == 403 and r.get_json() == {"ok": False}
    assert "pending_user_id" not in sess(c)
    assert actions("andi01").count("voice_verify_failed") == 3 and "account_locked" in actions("andi01")
    assert us.get_by_username("andi01").locked_until is not None
    assert GENERIC in text(login_step1(web, c, "andi01", PW, dongle()))


def test_successful_login_resets_failures(web):
    enroll_voice(web, us.get_by_username("andi01"))
    c = web.test_client()
    login_step1(web, c, "andi01", "salah-sekali", dongle())
    login_step1(web, c, "andi01", PW, dongle())
    voice_verify(c, BUDI)
    assert us.get_by_username("andi01").failed_logins == 2
    assert voice_verify(c).get_json() == {"ok": True}
    assert us.get_by_username("andi01").failed_logins == 0


def test_pending_session_expires(web):
    enroll_voice(web, us.get_by_username("andi01"))
    c = web.test_client()
    login_step1(web, c, "andi01", PW, dongle())
    with c.session_transaction() as s:
        s["pending_since"] -= 181
    assert api(c, "/api/voice/challenge", {"purpose": "verify"}).status_code == 401
    r = c.get("/login/voice")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert reasons() == ["expired"]


def test_enroll_deadline_passed(web):
    andi = us.get_by_username("andi01")
    us.require_enrollment(andi, 24)
    andi.enroll_deadline = datetime.now(timezone.utc) - timedelta(minutes=1)
    c = web.test_client()
    assert "hubungi admin" in text(login_step1(web, c, "andi01", PW, dongle()))
    assert "pending_user_id" not in sess(c) and reasons() == ["expired"]


def test_no_voice_profile_rejected(web):
    c = web.test_client()
    assert "belum memiliki profil suara" in text(login_step1(web, c, "andi01", PW, dongle()))
    assert "pending_user_id" not in sess(c)


def test_voice_endpoints_reject_non_pending(web):
    anon = web.test_client()
    set_csrf(anon)
    for url in ("/api/voice/challenge", "/api/voice/verify", "/api/voice/enroll"):
        assert api(anon, url, {"purpose": "verify"}).status_code == 401
    c = login(web, "andi01")                                            # login penuh, bukan pending
    assert api(c, "/api/voice/challenge", {"purpose": "verify"}).status_code == 401


def test_session_absolute_lifetime(web):
    c = login(web, "andi01")
    assert c.get("/dashboard").status_code == 200
    with c.session_transaction() as s:
        s["login_at"] -= 8 * 3600 + 1
    assert c.get("/dashboard").status_code == 302


def test_dev_mode_skips_voice_only_with_fake_backend_and_debug(web):
    web.config["KOMSAR_REQUIRE_DONGLE"] = False
    c = web.test_client()
    assert "belum memiliki profil suara" in text(login_step1(web, c, "andi01"))
    web.debug = True
    r = login_step1(web, c, "andi01")
    assert r.headers["Location"].endswith("/dashboard") and "user_pk" in sess(c)


def test_session_cookie_config():
    assert TestConfig.SESSION_COOKIE_HTTPONLY and TestConfig.SESSION_COOKIE_SAMESITE == "Lax"
    assert TestConfig.PERMANENT_SESSION_LIFETIME == timedelta(hours=8)
    assert TestConfig.SESSION_COOKIE_SECURE is False and TestConfig.KOMSAR_REQUIRE_DONGLE is False


# ---- CLI bootstrap-admin ----

@pytest.fixture
def drive(tmp_path, monkeypatch):
    root = str(tmp_path) + "\\"
    monkeypatch.setattr(komsar_cli.desk, "list_removable_drives", lambda: [root])
    monkeypatch.setattr(komsar_cli.desk, "volume_serial", lambda d: SERIAL)
    return root


def test_bootstrap_admin(drive, tmp_path):
    app = create_app(TestConfig)
    with app.app_context():
        runner = app.test_cli_runner()
        args = ["komsar", "bootstrap-admin", "--username", "boss01", "--full-name", "Bos", "--drive", drive,
                "--label", "Dongle 1"]
        r = runner.invoke(args=args)
        assert r.exit_code == 0, r.output
        temp = re.search(r"Password sementara \(ditampilkan sekali\): (\S+)", r.output).group(1)
        boss = User.query.filter_by(username="boss01").one()
        assert boss.is_admin and boss.must_enroll and authenticate("boss01", temp) is boss

        data = json.loads((tmp_path / "KOMSAR.DONGLE").read_text(encoding="utf-8"))
        assert data["v"] == 1 and DongleService().verify(data["dongle_id"], data["token"], SERIAL)
        assert data["token"] not in " ".join(f"{a.target} {a.meta}" for a in AuditLog.query)

        r = runner.invoke(args=["komsar", "bootstrap-admin", "--username", "boss02", "--full-name", "B",
                                "--drive", drive])
        assert r.exit_code != 0 and "Sudah ada admin" in r.output
        assert runner.invoke(args=["komsar", "bootstrap-admin", "--username", "boss02", "--full-name", "B",
                                   "--drive", "Z:\\", "--force"]).exit_code != 0     # bukan flashdisk
        r = runner.invoke(args=["komsar", "bootstrap-admin", "--force"], input="boss02\nBos Dua\n" + drive + "\n")
        assert r.exit_code == 0, r.output
        assert User.query.filter_by(username="boss02").one().is_admin


def test_bootstrap_admin_first_login(drive, tmp_path):
    app = create_app(TestConfig)
    app.config["KOMSAR_REQUIRE_DONGLE"] = True
    with app.app_context():
        r = app.test_cli_runner().invoke(args=["komsar", "bootstrap-admin", "--username", "boss01",
                                               "--full-name", "Bos", "--drive", drive])
        temp = re.search(r"\(ditampilkan sekali\): (\S+)", r.output).group(1)
        data = json.loads((tmp_path / "KOMSAR.DONGLE").read_text(encoding="utf-8"))
        c = app.test_client()
        r = login_step1(app, c, "boss01", temp, (data["dongle_id"], data["token"], SERIAL))
        assert r.headers["Location"].endswith("/login/enroll")
        set_csrf(c)
        c.post("/login/enroll", data={"new": "rahasiabos1", "confirm": "rahasiabos1", "csrf_token": CSRF})
        set_csrf(c)
        assert enroll_samples(c).get_json() == {"ok": True}
        assert c.get("/admin/audit").status_code == 200
        assert time.time() - sess(c)["dongle_seen"] < 5


# ---- Flag uji coba: admin tanpa suara, server tanpa dongle ----

def test_admin_skip_voice_flag(web):
    web.config["KOMSAR_ADMIN_SKIP_VOICE"] = True
    c = web.test_client()
    r = login_step1(web, c, "admin01", PW)                     # admin tanpa profil suara
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
    assert c.get("/dashboard").status_code == 200
    assert "admin_skip_voice" in [a.meta.get("factor") for a in AuditLog.query if a.action == "login_success"]

    c2 = web.test_client()                                      # pengguna biasa tetap wajib suara
    assert "belum memiliki profil suara" in text(login_step1(web, c2, "andi01", PW))

    web.config["KOMSAR_ADMIN_SKIP_VOICE"] = False               # flag mati: admin kembali wajib suara
    assert "belum memiliki profil suara" in text(login_step1(web, web.test_client(), "admin01", PW))


def test_admin_skip_voice_still_needs_password_and_dongle(web):
    web.config["KOMSAR_ADMIN_SKIP_VOICE"] = True
    assert GENERIC in text(login_step1(web, web.test_client(), "admin01", "salah-password"))
    assert GENERIC in text(login_step1(web, web.test_client(), "admin01", PW, ("x", "y", SERIAL)))


def test_client_config_and_heartbeat_follow_dongle_flag(web):
    web.config["KOMSAR_ADMIN_SKIP_VOICE"] = True
    c = web.test_client()
    assert c.get("/api/client-config").get_json() == {"require_dongle": True}
    login_step1(web, c, "admin01", PW)
    assert 'data-require-dongle="1"' in text(c.get("/dashboard"))

    web.config["KOMSAR_REQUIRE_DONGLE"] = False
    c = web.test_client()
    assert c.get("/api/client-config").get_json() == {"require_dongle": False}
    r = login_step1(web, c, "admin01", PW)                      # tanpa bukti dongle
    assert r.headers["Location"].endswith("/dashboard")
    assert "data-require-dongle" not in text(c.get("/dashboard"))


def test_bootstrap_admin_no_dongle():
    app = create_app(TestConfig)
    with app.app_context():
        r = app.test_cli_runner().invoke(args=["komsar", "bootstrap-admin", "--username", "boss01",
                                               "--full-name", "Bos", "--no-dongle"])
        assert r.exit_code == 0, r.output
        temp = re.search(r"\(ditampilkan sekali\): (\S+)", r.output).group(1)
        assert authenticate("boss01", temp).is_admin
        assert DongleService().list() == []
