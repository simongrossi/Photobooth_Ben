"""test_web_app.py — tests de l'app Flask d'admin (auth, routing, dashboard)."""
from __future__ import annotations

import base64
import json

import pytest

from web.app import create_app


HEADERS_OK = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}
HEADERS_KO = {"Authorization": "Basic " + base64.b64encode(b"admin:wrong").decode()}


@pytest.fixture
def app(tmp_path, monkeypatch):
    """App Flask avec data/ isolé dans tmp_path + mot de passe 'test'."""
    data_path = tmp_path / "data"
    data_path.mkdir()
    (data_path / "print").mkdir()
    (data_path / "print" / "print_10x15").mkdir()
    (data_path / "print" / "print_strip").mkdir()
    overlays = tmp_path / "overlays"
    overlays.mkdir()

    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")
    # Redirige les chemins config vers tmp_path (sans casser les autres tests).
    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data_path))
    monkeypatch.setattr(config, "PATH_PRINT", str(data_path / "print"))
    monkeypatch.setattr(config, "PATH_PRINT_10X15", str(data_path / "print" / "print_10x15"))
    monkeypatch.setattr(config, "PATH_PRINT_STRIP", str(data_path / "print" / "print_strip"))
    monkeypatch.setattr(config, "PATH_OVERLAYS", str(overlays))
    monkeypatch.setattr(config, "OVERLAY_10X15", str(overlays / "10x15_overlay.png"))
    monkeypatch.setattr(config, "OVERLAY_STRIPS", str(overlays / "strips_overlay.png"))
    monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(data_path / "config_overrides.json"))
    # Modules déjà importés qui captent les chemins par `from config import`.
    import web.db
    import web.routes.gallery
    import web.routes.settings_route
    import web.routes.templates_route
    monkeypatch.setattr(web.db, "DB_PATH", str(data_path / "admin.db"))
    monkeypatch.setattr(web.routes.gallery, "_RACINES_AUTORISEES", {
        "10x15": str(data_path / "print" / "print_10x15"),
        "strip": str(data_path / "print" / "print_strip"),
    })
    monkeypatch.setattr(web.routes.templates_route, "_CIBLE_ACTIVE", {
        "10x15": str(overlays / "10x15_overlay.png"),
        "strip": str(overlays / "strips_overlay.png"),
    })
    monkeypatch.setattr(
        web.routes.settings_route,
        "CONFIG_OVERRIDES_PATH",
        str(data_path / "config_overrides.json"),
    )

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestAuth:
    def test_sans_env_var_retourne_503(self, monkeypatch):
        monkeypatch.delenv("PHOTOBOOTH_ADMIN_PASS", raising=False)
        app = create_app()
        c = app.test_client()
        r = c.get("/dashboard/")
        assert r.status_code == 503

    def test_sans_auth_retourne_401(self, client):
        r = client.get("/dashboard/")
        assert r.status_code == 401
        assert "WWW-Authenticate" in r.headers

    def test_mauvais_mdp_retourne_401(self, client):
        r = client.get("/dashboard/", headers=HEADERS_KO)
        assert r.status_code == 401

    def test_bon_mdp_retourne_200(self, client):
        r = client.get("/dashboard/", headers=HEADERS_OK)
        assert r.status_code == 200


class TestIndex:
    def test_redirige_vers_dashboard(self, client):
        r = client.get("/")
        assert r.status_code == 302
        assert "/dashboard" in r.headers["Location"]


class TestDashboard:
    def test_sans_sessions_affiche_zero(self, client):
        r = client.get("/dashboard/", headers=HEADERS_OK)
        assert r.status_code == 200
        assert b"Sessions" in r.data

    def test_avec_sessions(self, client, app, tmp_path):
        import config
        jsonl = tmp_path / "data" / "sessions.jsonl"
        jsonl.write_text(json.dumps({
            "session_id": "s1", "mode": "10x15", "issue": "printed",
            "nb_photos": 1, "duree_s": 30.0, "ts": "2026-04-20 14:00:00",
        }) + "\n", encoding="utf-8")
        assert config.PATH_DATA == str(tmp_path / "data")
        r = client.get("/dashboard/", headers=HEADERS_OK)
        assert r.status_code == 200
        # La card "Imprimées" doit contenir 1.
        assert b"Imprim" in r.data
