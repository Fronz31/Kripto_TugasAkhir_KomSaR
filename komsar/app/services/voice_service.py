"""Pendaftaran & verifikasi suara. Hanya embedding terenkripsi (db_layer) yang disimpan, WAV tidak pernah."""
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import numpy as np

from ..auth.voice import VoiceVerifier
from ..crypto.db_layer import decrypt_from_db, encrypt_for_db
from ..errors import AccessDeniedError, ValidationError
from ..extensions import db
from ..models.security import VoiceProfile

PURPOSES = ("enroll", "verify")
ENROLL_SAMPLES = 3
CHALLENGE_TTL = 120     # detik
WORDS = ("merah", "biru", "hijau", "kuning", "putih", "hitam", "gunung", "sungai", "laut", "hutan",
         "kota", "desa", "pagi", "siang", "malam", "hujan", "angin", "bulan", "bintang", "matahari",
         "kopi", "teh", "nasi", "roti", "buku", "pena", "meja", "kursi", "pintu", "jendela",
         "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan", "sepuluh")


class VoiceService:
    def __init__(self, master_key: bytes, verifier: VoiceVerifier, threshold: float, enroll_hours: int):
        self.master_key, self.verifier = master_key, verifier
        self.threshold, self.enroll_hours = threshold, enroll_hours
        # shortcut: tantangan di memori per proses; ganti Redis/DB bila server >1 proses.
        self._challenges: dict[str, tuple[int, str, float]] = {}
        self._lock = threading.Lock()
        self.clock = time.monotonic

    @classmethod
    def from_app(cls, app):
        from ..auth.voice import make_verifier
        c = app.config
        return cls(c["DB_MASTER_KEY"], make_verifier(c), float(c["VOICE_THRESHOLD"]), int(c["ENROLL_WINDOW_HOURS"]))

    # ---- kalimat acak (tantangan) ----
    def new_challenge(self, user, purpose: str) -> tuple[str, str]:
        if purpose not in PURPOSES:
            raise ValidationError("Tujuan rekaman tidak dikenal.")
        cid = secrets.token_urlsafe(16)
        phrase = " ".join(secrets.choice(WORDS) for _ in range(4))
        with self._lock:
            now = self.clock()
            self._challenges = {k: v for k, v in self._challenges.items() if v[2] > now}
            self._challenges[cid] = (user.id, purpose, now + CHALLENGE_TTL)
        return cid, phrase

    def _consume(self, user, purpose: str, cid) -> None:
        with self._lock:
            entry = self._challenges.pop(cid, None) if isinstance(cid, str) else None
        if entry is None or entry[:2] != (user.id, purpose) or entry[2] <= self.clock():
            raise ValidationError("Kalimat acak tidak valid atau kedaluwarsa. Minta kalimat baru.")

    # ---- profil ----
    def has_profile(self, user) -> bool:
        return db.session.get(VoiceProfile, user.id) is not None

    def enroll(self, user, wavs: list[bytes], challenge_ids: list[str]) -> None:
        if len(wavs) != ENROLL_SAMPLES or len(challenge_ids) != ENROLL_SAMPLES:
            raise ValidationError(f"Pendaftaran suara membutuhkan tepat {ENROLL_SAMPLES} rekaman.")
        profile = db.session.get(VoiceProfile, user.id)
        if profile is not None and not user.must_enroll:
            raise AccessDeniedError("Suara sudah terdaftar. Hubungi admin untuk reset suara.")
        deadline = user.enroll_deadline
        if deadline is not None and (deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)) \
                < datetime.now(timezone.utc):
            raise AccessDeniedError("Batas waktu pendaftaran suara lewat. Hubungi admin.")
        for cid in challenge_ids:
            self._consume(user, "enroll", cid)
        emb = np.mean([self.verifier.embed(w) for w in wavs], axis=0)
        emb = (emb / (np.linalg.norm(emb) or 1.0)).astype("<f4")
        blob = encrypt_for_db(self.master_key, emb.tobytes())
        if profile is None:
            profile = VoiceProfile(user_id=user.id)
            db.session.add(profile)
        profile.embedding_enc, profile.nonce = blob, None       # nonce sudah di dalam blob AES-GCM
        profile.sample_count, profile.enrolled_at = ENROLL_SAMPLES, datetime.now(timezone.utc)
        user.must_enroll, user.enroll_deadline = False, None
        db.session.commit()

    def verify(self, user, wav: bytes, challenge_id) -> bool:
        self._consume(user, "verify", challenge_id)
        profile = db.session.get(VoiceProfile, user.id)
        if profile is None:
            return False
        stored = np.frombuffer(decrypt_from_db(self.master_key, profile.embedding_enc), dtype="<f4")
        return self.verifier.score(self.verifier.embed(wav), stored) >= self.threshold

    def reset(self, user, admin) -> None:
        if admin is None or not admin.is_admin:
            raise AccessDeniedError("Hanya admin yang dapat me-reset suara.")
        VoiceProfile.query.filter_by(user_id=user.id).delete()
        user.must_enroll = True
        user.enroll_deadline = datetime.now(timezone.utc) + timedelta(hours=self.enroll_hours)
        db.session.commit()
