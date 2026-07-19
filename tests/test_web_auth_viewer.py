"""test_web_auth_viewer.py — mode consultation anonyme (viewer) vs admin."""
from __future__ import annotations

import base64

import pytest
from PIL import Image

from web.app import create_app

HEADERS_OK = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}
HEADERS_KO = {"Authorization": "Basic " + base64.b64encode(b"admin:faux").decode()}


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    d10 = data / "print" / "print_10x15"
    dstrip = data / "print" / "print_strip"
    d10.mkdir(parents=True)
    dstrip.mkdir(parents=True)
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    monkeypatch.setattr(config, "PATH_PRINT", str(data / "print"))
    monkeypatch.setattr(config, "PATH_PRINT_10X15", str(d10))
    monkeypatch.setattr(config, "PATH_PRINT_STRIP", str(dstrip))
    import web.db
    import web.routes.gallery as g
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(g, "_RACINES_AUTORISEES", {"10x15": str(d10), "strip": str(dstrip)})
    monkeypatch.setattr(g, "PATH_CORBEILLE", str(data / "corbeille"))
    Image.new("RGB", (40, 40), (200, 30, 30)).save(str(d10 / "m1.jpg"), format="JPEG")

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


class TestViewerConsultation:
    def test_dashboard_accessible_sans_auth(self, client):
        r = client.get("/dashboard/")
        assert r.status_code == 200

    def test_heure_accessible_sans_auth(self, client):
        assert client.get("/dashboard/heure").status_code == 200

    def test_galerie_et_images_accessibles_sans_auth(self, client):
        assert client.get("/galerie/").status_code == 200
        assert client.get("/galerie/image/10x15/m1.jpg").status_code == 200
        assert client.get("/galerie/thumb/10x15/m1.jpg").status_code == 200

    def test_html_viewer_sans_actions_ni_chemins(self, client):
        dash = client.get("/dashboard/").get_data(as_text=True)
        assert "Réglages" not in dash
        assert "Journal :" not in dash
        assert "debloquer" not in dash
        galerie = client.get("/galerie/").get_data(as_text=True)
        assert "Retirer" not in galerie
        assert "Corbeille" not in galerie
        assert "Connexion admin" in dash


class TestViewerBloque:
    def test_post_retirer_401(self, client):
        assert client.post("/galerie/retirer/10x15/m1.jpg").status_code == 401

    def test_pages_gestion_401(self, client):
        for url in ("/templates/", "/kiosque/", "/settings/", "/evenements/"):
            assert client.get(url).status_code == 401, url

    def test_debloquer_quota_401(self, client):
        assert client.post("/dashboard/quota/debloquer").status_code == 401

    def test_mauvais_mdp_401(self, client):
        assert client.get("/dashboard/", headers=HEADERS_KO).status_code == 401


class TestInterrupteurEtFailClosed:
    def test_acces_libre_coupe_401(self, client, monkeypatch):
        monkeypatch.setenv("PHOTOBOOTH_ACCES_LIBRE", "0")
        assert client.get("/dashboard/").status_code == 401
        assert client.get("/dashboard/", headers=HEADERS_OK).status_code == 200

    def test_sans_mdp_admin_503_partout(self, client, monkeypatch):
        monkeypatch.delenv("PHOTOBOOTH_ADMIN_PASS", raising=False)
        assert client.get("/dashboard/").status_code == 503


class TestAdmin:
    def test_admin_voit_tout(self, client):
        dash = client.get("/dashboard/", headers=HEADERS_OK).get_data(as_text=True)
        assert "Réglages" in dash
        assert "Se déconnecter" in dash
        galerie = client.get("/galerie/", headers=HEADERS_OK).get_data(as_text=True)
        assert "Retirer" in galerie

    def test_connexion_declenche_challenge_puis_redirige(self, client):
        assert client.get("/connexion").status_code == 401
        r = client.get("/connexion", headers=HEADERS_OK)
        assert r.status_code == 302

    def test_deconnexion_repasse_en_viewer_jusqua_reconnexion(self, client):
        r = client.post("/deconnexion", headers=HEADERS_OK, follow_redirects=True)
        html = r.get_data(as_text=True)

        assert r.status_code == 200
        assert "Connexion admin" in html
        assert "Réglages" not in html

        # Même si le navigateur renvoie encore le header Basic, la session
        # reste volontairement en consultation.
        assert client.get("/settings/", headers=HEADERS_OK).status_code == 401

        client.get("/connexion", headers=HEADERS_OK)
        assert client.get("/settings/", headers=HEADERS_OK).status_code == 200
