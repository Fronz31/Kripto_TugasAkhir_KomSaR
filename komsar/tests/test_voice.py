"""Uji suara memakai FakeVoiceVerifier: validasi WAV, tantangan, enroll, verify, reset admin, endpoint."""
import numpy as np
import pytest

from app import create_app
from app.auth.voice import FakeVoiceVerifier, validate_wav
from app.config import TestConfig
from app.errors import AccessDeniedError, ValidationError
from app.extensions import db
from app.models.security import VoiceProfile
from app.services import user_service as us
from app.services.voice_service import CHALLENGE_TTL
from tests.helpers import ANDI, BUDI, PW, b64, login, login_step1, make_wav  # noqa: F401


@pytest.fixture
def web():
    app = create_app(TestConfig)
    with app.app_context():
        us.create_user("admin01", "Administrator", "Pusat", PW, is_admin=True)
        us.create_user("andi01", "Andi", "Unit A", PW)
        us.create_user("budi01", "Budi", "Unit B", PW)
        yield app


def voice(app):
    return app.extensions["komsar"].voice


def u(name):
    return us.get_by_username(name)


def enroll(app, user, freq=ANDI):
    v = voice(app)
    ids = [v.new_challenge(user, "enroll")[0] for _ in range(3)]
    v.enroll(user, [make_wav(freq, seed=i) for i in range(3)], ids)


def check(app, user, freq, seed=99):
    v = voice(app)
    return v.verify(user, make_wav(freq, seed=seed), v.new_challenge(user, "verify")[0])


# ---- WAV ----

def test_validate_wav_ok():
    assert validate_wav(make_wav(seconds=2)).size == 32000


@pytest.mark.parametrize("data", [
    b"", b"bukan wav", make_wav(rate=8000), make_wav(channels=2), make_wav(width=1),
    make_wav(seconds=1.5), make_wav(seconds=10.5), b"RIFF" + b"\0" * (1024 * 1024),
])
def test_validate_wav_rejects(data):
    with pytest.raises(ValidationError):
        validate_wav(data)


def test_fake_verifier_separates_speakers():
    f = FakeVoiceVerifier()
    a1, a2, b = f.embed(make_wav(ANDI, 1)), f.embed(make_wav(ANDI, 2)), f.embed(make_wav(BUDI, 1))
    assert f.score(a1, a2) > 0.9 and f.score(a1, b) < 0.1


# ---- tantangan ----

def test_challenge_phrase_and_purpose(web):
    cid, phrase = voice(web).new_challenge(u("andi01"), "verify")
    assert len(phrase.split()) == 4 and cid
    with pytest.raises(ValidationError):
        voice(web).new_challenge(u("andi01"), "lain")


def test_challenge_one_time_and_bound(web):
    enroll(web, u("andi01"))
    v, andi = voice(web), u("andi01")
    cid = v.new_challenge(andi, "verify")[0]
    assert v.verify(andi, make_wav(), cid)
    with pytest.raises(ValidationError):
        v.verify(andi, make_wav(), cid)                             # sekali pakai
    with pytest.raises(ValidationError):                            # milik akun lain
        v.verify(andi, make_wav(), v.new_challenge(u("budi01"), "verify")[0])
    with pytest.raises(ValidationError):                            # tujuan lain
        v.verify(andi, make_wav(), v.new_challenge(andi, "enroll")[0])


def test_challenge_expires(web):
    enroll(web, u("andi01"))
    v, andi = voice(web), u("andi01")
    cid = v.new_challenge(andi, "verify")[0]
    real = v.clock
    v.clock = lambda: real() + CHALLENGE_TTL + 1
    with pytest.raises(ValidationError):
        v.verify(andi, make_wav(), cid)


# ---- enroll / verify ----

def test_enroll_requires_three_samples(web):
    v, andi = voice(web), u("andi01")
    ids = [v.new_challenge(andi, "enroll")[0] for _ in range(2)]
    with pytest.raises(ValidationError):
        v.enroll(andi, [make_wav(), make_wav()], ids)
    assert not v.has_profile(andi)


def test_profile_encrypted_at_rest(web):
    andi = u("andi01")
    enroll(web, andi)
    p = db.session.get(VoiceProfile, andi.id)
    emb = np.mean([FakeVoiceVerifier().embed(make_wav(ANDI, i)) for i in range(3)], axis=0)
    raw = (emb / np.linalg.norm(emb)).astype("<f4").tobytes()
    assert p.sample_count == 3 and raw not in p.embedding_enc and raw[:16] not in p.embedding_enc
    assert len(p.embedding_enc) == len(raw) + 28                   # nonce 12 + tag 16


def test_verify_same_vs_other_speaker(web):
    enroll(web, u("andi01"))
    enroll(web, u("budi01"), BUDI)
    assert check(web, u("andi01"), ANDI)
    assert not check(web, u("andi01"), BUDI)                        # suara Budi ke akun Andi
    assert check(web, u("budi01"), BUDI) and not check(web, u("budi01"), ANDI)


def test_verify_without_profile_fails(web):
    assert not check(web, u("andi01"), ANDI)


def test_cannot_self_reenroll(web):
    enroll(web, u("andi01"))
    with pytest.raises(AccessDeniedError):
        enroll(web, u("andi01"), BUDI)
    assert check(web, u("andi01"), ANDI)


def test_admin_reset_flow(web):
    andi = u("andi01")
    enroll(web, andi)
    with pytest.raises(AccessDeniedError):
        voice(web).reset(andi, u("budi01"))
    voice(web).reset(andi, u("admin01"))
    assert andi.must_enroll and andi.enroll_deadline is not None and not voice(web).has_profile(andi)
    enroll(web, andi, BUDI)                                         # daftar ulang setelah reset
    assert not andi.must_enroll and andi.enroll_deadline is None
    assert check(web, andi, BUDI) and not check(web, andi, ANDI)


def test_delete_user_with_profile(web):
    enroll(web, u("andi01"))
    us.delete_user(u("andi01").id)
    assert db.session.query(VoiceProfile).count() == 0


# ---- endpoint ----

def post(c, url, body):
    return c.post(url, json=body, headers={"X-CSRF-Token": "tok-test"})


def test_api_enroll_and_verify(web):
    us.require_enrollment(u("andi01"), 24)
    c = web.test_client()
    login_step1(web, c, "andi01")                                   # sesi pending, wajib daftar
    assert web.test_client().post("/api/voice/challenge", json={"purpose": "verify"}).status_code in (400, 401)
    assert c.post("/api/voice/challenge", json={"purpose": "enroll"}).status_code == 400    # tanpa CSRF
    assert post(c, "/api/voice/challenge", {"purpose": "enroll"}).status_code == 403       # password belum diganti
    with c.session_transaction() as s:
        s["pw_changed"] = True
    assert post(c, "/api/voice/challenge", {"purpose": "x"}).status_code == 400
    assert post(c, "/api/voice/challenge", {"purpose": "verify"}).status_code == 403      # belum punya profil
    samples = []
    for i in range(3):
        r = post(c, "/api/voice/challenge", {"purpose": "enroll"}).get_json()
        assert len(r["phrase"].split()) == 4
        samples.append({"challenge_id": r["challenge_id"], "wav_b64": b64(make_wav(ANDI, i))})
    assert post(c, "/api/voice/enroll", {"samples": samples[:2]}).status_code == 400
    samples = [{"challenge_id": post(c, "/api/voice/challenge", {"purpose": "enroll"}).get_json()["challenge_id"],
                "wav_b64": s["wav_b64"]} for s in samples]
    assert post(c, "/api/voice/enroll", {"samples": samples}).get_json() == {"ok": True}
    with c.session_transaction() as s:
        assert "user_pk" in s and "pending_user_id" not in s
        s["csrf_token"] = "tok-test"
    assert post(c, "/api/voice/enroll", {"samples": samples}).status_code == 401           # sudah login, bukan pending

    c = web.test_client()
    login_step1(web, c, "andi01")
    assert post(c, "/api/voice/challenge", {"purpose": "enroll"}).status_code == 403      # tidak bisa daftar ulang

    def verify(wav):
        cid = post(c, "/api/voice/challenge", {"purpose": "verify"}).get_json()["challenge_id"]
        return post(c, "/api/voice/verify", {"challenge_id": cid, "wav_b64": wav})
    assert verify("%%%").status_code == 400
    assert verify(b64(b"bukan wav")).status_code == 400
    r = verify(b64(make_wav(BUDI, 7)))
    assert r.status_code == 403 and r.get_json() == {"ok": False}
    assert verify(b64(make_wav(ANDI, 7))).get_json() == {"ok": True}
    assert c.get("/dashboard").status_code == 200


def test_admin_reset_route(web):
    enroll(web, u("andi01"))
    pk = u("andi01").id
    assert login(web, "budi01").post(f"/users/{pk}/reset-voice", data={"csrf_token": "tok-test"}).status_code == 403
    assert voice(web).has_profile(u("andi01"))
    admin = login(web, "admin01")
    assert "terdaftar" in admin.get(f"/users/{pk}/edit").get_data(as_text=True)
    page = admin.post(f"/users/{pk}/reset-voice", data={"csrf_token": "tok-test"}).get_data(as_text=True)
    assert "Password sementara andi01" in page
    assert not voice(web).has_profile(u("andi01")) and u("andi01").must_enroll
