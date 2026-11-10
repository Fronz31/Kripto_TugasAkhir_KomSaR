from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..services import audit_service as svc_audit
from ..services.audit_service import DONGLE_DEACTIVATE, audit
from ._helpers import admin_required, svc

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/chain")
@admin_required
def chain():
    s = svc()
    return render_template("chain.html", validation=s.chain.validate(), blocks=s.assets.list_blocks())


@bp.route("/audit")
@admin_required
def audit_log():
    username, action = request.args.get("username", "").strip(), request.args.get("action", "")
    page = svc_audit.list_logs(username, action, page=request.args.get("page", 1, type=int))
    return render_template("audit.html", page=page, username=username, action=action, actions=svc_audit.ACTIONS)


@bp.route("/dongles")
@admin_required
def dongles():
    return render_template("dongles.html", dongles=svc().dongles.list())


@bp.route("/dongles/<dongle_id>/deactivate", methods=["POST"])
@admin_required
def dongle_deactivate(dongle_id):
    svc().dongles.deactivate(dongle_id)
    audit(DONGLE_DEACTIVATE, target=dongle_id[:64])
    flash("Dongle dinonaktifkan.", "success")
    return redirect(url_for("admin.dongles"))
