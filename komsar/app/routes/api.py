"""JSON API untuk dongle flashdisk dan suara. Balasan gagal dongle tidak pernah menyebut alasannya."""
import base64
import binascii
import time
from collections import defaultdict, deque
from functools import wraps

from flask import Blueprint, current_app, jsonify, request, session

from ..auth.service import MAX_VOICE_FAILS, complete_login, current_user, lock, pending_user, record_failure
from ..errors import AccessDeniedError, ValidationError
from ..services.audit_service import (ACCOUNT_LOCKED, DONGLE_REGISTER, LOGIN_SUCCESS, VOICE_ENROLL,
                                      VOICE_VERIFY_FAILED, VOICE_VERIFY_SUCCESS, audit)
from ._helpers import svc

bp = Blueprint("api", __name__, url_prefix="/api")


def _rate_limited() -> bool:
    # shortcut: limit di memori per proses, reset saat restart; ganti Redis bila server >1 proses.
    hits = current_app.extensions.setdefault("dongle_rate", defaultdict(deque))
    now, q = time.monotonic(), hits[request.remote_addr]
    while q and now - q[0] > 60:
        q.popleft()
    q.append(now)
    return len(q) > current_app.config["DONGLE_CHECK_RATE_PER_MIN"]


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _proof():
    data = _body()
    return data.get("dongle_id"), data.get("token"), data.get("volume_serial")


def _ok(ok: bool):
    return jsonify(ok=ok), (200 if ok else 403)


def api_login_required(admin=False):
    def deco(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None or not user.is_active:
                return jsonify(error="Silakan login terlebih dahulu."), 401
            if admin and not user.is_admin:
                return jsonify(error="Khusus admin."), 403
            return view(user, *args, **kwargs)
        return wrapped
    return deco


@bp.route("/client-config")
def client_config():
    """Dibaca klien desktop sebelum gerbang dongle; tanpa login."""
    return jsonify(require_dongle=bool(current_app.config["KOMSAR_REQUIRE_DONGLE"]))


@bp.route("/dongle/check", methods=["POST"])
def dongle_check():
    if _rate_limited():
        return jsonify(ok=False), 429
    return _ok(svc().dongles.verify(*_proof()) is not None)


@bp.route("/dongle/register", methods=["POST"])
@api_login_required(admin=True)
def dongle_register(user):
    data = _body()
    try:
        dongle_id, token = svc().dongles.register(data.get("label"), data.get("volume_serial"), user)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    audit(DONGLE_REGISTER, target=dongle_id, user=user)            # token tidak pernah dicatat
    return jsonify(dongle_id=dongle_id, token=token)


def _wav(b64) -> bytes:
    try:
        return base64.b64decode(b64 if isinstance(b64, str) else "", validate=True)
    except binascii.Error:
        raise ValidationError("Rekaman suara harus berupa base64.")


def _voice_call(fn):
    try:
        return fn()
    except ValidationError as e:
        return jsonify(error=str(e)), 400
    except AccessDeniedError as e:
        return jsonify(error=str(e)), 403


def _allowed(user, purpose) -> bool:
    """verify: pengguna pending yang punya profil suara. enroll: pengguna pending `must_enroll` yang sudah
    mengganti password sementara (langkah login pertama)."""
    if purpose == "verify":
        return not user.must_enroll and svc().voice.has_profile(user)
    if purpose == "enroll":
        return user.must_enroll and bool(session.get("pw_changed"))
    return True         # tujuan tak dikenal ditolak VoiceService (400)


def api_pending_required(purpose=None):
    """Endpoint suara hanya untuk sesi login yang belum selesai (setelah langkah 1, sebelum 3 menit)."""
    def deco(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = pending_user()
            if user is None:
                return jsonify(error="Sesi login tidak valid atau kedaluwarsa. Login ulang."), 401
            if not _allowed(user, purpose or _body().get("purpose")):
                return jsonify(error="Langkah login ini tidak tersedia untuk akun Anda."), 403
            return view(user, *args, **kwargs)
        return wrapped
    return deco


def _finish_login(user, factor):
    complete_login(user)
    audit(LOGIN_SUCCESS, target=user.username, user=user, factor=factor)
    return _ok(True)


@bp.route("/voice/challenge", methods=["POST"])
@api_pending_required()
def voice_challenge(user):
    def run():
        cid, phrase = svc().voice.new_challenge(user, _body().get("purpose"))
        return jsonify(challenge_id=cid, phrase=phrase)
    return _voice_call(run)


@bp.route("/voice/enroll", methods=["POST"])
@api_pending_required("enroll")
def voice_enroll(user):
    def run():
        samples = _body().get("samples")
        samples = [s for s in samples if isinstance(s, dict)] if isinstance(samples, list) else []
        svc().voice.enroll(user, [_wav(s.get("wav_b64")) for s in samples], [s.get("challenge_id") for s in samples])
        audit(VOICE_ENROLL, target=user.username, user=user)
        return _finish_login(user, "voice_enroll")      # password sudah diganti (dicek _allowed)
    return _voice_call(run)


@bp.route("/voice/verify", methods=["POST"])
@api_pending_required("verify")
def voice_verify(user):
    data = _body()

    def run():
        ok, score = svc().voice.verify_score(user, _wav(data.get("wav_b64")), data.get("challenge_id"))
        score = None if score is None else round(score, 3)      # untuk kalibrasi threshold (docs/uji-manual.md)
        if ok:
            audit(VOICE_VERIFY_SUCCESS, target=user.username, user=user, score=score)
            return _finish_login(user, "voice")
        audit(VOICE_VERIFY_FAILED, target=user.username, user=user, score=score)
        # Hitungan per sesi pending (3x) + hitungan akun (5x gabungan password/suara) agar
        # mengulang langkah 1 tidak mereset batas percobaan suara.
        session["voice_fails"] = session.get("voice_fails", 0) + 1
        locked = record_failure(user)
        if not locked and session["voice_fails"] >= MAX_VOICE_FAILS:
            lock(user)
            locked = True
        if locked:
            audit(ACCOUNT_LOCKED, target=user.username, user=user, factor="voice")
            session.clear()
        return _ok(False)
    return _voice_call(run)


@bp.route("/dongle/heartbeat", methods=["POST"])
@api_login_required()
def dongle_heartbeat(user):
    d = svc().dongles.verify(*_proof())
    if d is None:
        return _ok(False)
    session["dongle_id"] = d.id
    session["dongle_seen"] = int(time.time())
    return _ok(True)
