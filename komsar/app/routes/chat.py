from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..errors import KomSaRError
from ..services import user_service as us
from ._helpers import after_send, login_required, parse_usernames, svc

bp = Blueprint("chat", __name__)


@bp.route("/chat")
@login_required
def index():
    s = svc()
    inbox = s.messaging.inbox(g.user)
    for item in inbox:                       # isi hanya tampil bila sudah didekripsi pada sesi ini
        item["text"] = s.cache.get_text(g.user.id, item["delivery_id"])
    return render_template("chat.html", inbox=inbox, sent=s.messaging.sent(g.user))


@bp.route("/chat/<username>")
@login_required
def conversation(username):
    try:
        other = us.get_by_username(username)
    except KomSaRError:
        abort(404)
    if other.id == g.user.id:
        return redirect(url_for("chat.index"))
    return render_template("conversation.html", other=other, items=svc().messaging.conversation(g.user, other))


@bp.route("/chat/send", methods=["POST"])
@login_required
def send():
    f = request.form
    try:
        message = svc().messaging.send_text(g.user, parse_usernames(f.get("recipients", "")), f.get("message", ""),
                                            f.get("secret", ""), important=bool(f.get("important")))
        flash("Pesan terenkripsi berhasil dikirim; gambar steganografi dibuat untuk setiap penerima.", "success")
        after_send(message)
    except KomSaRError as e:
        flash(str(e), "error")
    return redirect(url_for("chat.index"))
