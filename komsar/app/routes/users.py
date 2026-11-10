from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..errors import KomSaRError
from ..services import user_service as us
from ..services.audit_service import (USER_CREATE, USER_DELETE, USER_REGENERATE_ID, USER_UPDATE,
                                      audit)
from ._helpers import admin_required, login_required, svc

bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    return render_template("users.html", users=us.search_users(q) if q else us.list_users(), q=q)


@bp.route("/add", methods=["POST"])
@admin_required
def add():
    f = request.form
    try:
        user = us.create_user(f.get("username"), f.get("full_name"), f.get("unit"),
                              f.get("password"), is_admin=bool(f.get("is_admin")))
        audit(USER_CREATE, target=user.username, is_admin=user.is_admin)
        flash(f"Pengguna berhasil ditambahkan. User ID: {user.user_id} (serahkan kepada pemiliknya).", "success")
    except KomSaRError as e:
        flash(str(e), "error")
    return redirect(url_for("users.index"))


@bp.route("/<int:pk>/edit", methods=["GET", "POST"])
@admin_required
def edit(pk):
    try:
        user = us.get_user(pk)
    except KomSaRError:
        flash("Pengguna tidak ditemukan.", "error")
        return redirect(url_for("users.index"))
    if request.method == "POST":
        f = request.form
        try:
            is_active = bool(f.get("is_active")) or user.id == g.user.id      # tidak bisa menonaktifkan diri sendiri
            is_admin = bool(f.get("is_admin")) or user.id == g.user.id
            us.update_user(pk, full_name=f.get("full_name"), unit=f.get("unit"),
                           password=f.get("password") or None, is_active=is_active, is_admin=is_admin)
            audit(USER_UPDATE, target=user.username, is_active=is_active, is_admin=is_admin,
                  password_changed=bool(f.get("password")))
            flash("Data pengguna diperbarui.", "success")
            return redirect(url_for("users.index"))
        except KomSaRError as e:
            flash(str(e), "error")
    return render_template("user_edit.html", user=user, voice_enrolled=svc().voice.has_profile(user))


@bp.route("/<int:pk>/regenerate-id", methods=["POST"])
@admin_required
def regenerate_id(pk):
    try:
        user = us.regenerate_user_id(pk)
        audit(USER_REGENERATE_ID, target=user.username)        # ID baru tidak pernah dicatat
        flash(f"User ID baru untuk {user.username}: {user.user_id}. Pesan untuk ID lama tidak dapat dibuka lagi.",
              "success")
    except KomSaRError as e:
        flash(str(e), "error")
    return redirect(url_for("users.edit", pk=pk))


@bp.route("/<int:pk>/reset-voice", methods=["POST"])
@admin_required
def reset_voice(pk):
    try:
        user = us.get_user(pk)
        svc().voice.reset(user, g.user)
        flash(f"Suara {user.username} di-reset. Pengguna wajib mendaftarkan suara saat login berikutnya.", "success")
    except KomSaRError as e:
        flash(str(e), "error")
    return redirect(url_for("users.edit", pk=pk))


@bp.route("/<int:pk>/delete", methods=["POST"])
@admin_required
def delete(pk):
    repo = svc().repo
    try:
        user = us.get_user(pk)
        if user.id == g.user.id:
            flash("Anda tidak dapat menghapus akun sendiri.", "error")
        elif repo.inbox(pk) or repo.sent_messages(pk):
            flash("Pengguna memiliki riwayat pesan/file, tidak dapat dihapus. Nonaktifkan saja.", "error")
        else:
            username = user.username
            us.delete_user(pk)
            audit(USER_DELETE, target=username)
            flash("Pengguna dihapus.", "success")
    except KomSaRError as e:
        flash(str(e), "error")
    return redirect(url_for("users.index"))
