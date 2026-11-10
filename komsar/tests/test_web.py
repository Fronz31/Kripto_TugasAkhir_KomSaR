"""Uji antarmuka web Flask end-to-end (login, chat, file, aset, dekripsi, admin)."""
import io
import os
import re

import pytest
from PIL import Image

from app import create_app
from app.config import TestConfig
from app.models.records import DeliveryRecord, FileRecord
from app.services import user_service as us
from tests.helpers import corrupt

PW = "komsar123"
SECRET = "K123"


@pytest.fixture
def web():
    app = create_app(TestConfig)
    with app.app_context():
        us.create_user("admin01", "ADM1", "Administrator", "Pusat", PW, is_admin=True)
        for n in ("andi", "budi", "citra"):
            us.create_user(f"{n}01", f"{n[0].upper()}001", n.title(), f"Unit {n[0].upper()}", PW)
        yield app


def token(client):
    with client.session_transaction() as s:
        s.setdefault("csrf_token", "tok-test")
        return s["csrf_token"]


def post(client, url, data=None, **kw):
    data = dict(data or {}); data["csrf_token"] = token(client)
    return client.post(url, data=data, follow_redirects=True, **kw)


def login(app, username, password=PW):
    c = app.test_client()
    post(c, "/login", {"username": username, "password": password})
    return c


def html(r):
    return r.get_data(as_text=True)


def delivery_id(app, username):
    repo = app.extensions["komsar"].repo
    pk = us.get_by_username(username).id
    return repo.inbox(pk)[-1].id


def decrypt(client, did, rid, key=SECRET):
    """Alur dua langkah: ekstrak kunci dengan ID, lalu ketik ulang kunci."""
    step1 = html(post(client, "/decrypt", {"action": "extract", "delivery_id": did, "user_id": rid}))
    m = re.search(r'name="token" value="([^"]+)"', step1)
    assert m, "langkah 2 tidak muncul"
    return html(post(client, "/decrypt", {"action": "decrypt", "token": m.group(1), "secret_key": key}))


def png_bytes():
    buf = io.BytesIO(); Image.effect_noise((48, 48), 30).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


# ---------- akses & login ----------
def test_requires_login_and_login_flow(web):
    c = web.test_client()
    r = c.get("/dashboard")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert "salah" in html(post(c, "/login", {"username": "budi01", "password": "x"}))
    r = post(c, "/login", {"username": "budi01", "password": PW})
    assert "Halo, Budi" in html(r)


def test_csrf_enforced_and_security_headers(web):
    c = login(web, "andi01")
    r = c.post("/chat/send", data={"message": "x"})                   # tanpa token
    assert r.status_code == 400
    r = c.get("/dashboard")
    assert r.headers["X-Frame-Options"] == "DENY" and "default-src 'self'" in r.headers["Content-Security-Policy"]


# ---------- pesan & dekripsi ----------
def send_text(c, to, text="Pergerakan dimulai 05.00", important=False):
    data = {"recipients": ", ".join(to), "message": text, "secret": SECRET}
    if important:
        data["important"] = "on"
    return post(c, "/chat/send", data)


def test_text_flow_encrypted_until_decrypted(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    assert "berhasil dikirim" in html(send_text(andi, ["budi01", "citra01"]))
    page = html(budi.get("/chat"))
    assert "Terenkripsi" in page and "Pergerakan dimulai" not in page and "Pesan Biasa" in page
    did = delivery_id(web, "budi01")

    bad = html(post(budi, "/decrypt", {"delivery_id": did, "user_id": "C001"}))
    assert "tidak sesuai" in bad and "Pergerakan dimulai" not in bad          # tanpa plaintext parsial

    ok = decrypt(budi, did, "b001")
    assert "Berhasil didekripsi" in ok and "Pergerakan dimulai 05.00" in ok
    assert "Pergerakan dimulai 05.00" in html(budi.get("/chat"))               # isi tidak hilang di chatbox
    assert "Sudah dibuka" in html(budi.get("/chat"))


def test_important_badge_and_sender_never_sees_plaintext(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    send_text(andi, ["budi01"], important=True)
    assert "Pesan Penting" in html(budi.get("/chat"))
    page = html(andi.get("/chat"))
    assert "Pesan Penting" in page and "Pergerakan dimulai" not in page


def test_other_user_cannot_open_or_download(web):
    andi, budi, citra = login(web, "andi01"), login(web, "budi01"), login(web, "citra01")
    send_text(andi, ["budi01"])
    did = delivery_id(web, "budi01")
    r = html(post(citra, "/decrypt", {"delivery_id": did, "user_id": "B001"}))
    assert "tidak berhak" in r and "Pergerakan dimulai" not in r
    assert citra.get(f"/delivery/{did}/stego").status_code == 404
    assert andi.get(f"/delivery/{did}/cipher").status_code == 404
    st = budi.get(f"/delivery/{did}/stego")
    assert st.status_code == 200 and st.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_xss_escaped(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    send_text(andi, ["budi01"], text="<script>alert(1)</script>")
    out = decrypt(budi, delivery_id(web, "budi01"), "B001")
    assert "<script>alert(1)</script>" not in out and "&lt;script&gt;" in out


def test_logout_clears_decrypted_cache(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    send_text(andi, ["budi01"])
    decrypt(budi, delivery_id(web, "budi01"), "B001")
    post(budi, "/logout")
    budi2 = login(web, "budi01")
    assert "Pergerakan dimulai" not in html(budi2.get("/chat"))


# ---------- file, gambar, aset ----------
def upload(c, to, name, data, kind, secret=SECRET):
    return post(c, "/transfer/send", {"recipients": ", ".join(to), "kind": kind, "secret": secret,
                                      "file": (io.BytesIO(data), name)}, content_type="multipart/form-data")


def test_file_upload_download_identical(web):
    andi, budi, citra = login(web, "andi01"), login(web, "budi01"), login(web, "citra01")
    data = b"%PDF-1.7 " + os.urandom(5000)
    assert "berhasil dienkripsi" in html(upload(andi, ["budi01"], "laporan.pdf", data, "file"))
    out = decrypt(budi, delivery_id(web, "budi01"), "B001")
    assert "laporan.pdf" in out
    tok = out.split("/decrypt/file/")[1].split('"')[0]
    r = budi.get(f"/decrypt/file/{tok}")
    assert r.data == data and "attachment" in r.headers["Content-Disposition"]
    assert citra.get(f"/decrypt/file/{tok}").status_code == 404


def test_image_no_preview_before_decrypt_and_preview_after(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    png = png_bytes()
    upload(andi, ["budi01"], "foto.png", png, "image")
    assert "/decrypt/file/" not in html(budi.get("/chat")) and "/decrypt/file/" not in html(budi.get("/decrypt"))
    out = decrypt(budi, delivery_id(web, "budi01"), "B001")
    assert "/decrypt/file/" in out
    tok = out.split("/decrypt/file/")[1].split("?")[0].split('"')[0]
    assert budi.get(f"/decrypt/file/{tok}?inline=1").data == png


def test_upload_validation_messages(web):
    andi = login(web, "andi01")
    assert "tidak diizinkan" in html(upload(andi, ["budi01"], "virus.exe", b"MZ", "file"))
    assert "Pilih minimal satu penerima" in html(upload(andi, [], "a.pdf", b"%PDF", "file"))
    assert "minimal 4" in html(upload(andi, ["budi01"], "a.pdf", b"%PDF", "file", secret="ab"))


def test_asset_list_integrity_and_tamper(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    upload(andi, ["budi01"], "kontrak.pdf", os.urandom(3000), "asset")
    page = html(budi.get("/assets"))
    assert "kontrak.pdf" in page and "Terverifikasi" in page
    assert "previous_hash" not in page and "Blockchain Records" not in page      # blok mentah tidak tampil ke user
    corrupt(FileRecord.query.one(), 40)
    assert "Bermasalah" in html(budi.get("/assets"))
    out = decrypt(budi, delivery_id(web, "budi01"), "B001")
    assert "Integritas aset gagal" in out and "Berhasil didekripsi" not in out


# ---------- admin & pengguna ----------
def test_admin_chain_page_access(web):
    admin, andi, budi = login(web, "admin01"), login(web, "andi01"), login(web, "budi01")
    upload(andi, ["budi01"], "kontrak.pdf", os.urandom(1000), "asset")
    page = html(admin.get("/admin/chain"))
    assert "Rantai valid" in page and "kontrak.pdf" in page and "Blockchain Records" in page
    assert budi.get("/admin/chain").status_code == 403


def test_user_management_permissions(web):
    admin, budi = login(web, "admin01"), login(web, "budi01")
    new = {"username": "deni01", "user_id": "D001", "full_name": "Deni", "unit": "Unit D", "password": PW}
    assert budi.post("/users/add", data={**new, "csrf_token": token(budi)}).status_code == 403
    assert "berhasil ditambahkan" in html(post(admin, "/users/add", new))
    assert "sudah dipakai" in html(post(admin, "/users/add", new))
    assert "deni01" in html(budi.get("/users/?q=unit d"))                     # user biasa boleh melihat/mencari
    assert "Tambah pengguna" not in html(budi.get("/users/"))


def test_cannot_delete_user_with_history_or_self(web):
    admin, andi = login(web, "admin01"), login(web, "andi01")
    send_text(andi, ["budi01"])
    budi_pk = us.get_by_username("budi01").id
    assert "riwayat" in html(post(admin, f"/users/{budi_pk}/delete"))
    admin_pk = us.get_by_username("admin01").id
    assert "akun sendiri" in html(post(admin, f"/users/{admin_pk}/delete"))
    citra_pk = us.get_by_username("citra01").id
    assert "dihapus" in html(post(admin, f"/users/{citra_pk}/delete"))


def test_profile_password_change(web):
    c = login(web, "budi01")
    assert "salah" in html(post(c, "/profile", {"current": "x", "new": "passwordbaru1", "confirm": "passwordbaru1"}))
    assert "berhasil diubah" in html(post(c, "/profile", {"current": PW, "new": "passwordbaru1", "confirm": "passwordbaru1"}))
    assert login(web, "budi01", "passwordbaru1").get("/dashboard").status_code == 200


# ---------- revisi: input username, alur dekripsi dua langkah, ID disembunyikan ----------
def test_recipients_are_typed_usernames(web):
    andi = login(web, "andi01")
    page = html(andi.get("/chat"))
    assert 'type="text" name="recipients"' in page and 'type="checkbox" name="recipients"' not in page
    assert "berhasil dikirim" in html(post(andi, "/chat/send", {"recipients": "budi01, citra01;BUDI01",
                                                               "message": "halo", "secret": SECRET}))
    assert DeliveryRecord.query.count() == 2                  # duplikat diabaikan
    assert "tidak ditemukan" in html(post(andi, "/chat/send", {"recipients": "budi01, hantu99",
                                                              "message": "halo", "secret": SECRET}))


def test_step1_shows_stego_image_and_extracted_key(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    send_text(andi, ["budi01"])
    did = delivery_id(web, "budi01")
    assert f"/delivery/{did}/stego?inline=1" in html(budi.get(f"/decrypt?d={did}"))        # gambar stego tampil
    r = budi.get(f"/delivery/{did}/stego?inline=1")
    assert r.status_code == 200 and "attachment" not in r.headers.get("Content-Disposition", "")
    page = html(post(budi, "/decrypt", {"action": "extract", "delivery_id": did, "user_id": "B001"}))
    assert "<code>K123</code>" in page and "Langkah 2" in page                          # kunci hasil stego ditampilkan
    assert "Pergerakan dimulai" not in page                                            # belum didekripsi


def test_step1_wrong_id_shows_no_key(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    send_text(andi, ["budi01"])
    page = html(post(budi, "/decrypt", {"action": "extract", "delivery_id": delivery_id(web, "budi01"),
                                        "user_id": "SALAH"}))
    assert "tidak sesuai" in page and "K123" not in page and "Langkah 2" not in page


def test_step2_wrong_key_error_retry_and_lockout(web):
    andi, budi = login(web, "andi01"), login(web, "budi01")
    send_text(andi, ["budi01"])
    did = delivery_id(web, "budi01")
    step1 = html(post(budi, "/decrypt", {"action": "extract", "delivery_id": did, "user_id": "B001"}))
    tok = re.search(r'name="token" value="([^"]+)"', step1).group(1)
    wrong = html(post(budi, "/decrypt", {"action": "decrypt", "token": tok, "secret_key": "SALAH"}))
    assert "tidak sesuai" in wrong and "Pergerakan dimulai" not in wrong and "<code>K123</code>" in wrong  # bisa mencoba lagi
    assert "wajib diisi" in html(post(budi, "/decrypt", {"action": "decrypt", "token": tok, "secret_key": ""}))
    ok = html(post(budi, "/decrypt", {"action": "decrypt", "token": tok, "secret_key": "K123"}))
    assert "Berhasil didekripsi" in ok and "Pergerakan dimulai 05.00" in ok
    assert "Sesi dekripsi sudah berakhir" in html(post(budi, "/decrypt", {"action": "decrypt", "token": tok, "secret_key": "K123"}))

    step1 = html(post(budi, "/decrypt", {"action": "extract", "delivery_id": did, "user_id": "B001"}))
    tok = re.search(r'name="token" value="([^"]+)"', step1).group(1)
    for _ in range(5):
        out = html(post(budi, "/decrypt", {"action": "decrypt", "token": tok, "secret_key": "x"}))
    assert "Terlalu banyak kesalahan" in out
    assert "Sesi dekripsi sudah berakhir" in html(post(budi, "/decrypt", {"action": "decrypt", "token": tok, "secret_key": "K123"}))


def test_step2_token_not_usable_by_other_user(web):
    andi, budi, citra = login(web, "andi01"), login(web, "budi01"), login(web, "citra01")
    send_text(andi, ["budi01"])
    step1 = html(post(budi, "/decrypt", {"action": "extract", "delivery_id": delivery_id(web, "budi01"), "user_id": "B001"}))
    tok = re.search(r'name="token" value="([^"]+)"', step1).group(1)
    out = html(post(citra, "/decrypt", {"action": "decrypt", "token": tok, "secret_key": "K123"}))
    assert "Sesi dekripsi sudah berakhir" in out and "Pergerakan dimulai" not in out


def test_own_user_id_hidden_after_login(web):
    budi = login(web, "budi01")
    for url in ("/dashboard", "/profile", "/chat", "/transfer", "/assets", "/decrypt", "/users/"):
        assert "B001" not in html(budi.get(url)), url


def test_users_page_ids_only_for_admin(web):
    admin, budi = login(web, "admin01"), login(web, "budi01")
    page = html(budi.get("/users/"))
    assert "andi01" in page and "A001" not in page and "ADM1" not in page and "User ID" not in page
    found = html(budi.get("/users/?q=A001"))                                             # ID tidak bisa dipakai mencari
    assert "andi01" not in found and "Tidak ada pengguna" in found
    apage = html(admin.get("/users/"))
    assert "A001" in apage and "B001" in apage and "<th>User ID</th>" in apage
