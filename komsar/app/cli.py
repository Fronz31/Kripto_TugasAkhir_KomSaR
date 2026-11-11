"""Perintah CLI: `flask --app run komsar bootstrap-admin` membuat admin pertama + dongle-nya.

Suara TIDAK direkam di sini: admin mendaftarkan suara saat login pertama di aplikasi desktop.
"""
import importlib.util

import click
from flask import current_app
from flask.cli import AppGroup

from .auth.dongle import DongleService
from .config import BASE_DIR
from .errors import KomSaRError
from .models.user import User
from .services import user_service as us
from .services.audit_service import DONGLE_REGISTER, USER_CREATE, audit

komsar_cli = AppGroup("komsar", help="Perintah administrasi KomSaR.")


def _load_desktop_dongle():
    """Pakai ulang helper ctypes klien desktop (desktop/dongle.py) tanpa menduplikasi kode."""
    spec = importlib.util.spec_from_file_location("komsar_desktop_dongle", BASE_DIR / "desktop" / "dongle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


desk = _load_desktop_dongle()


@komsar_cli.command("bootstrap-admin")
@click.option("--username", prompt="Username admin")
@click.option("--full-name", prompt="Nama lengkap")
@click.option("--unit", default="Pusat", show_default=True)
@click.option("--drive", help=r"Root flashdisk, mis. E:\ (tanpa opsi ini: pilih dari daftar)")
@click.option("--label", default="Dongle Admin", show_default=True, help="Label dongle")
@click.option("--force", is_flag=True, help="Tetap buat walau sudah ada admin")
@click.option("--no-dongle", is_flag=True, help="Uji coba: buat admin tanpa menulis dongle (server harus KOMSAR_REQUIRE_DONGLE=0)")
def bootstrap_admin(username, full_name, unit, drive, label, force, no_dongle):
    """Buat admin pertama (password sementara) dan tulis KOMSAR.DONGLE ke flashdisk."""
    if not force and User.query.filter_by(is_admin=True).first():
        raise click.ClickException("Sudah ada admin. Pakai --force bila memang ingin menambah admin lewat CLI.")
    if no_dongle:
        try:
            user, temp = us.create_with_temp_password(username, full_name, unit,
                                                      int(current_app.config["ENROLL_WINDOW_HOURS"]), is_admin=True)
        except (KomSaRError, ValueError) as e:
            raise click.ClickException(str(e))
        audit(USER_CREATE, target=user.username, user=user, is_admin=True, via="cli", dongle=False)
        click.echo(f"Admin {user.username} dibuat TANPA dongle. User ID: {user.user_id}")
        click.echo(f"Password sementara (ditampilkan sekali): {temp}")
        return
    drives = desk.list_removable_drives()
    if not drives:
        raise click.ClickException("Tidak ada flashdisk removable yang terdeteksi.")
    if drive is None:
        for d in drives:
            click.echo(f"  {d}  serial {desk.volume_serial(d) or '?'}")
        drive = click.prompt("Pilih drive", type=click.Choice(drives))
    elif drive not in drives:
        raise click.ClickException(f"{drive} bukan flashdisk removable. Pilihan: {', '.join(drives)}")
    serial = desk.volume_serial(drive)
    if serial is None:
        raise click.ClickException(f"Serial volume {drive} tidak terbaca.")

    try:
        user, temp = us.create_with_temp_password(username, full_name, unit,
                                                  int(current_app.config["ENROLL_WINDOW_HOURS"]), is_admin=True)
        dongle_id, token = DongleService().register(label, serial, user)
    except (KomSaRError, ValueError) as e:
        raise click.ClickException(str(e))
    desk.write_dongle(drive, dongle_id, token, drives=lambda: drives)
    audit(USER_CREATE, target=user.username, user=user, is_admin=True, via="cli")
    audit(DONGLE_REGISTER, target=dongle_id, user=user, via="cli")      # token tidak pernah dicatat

    click.echo(f"Admin {user.username} dibuat. User ID: {user.user_id}")
    click.echo(f"Dongle '{label}' ditulis ke {drive} (serial {serial}).")
    click.echo(f"Password sementara (ditampilkan sekali): {temp}")
    click.echo(f"Login pertama di aplikasi desktop dalam {current_app.config['ENROLL_WINDOW_HOURS']} jam: "
               "ganti password lalu daftarkan suara.")


def register_cli(app) -> None:
    app.cli.add_command(komsar_cli)
