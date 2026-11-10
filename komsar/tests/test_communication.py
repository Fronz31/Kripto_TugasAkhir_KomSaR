"""Pesan biasa & penting, file, gambar, aset, multi-penerima, Decryption Center."""
import io
import os
from types import SimpleNamespace

import pytest
from PIL import Image

from app.crypto import file_cipher
from app.crypto.db_layer import decrypt_from_db
from app.errors import (AccessDeniedError, DecryptionError, FileTooLargeError, IntegrityViolationError,
                        InvalidIDError, UserNotFoundError, ValidationError)
from app.models.records import (DeliveryRecord, FileRecord, KIND_ASSET, KIND_FILE, KIND_IMAGE, KIND_IMPORTANT_TEXT, KIND_TEXT,
                                STATUS_DECRYPTED, STATUS_DELIVERED, STATUS_SENT)
from app.repository import SqlRepository
from app.services import user_service as us
from app.services.decryption_service import DecryptionCenter
from app.services.messaging_service import MessagingService
from app.stego.extract import extract_key
from tests.helpers import corrupt

SECRET = "K123"
PLAIN = "Pergerakan pasukan dimulai pukul 05.00"


@pytest.fixture
def env(app):
    u = {n: us.create_user(f"{n}01", f"{n[0].upper()}001", n.title(), f"Unit {n[0].upper()}", f"password-{n}")
         for n in ("andi", "budi", "citra", "deni")}
    repo = SqlRepository()
    master = app.config["DB_MASTER_KEY"]
    msg = MessagingService(repo, master, app.config["COVER_IMAGES_DIR"], app.config["MAX_FILE_BYTES"])
    return SimpleNamespace(u=u, repo=repo, msg=msg, center=DecryptionCenter(repo, master), master=master)


def delivery_of(env, message, user):
    return next(d for d in env.repo.deliveries_for_message(message.id) if d.recipient_pk == user.id)


def make_png(color=(10, 200, 30)):
    buf = io.BytesIO(); Image.effect_noise((64, 64), 40).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


# ---------------- pesan biasa ----------------
def test_normal_text_roundtrip(env):
    a, b = env.u["andi"], env.u["budi"]
    m = env.msg.send_text(a, ["budi01"], PLAIN, SECRET)
    assert m.kind == KIND_TEXT and PLAIN.encode() not in m.ciphertext     # DB hanya ciphertext
    with pytest.raises(DecryptionError):                                  # tidak ada lapisan DB pada pesan biasa
        decrypt_from_db(env.master, m.ciphertext)
    res = env.center.open(b, delivery_of(env, m, b).id, "b001")           # ID dinormalisasi
    assert res.text == PLAIN and not res.is_important
    assert delivery_of(env, m, b).status == STATUS_DECRYPTED


def test_text_visible_again_after_decrypt(env):
    a, b = env.u["andi"], env.u["budi"]
    m = env.msg.send_text(a, "budi01", PLAIN, SECRET)
    d = delivery_of(env, m, b)
    assert env.center.open(b, d.id, "B001").text == PLAIN
    assert env.center.open(b, d.id, "B001").text == PLAIN                 # isi tidak hilang


# ---------------- pesan penting ----------------
def test_important_text_has_extra_layer(env):
    a, b = env.u["andi"], env.u["budi"]
    m = env.msg.send_text(a, ["budi01"], PLAIN, SECRET, important=True)
    assert m.kind == KIND_IMPORTANT_TEXT and PLAIN.encode() not in m.ciphertext
    inner = decrypt_from_db(env.master, m.ciphertext)                     # aplikasi dapat membuka lapisan DB
    assert len(inner) < len(m.ciphertext) and PLAIN.encode() not in inner
    res = env.center.open(b, delivery_of(env, m, b).id, "B001", expected_kind=KIND_IMPORTANT_TEXT)
    assert res.text == PLAIN and res.is_important


def test_important_and_normal_distinguishable_in_chat(env):
    a, b = env.u["andi"], env.u["budi"]
    env.msg.send_text(a, ["budi01"], "biasa", SECRET)
    env.msg.send_text(a, ["budi01"], "penting", SECRET, important=True)
    items = env.msg.inbox(b)
    assert {i["label"] for i in items} == {"Pesan Biasa", "Pesan Penting"}
    assert {i["is_important"] for i in items} == {True, False}
    assert all(i["encrypted"] and i["attachments"][0]["type"] == "ciphertext" for i in items)
    assert all("text" not in i and "biasa" not in str(i) and "penting" not in str(i).replace("Penting", "") for i in items)


# ---------------- ID salah & hak akses ----------------
def test_wrong_id_no_partial_plaintext_and_ciphertext_unchanged(env):
    a, b = env.u["andi"], env.u["budi"]
    m = env.msg.send_text(a, ["budi01"], PLAIN, SECRET, important=True)
    before, d = m.ciphertext, delivery_of(env, m, b)
    for bad in ("C001", "B002", "x"):
        with pytest.raises(InvalidIDError):
            env.center.open(b, d.id, bad)
    with pytest.raises(ValidationError):
        env.center.open(b, d.id, "  ")
    assert d.failed_attempts == 3 and d.status != STATUS_DECRYPTED
    assert env.repo.get_message(m.id).ciphertext == before


def test_cannot_open_others_or_sender(env):
    a, b, c = env.u["andi"], env.u["budi"], env.u["citra"]
    m = env.msg.send_text(a, ["budi01"], PLAIN, SECRET)
    d = delivery_of(env, m, b)
    with pytest.raises(AccessDeniedError):
        env.center.open(c, d.id, "B001")          # Citra tahu ID Budi, tapi bukan penerima
    with pytest.raises(AccessDeniedError):
        env.center.open(a, d.id, "B001")          # pengirim pun bukan penerima
    with pytest.raises(AccessDeniedError):
        env.center.open(b, "tidak-ada", "B001")


def test_expected_kind_mismatch(env):
    a, b = env.u["andi"], env.u["budi"]
    m = env.msg.send_text(a, ["budi01"], PLAIN, SECRET)
    with pytest.raises(ValidationError):
        env.center.open(b, delivery_of(env, m, b).id, "B001", expected_kind=KIND_FILE)


# ---------------- multi-penerima ----------------
def test_multiple_recipients_independent(env):
    a = env.u["andi"]
    m = env.msg.send_text(a, ["budi01", "citra01", "deni01", "BUDI01"], PLAIN, SECRET)   # duplikat diabaikan
    ds = env.repo.deliveries_for_message(m.id)
    assert len(ds) == 3 and len({d.stego_png for d in ds}) == 3 and len({d.wrapped_key for d in ds}) == 3
    for name, rid in (("budi", "B001"), ("citra", "C001"), ("deni", "D001")):
        user = env.u[name]
        assert extract_key(delivery_of(env, m, user).stego_png, rid) == SECRET.encode()
        assert env.center.open(user, delivery_of(env, m, user).id, rid).text == PLAIN
    assert len(env.repo.deliveries_for_message(m.id)) == 3 and env.repo.get_message(m.id).ciphertext  # satu ciphertext


def test_recipient_id_cannot_open_other_package_even_with_access(env):
    a, b, c = env.u["andi"], env.u["budi"], env.u["citra"]
    m = env.msg.send_text(a, ["budi01", "citra01"], PLAIN, SECRET)
    d_c = delivery_of(env, m, c)
    with pytest.raises(InvalidIDError):                 # andaikan Budi memiliki paket Citra: ID B001 tidak membukanya
        extract_key(d_c.stego_png, "B001")


def test_unknown_recipient_saves_nothing(env):
    a = env.u["andi"]
    with pytest.raises(UserNotFoundError):
        env.msg.send_text(a, ["budi01", "hantu99"], PLAIN, SECRET)
    assert env.repo.sent_messages(a.id) == [] and DeliveryRecord.query.count() == 0
    with pytest.raises(ValidationError):
        env.msg.send_text(a, [], PLAIN, SECRET)
    with pytest.raises(ValidationError):
        env.msg.send_text(a, ["andi01"], PLAIN, SECRET)
    with pytest.raises(ValidationError):
        env.msg.send_text(a, ["budi01"], PLAIN, "ab")


def test_status_flow_and_sent_view(env):
    a, b = env.u["andi"], env.u["budi"]
    m = env.msg.send_text(a, ["budi01", "citra01"], PLAIN, SECRET)
    assert delivery_of(env, m, b).status == STATUS_SENT
    env.msg.inbox(b)
    assert delivery_of(env, m, b).status == STATUS_DELIVERED
    env.center.open(b, delivery_of(env, m, b).id, "B001")
    st = {r["username"]: r["status"] for r in env.msg.sent(a)[0]["recipients"]}
    assert st == {"budi01": STATUS_DECRYPTED, "citra01": STATUS_SENT}


# ---------------- file ----------------
def test_file_roundtrip_multi_recipient(env):
    a = env.u["andi"]
    data = b"%PDF-1.7\n" + os.urandom(150_000)
    m = env.msg.send_file(a, ["budi01", "citra01"], "Laporan Harian.pdf", data, SECRET)
    f = env.repo.get_file(m.file_id)
    enc = f.ciphertext
    assert m.kind == KIND_FILE and f.algo == file_cipher.ALGO_CHACHA20 and b"%PDF" not in enc
    for name, rid in (("budi", "B001"), ("citra", "C001")):
        res = env.center.open(env.u[name], delivery_of(env, m, env.u[name]).id, rid)
        assert res.data == data and res.filename == "Laporan Harian.pdf" and res.mime == "application/pdf"
    assert env.repo.get_file(f.id).ciphertext == enc            # ciphertext tidak berubah


def test_file_validation(env):
    a = env.u["andi"]
    with pytest.raises(ValidationError):
        env.msg.send_file(a, ["budi01"], "virus.exe", b"MZ....", SECRET)
    with pytest.raises(ValidationError):
        env.msg.send_file(a, ["budi01"], "kosong.pdf", b"", SECRET)
    with pytest.raises(FileTooLargeError):
        env.msg.send_file(a, ["budi01"], "besar.pdf", os.urandom(1024 * 1024 + 1), SECRET)
    assert FileRecord.query.count() == 0 and DeliveryRecord.query.count() == 0
    m = env.msg.send_file(a, ["budi01"], "../../etc/catatan.txt", b"halo", SECRET)
    assert env.repo.get_file(m.file_id).original_name == "catatan.txt"       # path traversal dibuang


def test_tampered_file_detected_and_unchanged(env):
    a, b = env.u["andi"], env.u["budi"]
    m = env.msg.send_file(a, ["budi01"], "data.csv", os.urandom(5000), SECRET)
    raw = corrupt(env.repo.get_file(m.file_id), 60)
    with pytest.raises(DecryptionError):
        env.center.open(b, delivery_of(env, m, b).id, "B001")
    assert env.repo.get_file(m.file_id).ciphertext == raw


# ---------------- gambar ----------------
def test_image_transfer_distinct_from_stego(env):
    a, b = env.u["andi"], env.u["budi"]
    png = make_png()
    m = env.msg.send_file(a, ["budi01"], "foto.png", png, SECRET, kind=KIND_IMAGE)
    d, f = delivery_of(env, m, b), env.repo.get_file(m.file_id)
    assert d.stego_png != f.ciphertext                       # dua data berbeda
    assert f.ciphertext[:4] == b"KSF1" and d.stego_png[:4] == b"\x89PNG"
    info = env.msg.describe_delivery(d)
    assert [x["type"] for x in info["attachments"]] == ["ciphertext_file", "stego_image"]
    with pytest.raises(DecryptionError):                     # stego tidak bisa dipakai sebagai gambar utama
        file_cipher.decrypt_bytes(os.urandom(32), d.stego_png)
    res = env.center.open(b, d.id, "B001", expected_kind=KIND_IMAGE)
    assert res.data == png and res.filename == "foto.png"


def test_image_validation(env):
    a = env.u["andi"]
    with pytest.raises(ValidationError):
        env.msg.send_file(a, ["budi01"], "palsu.png", b"bukan gambar", SECRET, kind=KIND_IMAGE)
    with pytest.raises(ValidationError):
        env.msg.send_file(a, ["budi01"], "dokumen.pdf", b"%PDF", SECRET, kind=KIND_IMAGE)


# ---------------- aset penting ----------------
def test_important_asset_aesgcm_and_hash_check(env):
    a, b = env.u["andi"], env.u["budi"]
    data = os.urandom(30_000)
    m = env.msg.send_file(a, ["budi01"], "kontrak.docx", data, SECRET, kind=KIND_ASSET)
    f = env.repo.get_file(m.file_id)
    assert f.algo == file_cipher.ALGO_AESGCM and len(f.ciphertext_sha256) == 64
    res = env.center.open(b, delivery_of(env, m, b).id, "B001")
    assert res.data == data and res.is_important
    corrupt(f, -1)
    with pytest.raises(IntegrityViolationError):             # hash ciphertext tidak cocok
        env.center.open(b, delivery_of(env, m, b).id, "B001")


# ---------------- alur dua langkah (ekstrak -> ketik ulang kunci) ----------------
from app.errors import StegoKeyMismatchError


def test_two_step_extract_then_manual_key(env):
    a, b = env.u["andi"], env.u["budi"]
    m = env.msg.send_text(a, ["budi01"], PLAIN, SECRET)
    d = delivery_of(env, m, b)
    secret = env.center.extract_secret(b, d.id, "b001")
    assert secret == SECRET and d.status != STATUS_DECRYPTED
    res = env.center.open(b, d.id, "B001", secret_input=secret)
    assert res.text == PLAIN and d.status == STATUS_DECRYPTED


def test_two_step_wrong_id_and_wrong_key(env):
    a, b = env.u["andi"], env.u["budi"]
    m = env.msg.send_text(a, ["budi01"], PLAIN, SECRET, important=True)
    d = delivery_of(env, m, b)
    with pytest.raises(InvalidIDError):
        env.center.extract_secret(b, d.id, "C001")
    with pytest.raises(StegoKeyMismatchError):
        env.center.open(b, d.id, "B001", secret_input="SALAH")
    with pytest.raises(StegoKeyMismatchError):
        env.center.open(b, d.id, "B001", secret_input=SECRET + " ")        # harus persis sama
    with pytest.raises(ValidationError):
        env.center.open(b, d.id, "B001", secret_input="")
    assert d.status != STATUS_DECRYPTED and d.failed_attempts == 3
    assert env.center.open(b, d.id, "B001", secret_input=SECRET).text == PLAIN


def test_extract_secret_requires_recipient(env):
    a, b, c = env.u["andi"], env.u["budi"], env.u["citra"]
    m = env.msg.send_text(a, ["budi01"], PLAIN, SECRET)
    with pytest.raises(AccessDeniedError):
        env.center.extract_secret(c, delivery_of(env, m, b).id, "B001")
