"""test_web_gallery.py — tests de la route galerie (listing, thumbs, sécurité chemins)."""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from web.app import create_app

HEADERS = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}


def _png(path, couleur=(255, 0, 0), taille=(50, 50)):
    Image.new("RGB", taille, couleur).save(path, format="JPEG")


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_path = tmp_path / "data"
    (data_path / "print" / "print_10x15").mkdir(parents=True)
    (data_path / "print" / "print_strip").mkdir(parents=True)
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data_path))
    monkeypatch.setattr(config, "PATH_PRINT", str(data_path / "print"))
    monkeypatch.setattr(config, "PATH_PRINT_10X15", str(data_path / "print" / "print_10x15"))
    monkeypatch.setattr(config, "PATH_PRINT_STRIP", str(data_path / "print" / "print_strip"))

    import web.db
    import web.routes.gallery
    monkeypatch.setattr(web.db, "DB_PATH", str(data_path / "admin.db"))
    monkeypatch.setattr(web.routes.gallery, "_RACINES_AUTORISEES", {
        "10x15": str(data_path / "print" / "print_10x15"),
        "strip": str(data_path / "print" / "print_strip"),
    })

    # Deux images factices dans chaque mode.
    _png(data_path / "print" / "print_10x15" / "photo_001.jpg")
    _png(data_path / "print" / "print_strip" / "strip_001.jpg", couleur=(0, 255, 0))

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


class TestListing:
    def test_liste_affiche_les_deux_modes(self, client):
        r = client.get("/galerie/", headers=HEADERS)
        assert r.status_code == 200
        assert b"photo_001.jpg" in r.data
        assert b"strip_001.jpg" in r.data

    def test_dossier_vide(self, tmp_path, monkeypatch):
        data = tmp_path / "data"
        (data / "print" / "print_10x15").mkdir(parents=True)
        (data / "print" / "print_strip").mkdir(parents=True)
        monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")
        import config
        monkeypatch.setattr(config, "PATH_DATA", str(data))
        monkeypatch.setattr(config, "PATH_PRINT", str(data / "print"))
        monkeypatch.setattr(config, "PATH_PRINT_10X15", str(data / "print" / "print_10x15"))
        monkeypatch.setattr(config, "PATH_PRINT_STRIP", str(data / "print" / "print_strip"))
        import web.db
        import web.routes.gallery
        monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
        monkeypatch.setattr(web.routes.gallery, "_RACINES_AUTORISEES", {
            "10x15": str(data / "print" / "print_10x15"),
            "strip": str(data / "print" / "print_strip"),
        })
        app = create_app()
        app.config["TESTING"] = True
        r = app.test_client().get("/galerie/", headers=HEADERS)
        assert r.status_code == 200
        assert b"Aucun montage" in r.data


class TestSecurite:
    def test_mode_inconnu_404(self, client):
        r = client.get("/galerie/image/exotique/photo_001.jpg", headers=HEADERS)
        assert r.status_code == 404

    def test_path_traversal_bloque(self, client):
        # Doit retourner 404 sans remonter au parent
        r = client.get("/galerie/image/10x15/..%2F..%2Fconfig.py", headers=HEADERS)
        assert r.status_code in (404, 400)

    def test_fichier_inexistant_404(self, client):
        r = client.get("/galerie/image/10x15/n_existe_pas.jpg", headers=HEADERS)
        assert r.status_code == 404


class TestThumbnail:
    def test_thumb_genere_png_valide(self, client):
        r = client.get("/galerie/thumb/10x15/photo_001.jpg", headers=HEADERS)
        assert r.status_code == 200
        assert r.mimetype in ("image/jpeg", "image/png")
        img = Image.open(io.BytesIO(r.data))
        assert max(img.size) <= 300
