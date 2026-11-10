"""Fase 3: status `failed`, audit log, tampilan percakapan, riwayat file."""
import pytest

from app.errors import StegoCapacityError
from app.services import messaging_service as ms
from tests.test_web import SECRET, html, login, post, uid, web  # noqa: F401  (fixture web)


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
    import io
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
    from app.services import user_service as us
    return us.get_by_username(username).id
