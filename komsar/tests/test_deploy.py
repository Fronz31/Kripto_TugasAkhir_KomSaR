"""Uji kesiapan deploy: /healthz, fail-fast konfigurasi production, ProxyFix."""
import time

import pytest
from flask import request
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app
from app.config import TestConfig
from app.services import user_service as us
from tests.helpers import login


def test_healthz_without_login_and_with_dongle_enforced():
    app = create_app(TestConfig)
    app.config["KOMSAR_REQUIRE_DONGLE"] = True
    r = app.test_client().get("/healthz")
    assert r.status_code == 200 and r.data == b"ok"

    with app.app_context():
        us.create_user("andi01", "Andi", "Unit A", "komsar123")
        c = login(app, "andi01")
        with c.session_transaction() as s:
            s["dongle_seen"] = time.time() - 3600               # heartbeat kedaluwarsa
        assert c.get("/healthz").status_code == 200
        with c.session_transaction() as s:
            assert "user_pk" in s                               # healthz tidak mengakhiri sesi


class ProdConfig(TestConfig):
    KOMSAR_ENV = "production"
    DATABASE_URL_SET = True


def test_production_fails_fast_when_secrets_missing():
    class Missing(ProdConfig):
        SECRET_KEY = None
        DB_MASTER_KEY_B64 = None
        DATABASE_URL_SET = False

    with pytest.raises(RuntimeError) as e:
        create_app(Missing)
    for name in ("KOMSAR_SECRET_KEY", "KOMSAR_DB_MASTER_KEY", "DATABASE_URL"):
        assert name in str(e.value)
    assert create_app(ProdConfig)                               # lengkap -> jalan


def test_proxyfix_applied_only_when_flag_set():
    assert not isinstance(create_app(TestConfig).wsgi_app, ProxyFix)

    class Proxied(TestConfig):
        KOMSAR_TRUST_PROXY = True

    app = create_app(Proxied)
    assert isinstance(app.wsgi_app, ProxyFix)
    app.add_url_rule("/_whoami", "whoami", lambda: f"{request.scheme} {request.remote_addr}")
    r = app.test_client().get("/_whoami", headers={"X-Forwarded-For": "203.0.113.7",
                                                   "X-Forwarded-Proto": "https"})
    assert r.data == b"https 203.0.113.7"
