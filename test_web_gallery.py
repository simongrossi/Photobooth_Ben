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


# --- Corbeille (volet 2) : retirer du slideshow/galerie, restaurer ---


@pytest.fixture
def client_corbeille(tmp_path, monkeypatch):
    """Comme `client`, mais retourne aussi les dossiers pour vérifier les déplacements."""
    data_path = tmp_path / "data"
    d10 = data_path / "print" / "print_10x15"
    dstrip = data_path / "print" / "print_strip"
    corbeille = data_path / "corbeille"
    d10.mkdir(parents=True)
    dstrip.mkdir(parents=True)
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data_path))
    monkeypatch.setattr(config, "PATH_PRINT", str(data_path / "print"))
    monkeypatch.setattr(config, "PATH_PRINT_10X15", str(d10))
    monkeypatch.setattr(config, "PATH_PRINT_STRIP", str(dstrip))

    import web.db
    import web.routes.gallery as g
    monkeypatch.setattr(web.db, "DB_PATH", str(data_path / "admin.db"))
    monkeypatch.setattr(g, "_RACINES_AUTORISEES", {"10x15": str(d10), "strip": str(dstrip)})
    monkeypatch.setattr(g, "PATH_CORBEILLE", str(corbeille))

    _png(d10 / "m1.jpg")

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), {"10x15": str(d10), "corbeille": str(corbeille)}


class TestCorbeille:
    def test_retirer_deplace_en_corbeille(self, client_corbeille):
        import os
        c, dossiers = client_corbeille
        r = c.post("/galerie/retirer/10x15/m1.jpg", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert not os.path.exists(os.path.join(dossiers["10x15"], "m1.jpg"))
        assert os.path.exists(os.path.join(dossiers["corbeille"], "10x15", "m1.jpg"))

    def test_restaurer_ramene_le_fichier(self, client_corbeille):
        import os
        c, dossiers = client_corbeille
        c.post("/galerie/retirer/10x15/m1.jpg", headers=HEADERS, follow_redirects=True)
        r = c.post("/galerie/restaurer/10x15/m1.jpg", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert os.path.exists(os.path.join(dossiers["10x15"], "m1.jpg"))

    def test_retirer_fichier_inexistant_404(self, client_corbeille):
        c, dossiers = client_corbeille
        assert c.post("/galerie/retirer/10x15/absent.jpg", headers=HEADERS).status_code == 404

    def test_restaurer_inexistant_404(self, client_corbeille):
        c, dossiers = client_corbeille
        assert c.post("/galerie/restaurer/10x15/absent.jpg", headers=HEADERS).status_code == 404

    def test_corbeille_visible_dans_la_page(self, client_corbeille):
        c, dossiers = client_corbeille
        c.post("/galerie/retirer/10x15/m1.jpg", headers=HEADERS, follow_redirects=True)
        r = c.get("/galerie/", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "Corbeille" in html
        assert "m1.jpg" in html


class TestFiltrerCategories:
    def test_filtrer_categories(self, tmp_path, monkeypatch):
        data = tmp_path / "data"
        (data / "print" / "print_10x15").mkdir(parents=True)
        (data / "print" / "print_strip").mkdir(parents=True)
        (data / "raw").mkdir(parents=True)
        (data / "skipped" / "deleted").mkdir(parents=True)
        (data / "skipped" / "retake").mkdir(parents=True)
        
        monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")
        
        import config
        monkeypatch.setattr(config, "PATH_DATA", str(data))
        monkeypatch.setattr(config, "PATH_PRINT", str(data / "print"))
        monkeypatch.setattr(config, "PATH_PRINT_10X15", str(data / "print" / "print_10x15"))
        monkeypatch.setattr(config, "PATH_PRINT_STRIP", str(data / "print" / "print_strip"))
        monkeypatch.setattr(config, "PATH_RAW", str(data / "raw"))
        monkeypatch.setattr(config, "PATH_SKIPPED_DELETED", str(data / "skipped" / "deleted"))
        monkeypatch.setattr(config, "PATH_SKIPPED_RETAKE", str(data / "skipped" / "retake"))
        
        import web.db
        import web.routes.gallery as g
        monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
        
        # Override _RACINES_AUTORISEES to use temporary directories
        monkeypatch.setattr(g, "_RACINES_AUTORISEES", {
            "10x15": str(data / "print" / "print_10x15"),
            "strip": str(data / "print" / "print_strip"),
            "raw": str(data / "raw"),
            "deleted": str(data / "skipped" / "deleted"),
            "retake": str(data / "skipped" / "retake"),
        })
        
        # Write fake images
        _png(data / "print" / "print_10x15" / "m1.jpg")
        _png(data / "raw" / "raw_1.jpg")
        _png(data / "skipped" / "deleted" / "del_1.jpg")
        _png(data / "skipped" / "retake" / "ret_1.jpg")
        
        app = create_app()
        app.config["TESTING"] = True
        c = app.test_client()
        
        # 1. Montages (default)
        r = c.get("/galerie/", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "m1.jpg" in html
        assert "raw_1.jpg" not in html
        
        # 2. Raw
        r = c.get("/galerie/?type=raw", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "raw_1.jpg" in html
        assert "m1.jpg" not in html
        
        # 3. Deleted
        r = c.get("/galerie/?type=deleted", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "del_1.jpg" in html
        assert "m1.jpg" not in html
        
        # 4. Retake
        r = c.get("/galerie/?type=retake", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "ret_1.jpg" in html
        assert "m1.jpg" not in html
