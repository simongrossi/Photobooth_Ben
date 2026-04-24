"""app.py — factory Flask pour l'interface admin web.

Usage local (dev) :
    PHOTOBOOTH_ADMIN_PASS=secret python3 -m web.app

Usage prod (systemd) :
    Voir deploy/photobooth-admin.service.
"""
from __future__ import annotations

import os

from flask import Flask, redirect, url_for

from web.db import init_db
from web.routes import dashboard, gallery, settings_route, templates_route


def create_app(config_overrides: dict | None = None) -> Flask:
    """Crée l'app Flask. `config_overrides` permet d'injecter des options en test."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    # Limite d'upload (10 Mo — largement au-dessus d'un PNG 1800x1200 RGBA).
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    # SECRET_KEY : utilisée uniquement pour signer les cookies flash(). Lue dans
    # l'env si fournie, sinon générée au démarrage (les flashes ne survivent
    # alors pas à un redémarrage, ce qui est sans conséquence ici).
    app.secret_key = os.environ.get("PHOTOBOOTH_ADMIN_SECRET") or os.urandom(32)
    if config_overrides:
        app.config.update(config_overrides)

    # Initialise la DB à la création de l'app (idempotent).
    init_db()

    # Blueprints
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(gallery.bp)
    app.register_blueprint(templates_route.bp)
    app.register_blueprint(settings_route.bp)

    @app.route("/")
    def index():
        return redirect(url_for("dashboard.index"))

    return app


def main() -> None:
    app = create_app()
    port = int(os.environ.get("PHOTOBOOTH_ADMIN_PORT", "8080"))
    host = os.environ.get("PHOTOBOOTH_ADMIN_HOST", "0.0.0.0")  # noqa: S104 — LAN admin
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
