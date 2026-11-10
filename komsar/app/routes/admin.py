from flask import Blueprint, flash, redirect, render_template, url_for

from ._helpers import admin_required, svc

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/chain")
@admin_required
def chain():
    s = svc()
    return render_template("chain.html", validation=s.chain.validate(), blocks=s.assets.list_blocks())


@bp.route("/dongles")
@admin_required
def dongles():
    return render_template("dongles.html", dongles=svc().dongles.list())


@bp.route("/dongles/<dongle_id>/deactivate", methods=["POST"])
@admin_required
def dongle_deactivate(dongle_id):
    svc().dongles.deactivate(dongle_id)
    flash("Dongle dinonaktifkan.", "success")
    return redirect(url_for("admin.dongles"))
