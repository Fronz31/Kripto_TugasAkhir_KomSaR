from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..auth.password import verify_password
from ..auth.service import authenticate, current_user, login_user, logout_user
from ..errors import KomSaRError
from ..services import user_service as us
from ..services.audit_service import LOGIN_FAILED, LOGIN_SUCCESS, LOGOUT, audit
from ._helpers import login_required, svc

bp = Blueprint("auth", __name__)


@bp.route("/")
def root():
    return redirect(url_for("dashboard.index"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        username = request.form.get("username", "")
        user = authenticate(username, request.form.get("password", ""))
        if user:
            login_user(user)
            audit(LOGIN_SUCCESS, target=user.username, user=user, factor="password")
            return redirect(url_for("dashboard.index"))
        audit(LOGIN_FAILED, target=username.strip().lower()[:32], factor="password")
        flash("Username atau password salah.", "error")
    return render_template("login.html")


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
                flash("Password berhasil diubah.", "success")
            except KomSaRError as e:
                flash(str(e), "error")
        return redirect(url_for("auth.profile"))
    return render_template("profile.html")
