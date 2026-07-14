"""test_web_kiosque.py — page Kiosque (fond accueil, police, slides)."""
from __future__ import annotations

import base64
import io
import os

import pytest
from PIL import Image

from web.app import create_app

HEADERS = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}


class TestTableAssetKiosque:
    def test_table_creee(self, tmp_path):
        import sqlite3
        from web.db import init_db
        db = str(tmp_path / "admin.db")
        init_db(path=db)
        conn = sqlite3.connect(db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "asset_kiosque" in tables


def _png_bytes(taille=(60, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", taille, (10, 120, 220)).save(buf, format="PNG")
    return buf.getvalue()


def _ttf_bytes() -> bytes:
    # La police par défaut du repo sert de .ttf valide pour les tests.
    with open("assets/fonts/WesternBangBang-Regular.ttf", "rb") as f:
        return f.read()


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    accueil_bib = tmp_path / "accueil"
    fonts_bib = tmp_path / "fonts"
    slides = tmp_path / "slides"
    for d in (accueil_bib, fonts_bib, slides):
        d.mkdir()
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    import web.db
    import web.routes.kiosque_route as kr
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(kr, "_RACINE_PAR_CATEGORIE", {
        "accueil": str(accueil_bib), "police": str(fonts_bib), "slide": str(slides),
    })
    monkeypatch.setattr(kr, "_CIBLE_ACTIVE", {
        "accueil": str(tmp_path / "accueil_actif.jpg"),
        "police": str(tmp_path / "police_active.ttf"),
    })

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), str(tmp_path)


def _uploader(c, nom, categorie, contenu, nom_fichier):
    c.post("/kiosque/upload", data={
        "nom": nom, "categorie": categorie,
        "fichier": (io.BytesIO(contenu), nom_fichier),
    }, headers=HEADERS, content_type="multipart/form-data", follow_redirects=True)
    import sqlite3
    import web.db
    conn = sqlite3.connect(web.db.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM asset_kiosque WHERE nom = ?", (nom,)).fetchone()
    conn.close()
    return row["id"] if row else None


class TestUploadKiosque:
    def test_upload_fond_accueil(self, client):
        c, base = client
        tid = _uploader(c, "Plage", "accueil", _png_bytes(), "plage.png")
        assert tid is not None

    def test_upload_police_valide(self, client):
        c, base = client
        tid = _uploader(c, "Western", "police", _ttf_bytes(), "western.ttf")
        assert tid is not None

    def test_upload_police_corrompue_refusee(self, client):
        c, base = client
        tid = _uploader(c, "Fausse", "police", b"pas une fonte", "fake.ttf")
        assert tid is None

    def test_upload_slide(self, client):
        c, base = client
        tid = _uploader(c, "Annonce", "slide", _png_bytes(), "annonce.png")
        assert tid is not None

    def test_categorie_inconnue_refusee(self, client):
        c, base = client
        assert _uploader(c, "X", "autre", _png_bytes(), "x.png") is None


class TestActivationKiosque:
    def test_activer_accueil_copie_cible(self, client):
        c, base = client
        tid = _uploader(c, "Plage", "accueil", _png_bytes(), "plage.png")
        r = c.post(f"/kiosque/activer/{tid}", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert os.path.isfile(os.path.join(base, "accueil_actif.jpg"))

    def test_activer_police_copie_cible(self, client):
        c, base = client
        tid = _uploader(c, "Western", "police", _ttf_bytes(), "w.ttf")
        c.post(f"/kiosque/activer/{tid}", headers=HEADERS, follow_redirects=True)
        assert os.path.isfile(os.path.join(base, "police_active.ttf"))

    def test_activer_slide_400(self, client):
        c, base = client
        tid = _uploader(c, "Annonce", "slide", _png_bytes(), "a.png")
        r = c.post(f"/kiosque/activer/{tid}", headers=HEADERS)
        assert r.status_code == 400


class TestDefautKiosque:
    def test_defaut_supprime_cible(self, client):
        c, base = client
        tid = _uploader(c, "Plage", "accueil", _png_bytes(), "plage.png")
        c.post(f"/kiosque/activer/{tid}", headers=HEADERS, follow_redirects=True)
        r = c.post("/kiosque/defaut/accueil", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert not os.path.exists(os.path.join(base, "accueil_actif.jpg"))

    def test_defaut_idempotent(self, client):
        c, base = client
        r = c.post("/kiosque/defaut/police", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200

    def test_defaut_slide_404(self, client):
        c, base = client
        assert c.post("/kiosque/defaut/slide", headers=HEADERS).status_code == 404


class TestPageEtThumb:
    def test_page_trois_sections(self, client):
        c, base = client
        r = c.get("/kiosque/", headers=HEADERS)
        html = r.get_data(as_text=True)
        for txt in ("Fond d'accueil", "Police", "Slides"):
            assert txt in html

    def test_thumb_police_rendue(self, client):
        c, base = client
        tid = _uploader(c, "Western", "police", _ttf_bytes(), "w.ttf")
        r = c.get(f"/kiosque/thumb/{tid}", headers=HEADERS)
        assert r.status_code == 200
        assert r.mimetype == "image/png"

    def test_supprimer_actif_refuse(self, client):
        c, base = client
        tid = _uploader(c, "Plage", "accueil", _png_bytes(), "p.png")
        c.post(f"/kiosque/activer/{tid}", headers=HEADERS, follow_redirects=True)
        c.post(f"/kiosque/supprimer/{tid}", headers=HEADERS, follow_redirects=True)
        import sqlite3
        import web.db
        conn = sqlite3.connect(web.db.DB_PATH)
        n = conn.execute("SELECT COUNT(*) FROM asset_kiosque").fetchone()[0]
        conn.close()
        assert n == 1  # toujours là
