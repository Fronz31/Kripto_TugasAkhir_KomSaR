import base64
import io
import wave

import numpy as np

from app.auth.dongle import DongleService
from app.auth.service import find_user
from app.extensions import db

PW = "komsar123"
SERIAL = "1A2B3C4D"
CSRF = "tok-test"
ANDI, BUDI = 220.0, 3100.0          # "pembicara" = frekuensi dasar berbeda (FakeVoiceVerifier)


def corrupt(file_rec, pos: int) -> bytes:
    """Balik satu bit ciphertext langsung di kolom database (simulasi penyerang dengan akses DB)."""
    raw = bytearray(file_rec.ciphertext)
    raw[pos] ^= 1
    file_rec.ciphertext = bytes(raw)
    db.session.commit()
    return bytes(raw)


def make_wav(freq=ANDI, seed=0, seconds=3.0, rate=16000, channels=1, width=2) -> bytes:
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * rate)) / rate
    x = 0.5 * np.sin(2 * np.pi * freq * t) + 0.02 * rng.standard_normal(t.size)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    if channels == 2:
        pcm = np.repeat(pcm, 2)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes() if width == 2 else (pcm >> 8).astype("i1").tobytes())
    return buf.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def enroll_voice(app, user, freq=ANDI):
    """Daftarkan suara lewat service (melewati alur login pertama)."""
    v = app.extensions["komsar"].voice
    ids = [v.new_challenge(user, "enroll")[0] for _ in range(3)]
    v.enroll(user, [make_wav(freq, seed=i) for i in range(3)], ids)


def set_csrf(c):
    with c.session_transaction() as s:
        s["csrf_token"] = CSRF


def api(c, url, body):
    return c.post(url, json=body, headers={"X-CSRF-Token": CSRF})


def login_step1(app, c, username, password=PW, dongle=None):
    """POST /login. `dongle` = (dongle_id, token, serial); dibuat otomatis bila dongle diwajibkan."""
    set_csrf(c)
    data = {"username": username, "password": password, "csrf_token": CSRF}
    if dongle is None and app.config["KOMSAR_REQUIRE_DONGLE"]:
        dongle = (*DongleService().register("Dongle test", SERIAL), SERIAL)
    if dongle:
        data.update(dongle_id=dongle[0], token=dongle[1], volume_serial=dongle[2])
    r = c.post("/login", data=data)
    set_csrf(c)
    return r


def voice_verify(c, freq=ANDI, seed=7):
    cid = api(c, "/api/voice/challenge", {"purpose": "verify"}).get_json().get("challenge_id")
    return api(c, "/api/voice/verify", {"challenge_id": cid, "wav_b64": b64(make_wav(freq, seed))})


def login(app, username, password=PW, client=None):
    """Login lengkap: langkah 1 lalu verifikasi suara (profil suara dibuat bila belum ada)."""
    c = client or app.test_client()
    user = find_user(username)
    if user is not None and not user.must_enroll and not app.extensions["komsar"].voice.has_profile(user):
        enroll_voice(app, user)
    r = login_step1(app, c, username, password)
    if r.status_code == 302 and r.headers["Location"].endswith("/login/voice"):
        voice_verify(c)
        set_csrf(c)
    return c
