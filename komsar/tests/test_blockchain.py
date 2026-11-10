"""Blockchain (hash chaining, tanpa PoW), aset penting, dan verifikasi integritas."""
import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from app.blockchain.block import GENESIS_PREV_HASH, Block
from app.blockchain.chain import Blockchain
from app.blockchain.store import BlockRow, SqlBlockStore
from app.extensions import db
from app.errors import AccessDeniedError, DecryptionError, IntegrityViolationError, ValidationError
from app.models.records import KIND_ASSET, KIND_FILE
from app.repository import SqlRepository
from app.services import user_service as us
from app.services.asset_service import AssetService
from app.services.decryption_service import DecryptionCenter
from app.services.messaging_service import MessagingService
from tests.helpers import corrupt

SECRET = "K123"
H = "a" * 64
pytestmark = pytest.mark.usefixtures("app")          # blok disimpan di tabel `blocks`
_COLUMN = {"index": "idx", "metadata": "metadata_json", "recipients": "recipients_json"}


def tamper(index, **changes):
    """Ubah baris blok langsung di database (simulasi penyerang dengan akses DB)."""
    row = db.session.get(BlockRow, index)
    for field, value in changes.items():
        setattr(row, _COLUMN.get(field, field), value)
    db.session.commit()


def delete_block(index):
    db.session.delete(db.session.get(BlockRow, index))
    db.session.commit()


def new_chain(n=3):
    chain = Blockchain()
    for i in range(n):
        chain.add_block(f"asset-{i}", f"{i:064x}", {"original_name": f"f{i}.pdf"}, {"user_id": "A001"},
                        [{"user_id": "B001"}])
    return chain


# ---------------- blockchain murni ----------------
def test_genesis_and_block_creation():
    chain = Blockchain()
    g = chain.blocks()[0]
    assert g.index == 0 and g.previous_hash == GENESIS_PREV_HASH and g.hash == g.compute_hash()
    b = chain.add_block("asset-1", H, {"original_name": "a.pdf"}, {"user_id": "A001"}, [{"user_id": "B001"}])
    assert b.index == 1 and b.previous_hash == g.hash and b.hash == b.compute_hash()
    assert len(b.hash) == 64 and chain.get_block_by_asset("asset-1") == b


def test_valid_chain_links():
    chain = new_chain(5)
    v = chain.validate()
    assert v.valid and v.length == 6 and v.errors == []
    bs = chain.blocks()
    assert all(bs[i].previous_hash == bs[i - 1].hash for i in range(1, len(bs)))


def test_duplicate_asset_and_bad_input_rejected():
    chain = new_chain(1)
    with pytest.raises(ValidationError):
        chain.add_block("asset-0", H, {}, {}, [])
    with pytest.raises(ValidationError):
        chain.add_block("x", "pendek", {}, {}, [])


@pytest.mark.parametrize("field,value", [
    ("metadata", {"original_name": "diubah.pdf"}),
    ("ciphertext_hash", "b" * 64),
    ("recipients", [{"user_id": "Z999"}]),
    ("sender", {"user_id": "Z999"}),
    ("timestamp", "2020-01-01T00:00:00+00:00"),
])
def test_modified_block_data_detected(field, value):
    chain = new_chain(4)
    tamper(2, **{field: value})
    v = chain.validate()
    assert not v.valid and v.first_invalid_index == 2


def test_modified_previous_hash_detected():
    chain = new_chain(4)
    tamper(3, previous_hash="c" * 64)
    assert not chain.validate().valid


def test_replaced_block_breaks_next_link():
    chain = new_chain(4)
    b = chain.blocks()[2]
    b.ciphertext_hash = "d" * 64
    b.seal()                                        # penyerang menghitung ulang hash blok itu saja
    tamper(2, ciphertext_hash=b.ciphertext_hash, hash=b.hash)
    v = chain.validate()
    assert not v.valid and v.first_invalid_index == 3     # tertangkap di blok berikutnya


def test_deleted_middle_block_detected():
    chain = new_chain(4)
    delete_block(2)
    assert not chain.validate().valid


def test_inserted_block_detected():
    chain = new_chain(3)
    for row in sorted(BlockRow.query.filter(BlockRow.idx >= 2), key=lambda r: -r.idx):   # geser, lalu sisipkan
        row.idx += 1
        db.session.flush()
    chain.store.append(Block(index=2, timestamp="2099-01-01T00:00:00+00:00", asset_id="fake",
                             ciphertext_hash=H, previous_hash=chain.blocks()[1].hash).seal())
    assert not chain.validate().valid


def test_sql_block_store_roundtrip():
    store = SqlBlockStore()
    genesis = store.last()                                  # dibuat create_app
    assert genesis.index == 0 and store.all() == [genesis]
    b = Block(index=1, timestamp="2026-01-01T00:00:00+00:00", asset_id="x", ciphertext_hash=H,
              metadata={"original_name": "laporan é.pdf", "size": 5}, sender={"user_id": "A001"},
              recipients=[{"user_id": "B001"}], previous_hash=genesis.hash).seal()
    store.append(b)
    db.session.expire_all()                                 # paksa baca ulang dari DB
    assert store.last() == b and store.all() == [genesis, b]
    assert store.all()[1].compute_hash() == b.hash          # JSON bolak-balik tidak mengubah hash


def test_export_json(tmp_path):
    chain = new_chain(2)
    data = json.loads(chain.export_json(tmp_path / "chain.json").read_text(encoding="utf-8"))
    assert len(data) == 3 and data[2]["previous_hash"] == data[1]["hash"]


# ---------------- aset penting ----------------
@pytest.fixture
def env(app):
    u = {n: us.create_user(f"{n}01", n.title(), f"Unit {n[0].upper()}", f"password-{n}")
         for n in ("andi", "budi", "citra", "deni")}
    repo, chain = SqlRepository(), Blockchain()
    assets = AssetService(repo, chain)
    master = app.config["DB_MASTER_KEY"]
    msg = MessagingService(repo, master, app.config["COVER_IMAGES_DIR"], app.config["MAX_FILE_BYTES"],
                           asset_service=assets)
    return SimpleNamespace(u=u, repo=repo, chain=chain, assets=assets, msg=msg,
                           center=DecryptionCenter(repo, master, assets), master=master)


def send_asset(env, to=("budi01",), data=None):
    data = data or os.urandom(20_000)
    m = env.msg.send_file(env.u["andi"], list(to), "kontrak.pdf", data, SECRET, kind=KIND_ASSET)
    return m, env.repo.get_file(m.file_id), data


def delivery_of(env, m, user):
    return next(d for d in env.repo.deliveries_for_message(m.id) if d.recipient_pk == user.id)


def test_asset_creates_one_block_with_hash_and_metadata_only(env):
    m, f, data = send_asset(env, ("budi01", "citra01", "deni01"))
    bs = env.chain.blocks()
    assert len(bs) == 2                                   # genesis + SATU blok walau 3 penerima
    b = bs[1]
    assert b.asset_id == f.id and f.block_index == 1
    assert b.ciphertext_hash == hashlib.sha256(f.ciphertext).hexdigest() == f.ciphertext_sha256
    assert b.metadata["original_name"] == "kontrak.pdf" and b.metadata["size"] == len(data)
    assert b.sender["user_id"] == env.u["andi"].user_id and {r["user_id"] for r in b.recipients} == {env.u["budi"].user_id, env.u["citra"].user_id, env.u["deni"].user_id}
    dump = json.dumps(b.to_record())
    assert SECRET not in dump and data[:16].hex() not in dump          # tanpa plaintext/kunci
    assert b.previous_hash == bs[0].hash and env.chain.validate().valid


def test_normal_file_and_text_do_not_create_blocks(env):
    env.msg.send_file(env.u["andi"], ["budi01"], "biasa.pdf", b"%PDF-1", SECRET, kind=KIND_FILE)
    env.msg.send_text(env.u["andi"], ["budi01"], "halo", SECRET, important=True)
    assert len(env.chain.blocks()) == 1


def test_list_and_metadata_access(env):
    m, f, _ = send_asset(env, ("budi01",))
    a, b, c = env.u["andi"], env.u["budi"], env.u["citra"]
    assert [x["name"] for x in env.assets.list_assets(a)] == ["kontrak.pdf"]
    assert env.assets.list_assets(a)[0]["role"] == "sender"
    assert env.assets.list_assets(b)[0]["role"] == "recipient"
    assert env.assets.list_assets(c) == []
    info = env.assets.asset_metadata(b, f.id)
    assert info["integrity"]["ok"] and info["integrity"]["status"] == "verified"
    assert "hash" not in json.dumps(info).lower() and "previous" not in json.dumps(info)   # blok mentah tidak tampil
    with pytest.raises(AccessDeniedError):
        env.assets.asset_metadata(c, f.id)
    with pytest.raises(AccessDeniedError):
        env.assets.verify_integrity(c, f.id)
    assert env.assets.list_blocks()[1]["asset_id"] == f.id           # blok mentah hanya via jalur admin


def test_verify_ok_and_ciphertext_modified(env):
    m, f, _ = send_asset(env)
    b = env.u["budi"]
    assert env.assets.verify_integrity(b, f.id).ok
    corrupt(f, 40)
    rep = env.assets.verify_integrity(b, f.id)
    assert not rep.ok and rep.status == "ciphertext_modified"


def test_verify_detects_block_tampering_missing_and_metadata(env):
    m, f, _ = send_asset(env)
    b = env.u["budi"]
    f.original_name = "diubah.pdf"                                    # metadata di record diubah
    assert env.assets.verify_integrity(b, f.id).status == "metadata_mismatch"
    f.original_name = "kontrak.pdf"
    tamper(1, metadata={**env.chain.blocks()[1].metadata, "size": 1})   # blok diubah
    assert env.assets.verify_integrity(b, f.id).status == "chain_broken"
    delete_block(1)                                                   # blok dihapus
    assert env.assets.verify_integrity(b, f.id).status == "block_missing"


def test_decryption_center_asset_flow_with_blockchain(env):
    m, f, data = send_asset(env)
    b = env.u["budi"]
    d = delivery_of(env, m, b)
    res = env.center.open(b, d.id, env.u["budi"].user_id)
    assert res.data == data and res.is_important and res.filename == "kontrak.pdf"


def test_decryption_center_refuses_modified_asset(env):
    m, f, _ = send_asset(env)
    b = env.u["budi"]
    d = delivery_of(env, m, b)
    raw = corrupt(f, -1)
    with pytest.raises(IntegrityViolationError) as e:
        env.center.open(b, d.id, env.u["budi"].user_id)
    assert "berubah" in str(e.value)
    assert env.repo.get_file(f.id).ciphertext == raw and d.status != "decrypted"   # ciphertext tidak diubah/dihapus


def test_decryption_center_refuses_when_chain_tampered(env):
    m, f, _ = send_asset(env)
    b = env.u["budi"]
    tamper(1, recipients=[{"user_id": "Z999"}])
    with pytest.raises(IntegrityViolationError):
        env.center.open(b, delivery_of(env, m, b).id, env.u["budi"].user_id)


def test_raw_sql_tamper_like_neon_console(env):
    """Simulasi uji manual: UPDATE langsung lewat SQL (bukan ORM), lalu sesi dibaca ulang dari DB."""
    from sqlalchemy import text
    m, f, _ = send_asset(env)
    b = env.u["budi"]
    raw = bytearray(f.ciphertext)
    raw[50] ^= 0xFF
    db.session.execute(text("UPDATE files SET ciphertext = :c WHERE id = :i"), {"c": bytes(raw), "i": f.id})
    db.session.commit()
    db.session.expire_all()
    assert env.assets.verify_integrity(b, f.id).status == "ciphertext_modified"
    with pytest.raises(IntegrityViolationError):
        env.center.open(b, delivery_of(env, m, b).id, b.user_id)
    assert delivery_of(env, m, b).status != "decrypted"

    db.session.execute(text("UPDATE blocks SET asset_id = 'palsu' WHERE idx = 1"))
    db.session.commit()
    db.session.expire_all()
    v = env.chain.validate()
    assert not v.valid and v.first_invalid_index == 1


def test_known_limitation_full_rewrite_not_detected_but_aead_still_protects(env):
    """Dokumentasi batas tamper-evident: penyerang yang menulis ulang ciphertext DAN seluruh blok
    setelahnya lolos dari validasi rantai, tetapi AEAD tetap menolak ciphertext yang diubah."""
    m, f, _ = send_asset(env)
    b = env.u["budi"]
    raw = corrupt(f, 40)
    blk = env.chain.blocks()[1]
    blk.ciphertext_hash = hashlib.sha256(raw).hexdigest(); blk.seal()                  # hitung ulang (blok ini terakhir)
    tamper(1, ciphertext_hash=blk.ciphertext_hash, hash=blk.hash)
    assert env.assets.verify_integrity(b, f.id).ok                    # batas: tidak terdeteksi oleh blockchain
    with pytest.raises(DecryptionError):                              # tetapi isi yang diubah tak bisa didekripsi
        env.center.open(b, delivery_of(env, m, b).id, env.u["budi"].user_id)
