"""JSON API untuk dongle flashdisk. Balasan gagal tidak pernah menyebut alasannya."""
import time
from collections import defaultdict, deque
from functools import wraps

from flask import Blueprint, current_app, jsonify, request, session

from ..auth.service import current_user
from ..services.audit_service import DONGLE_REGISTER, audit
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


@bp.route("/dongle/heartbeat", methods=["POST"])
@api_login_required()
def dongle_heartbeat(user):
    d = svc().dongles.verify(*_proof())
    if d is None:
        return _ok(False)
    session["dongle_id"] = d.id
    session["dongle_seen"] = int(time.time())
    return _ok(True)
