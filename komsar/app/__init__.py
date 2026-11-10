from pathlib import Path

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config, load_db_master_key
from .crypto.kdf import KDFParams, set_kdf_params
from .extensions import db


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    if app.config.get("KOMSAR_ENV") == "production":
        missing = [name for name, ok in (("KOMSAR_SECRET_KEY", app.config.get("SECRET_KEY")),
                                         ("KOMSAR_DB_MASTER_KEY", app.config.get("DB_MASTER_KEY_B64")),
                                         ("DATABASE_URL", app.config.get("DATABASE_URL_SET"))) if not ok]
        if missing:
            raise RuntimeError(f"KOMSAR_ENV=production: env wajib belum diisi: {', '.join(missing)}.")
    if app.config.get("KOMSAR_TRUST_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    if not app.config.get("SECRET_KEY") or not app.config.get("DB_MASTER_KEY_B64"):
        raise RuntimeError(
            "KOMSAR_SECRET_KEY dan KOMSAR_DB_MASTER_KEY wajib diisi (lihat .env.example)."
        )
    app.config["DB_MASTER_KEY"] = load_db_master_key(app.config)

    (Path(app.root_path).parent / "instance").mkdir(exist_ok=True)

    set_kdf_params(KDFParams(
        time_cost=app.config["ARGON2_TIME_COST"],
        memory_kib=app.config["ARGON2_MEMORY_KIB"],
        parallelism=app.config["ARGON2_PARALLELISM"],
    ))

    app.config.setdefault("MAX_CONTENT_LENGTH", app.config["MAX_FILE_BYTES"] + 2 * 1024 * 1024)
    db.init_app(app)
    from .blockchain import store  # noqa: F401  (daftarkan model)
    from .models import records, security, user  # noqa: F401
    from .services.container import build_services
    with app.app_context():
        db.create_all()
        app.extensions["komsar"] = build_services(app)      # blok genesis dibuat di DB bila belum ada
    from .routes import register_routes
    register_routes(app)
    from .cli import register_cli
    register_cli(app)
    return app
