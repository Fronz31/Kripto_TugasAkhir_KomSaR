from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for

from ..auth.password import verify_password
from ..auth.service import (complete_login, current_user, enroll_expired, find_user, is_locked, logout_user,
                            pending_state, record_failure, start_pending)
from ..errors import KomSaRError
from ..services import user_service as us
from ..services.audit_service import (ACCOUNT_LOCKED, LOGIN_FAILED, LOGIN_STEP1_SUCCESS, LOGIN_SUCCESS, LOGOUT,
                                      PASSWORD_CHANGE, audit)
from ._helpers import login_required, svc

bp = Blueprint("auth", __name__)

GENERIC_ERROR = "Username, password, atau dongle tidak valid."
EXPIRED_ENROLL = "Batas waktu login pertama sudah lewat. Akun dikunci; hubungi admin untuk reset."


def dev_skip_voice() -> bool:
    # Hanya development: backend suara palsu + mode debug. Konfigurasi produksi tidak pernah memenuhi keduanya.
    return current_app.debug and current_app.config["VOICE_BACKEND"] == "fake"


@bp.route("/")
def root():
    return redirect(url_for("dashboard.index"))


def _render_login():
    return render_template("login.html", require_dongle=current_app.config["KOMSAR_REQUIRE_DONGLE"])


def _fail(username, reason):
    audit(LOGIN_FAILED, target=username, reason=reason)          # alasan hanya di audit, tidak di UI
    flash(GENERIC_ERROR, "error")
    return _render_login()


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard.index"))
    if request.method != "POST":
        return _render_login()

    f = request.form
    username = f.get("username", "").strip().lower()[:32]
    user = find_user(username)
    if user is None or not user.is_active:
        return _fail(username, "password")
    if is_locked(user):
        return _fail(username, "locked")
    if not verify_password(user.password_hash, f.get("password", "")):
        if record_failure(user):
            audit(ACCOUNT_LOCKED, target=username, user=user, factor="password")
        return _fail(username, "password")
    dongle_id = None
    if current_app.config["KOMSAR_REQUIRE_DONGLE"]:
        dongle = svc().dongles.verify(f.get("dongle_id"), f.get("token"), f.get("volume_serial"))
        if dongle is None:
            return _fail(username, "dongle")
        dongle_id = dongle.id

    if user.must_enroll and enroll_expired(user):
        audit(LOGIN_FAILED, target=username, reason="expired")
        flash(EXPIRED_ENROLL, "error")
        return _render_login()
    if not user.must_enroll and not svc().voice.has_profile(user) and not dev_skip_voice():
        audit(LOGIN_FAILED, target=username, reason="no_voice_profile")
        flash("Akun belum memiliki profil suara. Hubungi admin.", "error")
        return _render_login()

    start_pending(user, dongle_id)
    audit(LOGIN_STEP1_SUCCESS, target=username, user=user)
    if user.must_enroll:
        return redirect(url_for("auth.login_enroll"))
    if dev_skip_voice():
        complete_login(user)
        audit(LOGIN_SUCCESS, target=username, user=user, factor="dev_no_voice")
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("auth.login_voice"))


def _pending():
    """User pending yang valid, atau response redirect ke /login."""
    state, user = pending_state()
    if state == "ok":
        return user, None
    if state == "expired":
        audit(LOGIN_FAILED, target=user.username, reason="expired")
        flash("Waktu login habis. Silakan ulangi dari awal.", "error")
    session.pop("pending_user_id", None)
    return None, redirect(url_for("auth.login"))


@bp.route("/login/voice")
def login_voice():
    user, resp = _pending()
    if resp:
        return resp
    if user.must_enroll:
        return redirect(url_for("auth.login_enroll"))
    return render_template("login_voice.html", pending=user)


@bp.route("/login/enroll", methods=["GET", "POST"])
def login_enroll():
    user, resp = _pending()
    if resp:
        return resp
    if not user.must_enroll:
        return redirect(url_for("auth.login_voice"))
    if enroll_expired(user):
        audit(LOGIN_FAILED, target=user.username, reason="expired")
        session.clear()
        flash(EXPIRED_ENROLL, "error")
        return redirect(url_for("auth.login"))
    if request.method == "POST" and not session.get("pw_changed"):
        new, confirm = request.form.get("new", ""), request.form.get("confirm", "")
        if new != confirm:
            flash("Konfirmasi password baru tidak sama.", "error")
        elif verify_password(user.password_hash, new):
            flash("Password baru harus berbeda dari password sementara.", "error")
        else:
            try:
                us.update_user(user.id, password=new)
                session["pw_changed"] = True
                audit(PASSWORD_CHANGE, target=user.username, user=user, first_login=True)
                flash("Password diganti. Lanjutkan dengan mendaftarkan suara.", "success")
            except KomSaRError as e:
                flash(str(e), "error")
        return redirect(url_for("auth.login_enroll"))
    return render_template("login_enroll.html", pending=user, pw_changed=session.get("pw_changed", False))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    svc().cache.clear_user(g.user.id)       # hapus hasil dekripsi dari memori
    audit(LOGOUT, target=g.user.username)
    logout_user()
    flash("Anda telah keluar.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current, new, confirm = (request.form.get(k, "") for k in ("current", "new", "confirm"))
        if not verify_password(g.user.password_hash, current):
            flash("Password saat ini salah.", "error")
        elif new != confirm:
            flash("Konfirmasi password baru tidak sama.", "error")
        else:
            try:
                us.update_user(g.user.id, password=new)
                audit(PASSWORD_CHANGE, target=g.user.username)
                flash("Password berhasil diubah.", "success")
            except KomSaRError as e:
                flash(str(e), "error")
        return redirect(url_for("auth.profile"))
    return render_template("profile.html")
