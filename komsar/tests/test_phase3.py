"""Fase 3: status `failed`, audit log, tampilan percakapan, riwayat file."""
import io
import os

import pytest

from app.errors import StegoCapacityError
from app.models.records import FileRecord
from app.models.security import AuditLog
from app.services import messaging_service as ms
from app.services import user_service as us
from app.services.audit_service import audit
from tests.helpers import corrupt
from tests.test_web import (PW, SECRET, decrypt, delivery_id, html, login, post, token, uid, upload,  # noqa: F401
                            web)


def _fail_embed_for(monkeypatch, *usernames):
    bad = {uid(u) for u in usernames}
    real = ms.embed_key

    def fake(cover, rid, secret):
        if rid in bad:
            raise StegoCapacityError("simulasi gagal")
        return real(cover, rid, secret)
    monkeypatch.setattr(ms, "embed_key", fake)


# ---------- status failed ----------
def test_one_recipient_failure_marks_failed_others_succeed(web, monkeypatch):
    _fail_embed_for(monkeypatch, "citra01")
    andi = login(web, "andi01")
    page = html(post(andi, "/chat/send", {"recipients": "budi01, citra01", "message": "Halo", "secret": SECRET}))
    assert "1 penerima gagal" in page and "Gagal" in page and "StegoCapacityError" in page
    repo = web.extensions["komsar"].repo
    by_user = {d.recipient_pk: d for d in repo.inbox(us_pk("budi01")) + repo.inbox(us_pk("citra01"))}
    assert by_user[us_pk("budi01")].status == "sent" and by_user[us_pk("budi01")].stego_png
    failed = by_user[us_pk("citra01")]
    assert failed.status == "failed" and failed.error and not failed.stego_png
    assert "Belum ada pesan masuk" in html(login(web, "citra01").get("/chat"))   # paket gagal tidak tampil


def test_file_failure_shown_on_transfer_page(web, monkeypatch):
    _fail_embed_for(monkeypatch, "citra01")
    andi = login(web, "andi01")
    page = html(post(andi, "/transfer/send", {"recipients": "budi01,citra01", "secret": SECRET, "kind": "file",
                                              "file": (io.BytesIO(b"isi"), "a.txt")},
                     content_type="multipart/form-data"))
    assert "File terkirim" in page and "Gagal" in page


def test_all_recipients_fail_raises(web, monkeypatch):
    _fail_embed_for(monkeypatch, "budi01", "citra01")
    andi = login(web, "andi01")
    page = html(post(andi, "/chat/send", {"recipients": "budi01,citra01", "message": "Halo", "secret": SECRET}))
    assert "Belum ada pengiriman" in page
    assert not web.extensions["komsar"].repo.sent_messages(us_pk("andi01"))


def us_pk(username):
    return us.get_by_username(username).id


# ---------- audit log ----------
def _logs(action=None):
    q = AuditLog.query.order_by(AuditLog.id)
    return (q.filter_by(action=action) if action else q).all()


def _all_log_text():
    return " ".join(f"{r.action} {r.target} {r.meta} {r.ip} {r.dongle_id}" for r in _logs())


def test_audit_login_logout_send_decrypt_without_sensitive_data(web):
    login(web, "budi01", password="salah-sekali")
    andi = login(web, "andi01")
    post(andi, "/chat/send", {"recipients": "budi01", "message": "Rahasia negara", "secret": SECRET})
    budi = login(web, "budi01")
    did = delivery_id(web, "budi01")
    post(budi, "/decrypt", {"delivery_id": did, "user_id": uid("citra01")})           # ID salah
    assert "Berhasil didekripsi" in decrypt(budi, did, uid("budi01"))
    post(budi, "/logout")

    failed = _logs("login_failed")[0]
    assert failed.target == "budi01" and failed.user_id is None and failed.ip == "127.0.0.1"
    assert _logs("login_success")[0].user.username == "andi01"
    sent = _logs("send_text")[0]
    assert sent.user.username == "andi01" and sent.meta == {"kind": "text", "recipients": 1, "failed": 0}
    assert _logs("decrypt_failed")[0].meta["reason"] == "InvalidIDError"
    assert _logs("decrypt_success")[0].target == did
    assert _logs("logout")[0].user.username == "budi01"
    text = _all_log_text()
    for forbidden in ("Rahasia negara", SECRET, "salah-sekali", PW, uid("budi01"), uid("citra01")):
        assert forbidden not in text


def test_audit_integrity_failure(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    upload(andi, ["budi01"], "kontrak.pdf", os.urandom(3000), "asset")
    assert _logs("send_asset")[0].meta["kind"] == "asset"
    corrupt(FileRecord.query.one(), 40)
    decrypt(budi, delivery_id(web, "budi01"), uid("budi01"))
    assert _logs("integrity_failed")[0].meta["reason"] == "IntegrityViolationError"


def test_audit_admin_actions_and_user_delete_keeps_logs(web):
    admin = login(web, "admin01")
    post(admin, "/users/add", {"username": "dodi01", "full_name": "Dodi", "unit": "U", "password": PW})
    dodi = us.get_by_username("dodi01")
    pk, first_id = dodi.id, dodi.user_id
    login(web, "dodi01")                                       # baris audit milik dodi sendiri
    post(admin, f"/users/{pk}/edit", {"full_name": "Dodi B", "unit": "U", "is_active": "on"})
    post(admin, f"/users/{pk}/regenerate-id")
    regen_id = us.get_by_username("dodi01").user_id
    post(admin, f"/users/{pk}/delete")
    assert [r.action for r in _logs() if r.target == "dodi01"] == [
        "user_create", "login_success", "user_update", "user_regenerate_id", "user_delete"]
    own = AuditLog.query.filter_by(action="login_success", target="dodi01").one()
    assert own.user_id is None                                 # FK di-NULL-kan, user tetap terhapus
    assert first_id not in _all_log_text() and regen_id not in _all_log_text()


def test_audit_dongle_register_and_deactivate(web):
    admin = login(web, "admin01")
    r = admin.post("/api/dongle/register", json={"label": "FD", "volume_serial": "1A2B3C4D"},
                   headers={"X-CSRF-Token": token(admin)})
    did, tok = r.get_json()["dongle_id"], r.get_json()["token"]
    post(admin, f"/admin/dongles/{did}/deactivate")
    assert _logs("dongle_register")[0].target == did and _logs("dongle_deactivate")[0].target == did
    assert tok not in _all_log_text()


def test_audit_rejects_sensitive_meta(web):
    with pytest.raises(ValueError):
        audit("send_text", secret="K123")


def test_audit_page_admin_only_filter_and_pagination(web):
    budi = us.get_by_username("budi01")
    for i in range(55):
        audit("send_text", target=f"m{i}", user=budi)
    audit("logout", target="x", user=us.get_by_username("citra01"))
    assert login(web, "budi01").get("/admin/audit").status_code == 403
    admin = login(web, "admin01")
    page = html(admin.get("/admin/audit"))
    assert "Audit Log" in page and "dari 2" in page and "Berikutnya" in page
    assert page.index(">x<") < page.index(">m54<")                 # terbaru di atas
    filtered = html(admin.get("/admin/audit?username=citra01"))
    assert ">x<" in filtered and ">m1<" not in filtered
    by_action = html(admin.get("/admin/audit?action=send_text&page=2"))
    assert ">m0<" in by_action and ">x<" not in by_action


# ---------- percakapan & riwayat file ----------
def test_conversation_two_way_ciphertext_only(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    post(andi, "/chat/send", {"recipients": "budi01", "message": "Pesan satu", "secret": SECRET})
    post(budi, "/chat/send", {"recipients": "andi01", "message": "Balasan dua", "secret": SECRET})
    post(andi, "/chat/send", {"recipients": "citra01", "message": "Untuk citra", "secret": SECRET})
    page = html(andi.get("/chat/budi01"))
    assert "Percakapan dengan Budi" in page and page.count('class="msg') == 2
    assert "Pesan satu" not in page and "Balasan dua" not in page and "Terenkripsi" in page
    assert page.index("Anda → budi01") < page.index("dari budi01")                # urut waktu
    did = delivery_id(web, "andi01")
    assert f"/decrypt?d={did}" in page and page.count("Buka</a>") == 1           # Buka hanya untuk pesan masuk
    assert "/chat/budi01" in html(andi.get("/chat")) and "/chat/andi01" in html(budi.get("/chat"))
    assert "/chat/budi01" in html(andi.get("/users/"))


def test_conversation_requires_login_and_unknown_user(web):
    assert web.test_client().get("/chat/budi01").status_code == 302
    andi = login(web, "andi01")
    assert andi.get("/chat/tidakada").status_code == 404
    assert andi.get("/chat/andi01").status_code == 302


def test_conversation_is_only_own(web):
    andi, citra = login(web, "andi01"), login(web, "citra01")
    post(andi, "/chat/send", {"recipients": "budi01", "message": "Halo", "secret": SECRET})
    assert "Belum ada pesan" in html(citra.get("/chat/budi01"))                  # citra tidak melihat andi<->budi


def test_files_history_sent_and_received(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    upload(andi, ["budi01"], "laporan.pdf", b"%PDF-1.7 isi", "file")
    upload(budi, ["citra01"], "kontrak.pdf", os.urandom(500), "asset")
    post(andi, "/chat/send", {"recipients": "budi01", "message": "teks saja", "secret": SECRET})
    page = html(budi.get("/files"))
    assert "laporan.pdf" in page and "kontrak.pdf" in page and "Diterima" in page and "Terkirim" in page
    assert "Aset Penting" in page and page.count("Buka</a>") == 1 and "teks saja" not in page
    assert "Riwayat File" in page
    a = html(andi.get("/files"))
    assert "laporan.pdf" in a and "kontrak.pdf" not in a
    assert "Belum ada file" in html(login(web, "admin01").get("/files"))


def test_blockchain_records_admin_only(web):
    assert login(web, "budi01").get("/admin/chain").status_code == 403
    assert login(web, "admin01").get("/admin/chain").status_code == 200
