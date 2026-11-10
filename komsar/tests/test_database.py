"""Penyimpanan database: SqlRepository, foreign key, URL Postgres, dan data bertahan setelah restart."""
import os

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.config import TestConfig, database_url
from app.extensions import db
from app.models.records import (KIND_ASSET, KIND_FILE, KIND_TEXT, STATUS_DECRYPTED, STATUS_FAILED,
                                DeliveryRecord, FileRecord, MessageRecord)
from app.repository import SqlRepository
from app.services import user_service as us
from app.services.asset_service import STATUS_CIPHERTEXT_MISSING

SECRET = "K123"


def _users():
    return {n: us.create_user(f"{n}01", n.title(), "Unit", f"password-{n}")
            for n in ("andi", "budi", "citra")}


def _delivery(i, message_id, recipient_pk):
    return DeliveryRecord(id=f"d{i}", message_id=message_id, recipient_pk=recipient_pk,
                          kdf_salt=b"s", wrapped_key=b"w", stego_png=b"png")


def test_sql_repository_methods(app):
    u = _users()
    a, b, c = u["andi"], u["budi"], u["citra"]
    repo = SqlRepository()
    text = MessageRecord(id="m1", kind=KIND_TEXT, sender_pk=a.id, ciphertext=b"ct")
    repo.add_message(text, [_delivery(1, "m1", b.id), _delivery(2, "m1", c.id)])
    asset = MessageRecord(id="m2", kind=KIND_ASSET, important=True, sender_pk=b.id)
    f = FileRecord(id="f2", message_id="m2", original_name="k.pdf", plaintext_size=3, mime="application/pdf",
                   algo="aes-256-gcm", ciphertext=b"KSF1", ciphertext_sha256="0" * 64)
    repo.add_message(asset, [_delivery(3, "m2", c.id)], f)

    assert repo.get_message("m1").ciphertext == b"ct" and repo.get_message("zz") is None
    assert repo.get_delivery("d1").recipient_pk == b.id and repo.get_file("f2").original_name == "k.pdf"
    assert {d.id for d in repo.deliveries_for_message("m1")} == {"d1", "d2"}
    assert [d.id for d in repo.inbox(c.id)] == ["d2", "d3"]
    assert [m.id for m in repo.sent_messages(a.id)] == ["m1"]
    assert repo.get_message("m1").recipient_pks == [b.id, c.id] and repo.get_message("m2").file_id == "f2"
    assert [x.id for x in repo.asset_files(b.id)] == ["f2"]          # pengirim
    assert [x.id for x in repo.asset_files(c.id)] == ["f2"]          # penerima
    assert repo.asset_files(a.id) == []


def test_add_message_is_atomic_and_foreign_keys_enforced(app):
    a = _users()["andi"]
    repo = SqlRepository()
    with pytest.raises(IntegrityError):                              # penerima tidak ada di tabel users
        repo.add_message(MessageRecord(id="m1", kind=KIND_TEXT, sender_pk=a.id, ciphertext=b"x"),
                         [_delivery(1, "m1", 9999)])
    assert MessageRecord.query.count() == 0 and DeliveryRecord.query.count() == 0


def test_delivery_status_allows_failed_with_error(app):
    u = _users()
    repo = SqlRepository()
    repo.add_message(MessageRecord(id="m1", kind=KIND_TEXT, sender_pk=u["andi"].id, ciphertext=b"x"),
                     [_delivery(1, "m1", u["budi"].id)])
    d = repo.get_delivery("d1")
    d.status, d.error = STATUS_FAILED, "embed gagal"
    db.session.commit()
    assert repo.get_delivery("d1").status == STATUS_FAILED and d.decrypted_at is None
    d.status = "hilang"
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_ciphertext_missing_status(app):
    u = _users()
    svc = app.extensions["komsar"]
    m = svc.messaging.send_file(u["andi"], ["budi01"], "k.pdf", os.urandom(500), SECRET, kind=KIND_ASSET)
    f = svc.repo.get_file(m.file_id)
    f.ciphertext = None
    db.session.commit()
    assert svc.assets.verify_integrity(u["budi"], f.id).status == STATUS_CIPHERTEXT_MISSING


def test_database_url_normalised():
    assert database_url("postgres://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert database_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    assert database_url("").startswith("sqlite:///") and database_url(None).endswith("komsar.db")


def test_data_survives_restart(tmp_path):
    class FileDB(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'komsar.db').as_posix()}"

    data = b"%PDF-1.7 " + os.urandom(5000)
    first = create_app(FileDB)
    with first.app_context():
        _users()
        svc = first.extensions["komsar"]
        andi = us.get_by_username("andi01")
        svc.messaging.send_text(andi, ["budi01"], "rahasia", SECRET, important=True)
        svc.messaging.send_file(andi, ["budi01"], "laporan.pdf", data, SECRET, kind=KIND_FILE)
        svc.messaging.send_file(andi, ["budi01"], "kontrak.pdf", data, SECRET, kind=KIND_ASSET)
        db.session.remove()
        db.engine.dispose()

    second = create_app(FileDB)                                      # "server restart": app & engine baru
    with second.app_context():
        svc = second.extensions["komsar"]
        budi = us.get_by_username("budi01")
        items = sorted(svc.messaging.inbox(budi), key=lambda i: i["created_at"])
        assert [i["kind"] for i in items] == ["important_text", "file", "asset"]
        opened = [svc.decryption.open(budi, i["delivery_id"], budi.user_id) for i in items]
        assert opened[0].text == "rahasia" and opened[1].data == data and opened[2].data == data
        assert len(svc.chain.blocks()) == 2 and svc.chain.validate().valid  # genesis tidak dibuat ulang
        assert svc.repo.get_delivery(items[0]["delivery_id"]).status == STATUS_DECRYPTED
        db.session.remove()
        db.engine.dispose()
