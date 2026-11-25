"""Jumlah query halaman daftar tidak boleh naik seiring jumlah pesan (cegah N+1; tiap query = 1 round trip ke Neon)."""
import re

from sqlalchemy import event

from app.extensions import db
from app.services import user_service as us
from tests.test_dongle import login, web  # noqa: F401


def _queries(c, url):
    n = [0]
    count = lambda *a: n.__setitem__(0, n[0] + 1)  # noqa: E731
    event.listen(db.engine, "before_cursor_execute", count)
    try:
        assert c.get(url).status_code == 200
    finally:
        event.remove(db.engine, "before_cursor_execute", count)
    return n[0]


def test_list_pages_do_not_scale_with_messages(web):
    us.create_user("budi01", "Budi", "Unit B", "komsar123")
    m = web.extensions["komsar"].messaging
    admin, andi = us.get_by_username("admin01"), us.get_by_username("andi01")
    urls = ["/dashboard", "/chat", "/chat/andi01", "/decrypt", "/transfer"]

    def send(k):
        with web.test_request_context():
            for i in range(k):
                m.send_text(admin, ["andi01", "budi01"], f"halo {i}", "Rahasia123!x")
                m.send_text(andi, ["admin01"], f"balas {i}", "Rahasia123!x")

    send(2)
    c = login(web, "admin01")
    for u in urls:
        c.get(u)                                    # status sent -> delivered sekali
    before = {u: _queries(c, u) for u in urls}
    send(8)
    for u in urls:
        c.get(u)
    assert {u: _queries(c, u) for u in urls} == before


def test_list_pages_skip_large_blobs(web):
    m = web.extensions["komsar"].messaging
    with web.test_request_context():
        m.send_text(us.get_by_username("admin01"), ["andi01"], "halo", "Rahasia123!x")
    c = login(web, "andi01")
    sql = []
    grab = lambda conn, cur, stmt, *a: sql.append(stmt)  # noqa: E731
    event.listen(db.engine, "before_cursor_execute", grab)
    try:
        for u in ["/dashboard", "/chat", "/decrypt", "/files"]:
            assert c.get(u).status_code == 200
    finally:
        event.remove(db.engine, "before_cursor_execute", grab)
    bad = [s[:300] for s in sql if re.search(r"stego_png|files\.ciphertext(?!_)", s)]
    assert not bad, bad


def test_static_cache_headers(web):
    c = web.test_client()
    with web.test_request_context():
        from flask import url_for
        js, font = url_for("static", filename="app.js"), url_for("static", filename="fonts/archivo-latin-wdth-normal.woff2")
    assert "?v=" in js and "?v=" not in font
    assert "immutable" in c.get(js).headers["Cache-Control"]
    assert "immutable" in c.get(font).headers["Cache-Control"]
    assert c.get("/static/app.js").headers["Cache-Control"] == "no-cache"
    assert c.get("/login").headers["Cache-Control"] == "no-store"
