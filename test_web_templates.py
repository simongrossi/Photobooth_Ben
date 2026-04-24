"""test_web_templates.py — tests upload/activation/suppression de templates."""
from __future__ import annotations

import base64
import io
import os

import pytest
from PIL import Image

from web.app import create_app

HEADERS = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}


def _png_bytes(taille=(100, 100), couleur=(255, 0, 0, 128)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", taille, couleur).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    monkeypatch.setattr(config, "PATH_OVERLAYS", str(overlays))
    monkeypatch.setattr(config, "OVERLAY_10X15", str(overlays / "10x15_overlay.png"))
    monkeypatch.setattr(config, "OVERLAY_STRIPS", str(overlays / "strips_overlay.png"))
    import web.db
    import web.routes.templates_route as tr
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(tr, "_CIBLE_ACTIVE", {
        "10x15": str(overlays / "10x15_overlay.png"),
        "strip": str(overlays / "strips_overlay.png"),
    })
    # Les routes lisent PATH_OVERLAYS depuis le module importé — on patch aussi.
    monkeypatch.setattr(tr, "PATH_OVERLAYS", str(overlays))

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), str(overlays)


class TestUpload:
    def test_upload_png_valide(self, client):
        c, _ = client
        data = {
            "nom": "Mariage",
            "type": "10x15",
            "fichier": (io.BytesIO(_png_bytes()), "overlay.png"),
        }
        r = c.post("/templates/upload", data=data,
                   headers=HEADERS, content_type="multipart/form-data",
                   follow_redirects=True)
        assert r.status_code == 200
        assert b"Mariage" in r.data or b"uploade" in r.data.lower()

    def test_upload_refuse_mauvaise_extension(self, client):
        c, _ = client
        data = {
            "nom": "x",
            "type": "10x15",
            "fichier": (io.BytesIO(b"not an image"), "overlay.txt"),
        }
        r = c.post("/templates/upload", data=data,
                   headers=HEADERS, content_type="multipart/form-data",
                   follow_redirects=True)
        assert r.status_code == 200
        assert b"PNG uniquement" in r.data or b"invalide" in r.data.lower()

    def test_upload_refuse_fichier_corrompu(self, client):
        c, _ = client
        data = {
            "nom": "x",
            "type": "10x15",
            "fichier": (io.BytesIO(b"pas du png"), "fake.png"),
        }
        r = c.post("/templates/upload", data=data,
                   headers=HEADERS, content_type="multipart/form-data",
                   follow_redirects=True)
        assert r.status_code == 200
        assert b"non reconnu" in r.data or b"valide" in r.data.lower()

    def test_upload_refuse_type_inconnu(self, client):
        c, _ = client
        data = {
            "nom": "x",
            "type": "wrong",
            "fichier": (io.BytesIO(_png_bytes()), "o.png"),
        }
        r = c.post("/templates/upload", data=data,
                   headers=HEADERS, content_type="multipart/form-data",
                   follow_redirects=True)
        assert r.status_code == 200
        assert b"invalide" in r.data.lower()


class TestActivation:
    def test_activer_copie_le_fichier_vers_cible(self, client):
        c, overlays = client
        # Upload
        c.post("/templates/upload", data={
            "nom": "T1", "type": "10x15",
            "fichier": (io.BytesIO(_png_bytes()), "template1.png"),
        }, headers=HEADERS, content_type="multipart/form-data")
        # Trouver l'id via la liste
        from web.db import connexion
        with connexion() as conn:
            row = conn.execute("SELECT id FROM template WHERE nom = 'T1'").fetchone()
        c.post(f"/templates/activer/{row['id']}", headers=HEADERS, follow_redirects=True)
        # Vérifier que la cible existe
        cible = os.path.join(overlays, "10x15_overlay.png")
        assert os.path.isfile(cible)
        # Statut actif en DB
        with connexion() as conn:
            actif = conn.execute("SELECT actif FROM template WHERE id = ?", (row["id"],)).fetchone()
        assert actif["actif"] == 1

    def test_activer_exclusif_par_type(self, client):
        c, _ = client
        # Upload deux templates 10x15
        for nom, fichier in [("A", "a.png"), ("B", "b.png")]:
            c.post("/templates/upload", data={
                "nom": nom, "type": "10x15",
                "fichier": (io.BytesIO(_png_bytes()), fichier),
            }, headers=HEADERS, content_type="multipart/form-data")
        from web.db import connexion
        with connexion() as conn:
            rows = conn.execute(
                "SELECT id, nom FROM template WHERE type = '10x15' ORDER BY id"
            ).fetchall()
        c.post(f"/templates/activer/{rows[0]['id']}", headers=HEADERS)
        c.post(f"/templates/activer/{rows[1]['id']}", headers=HEADERS)
        with connexion() as conn:
            actifs = conn.execute(
                "SELECT COUNT(*) AS n FROM template WHERE type = '10x15' AND actif = 1"
            ).fetchone()
        assert actifs["n"] == 1


class TestSuppression:
    def test_suppression_bloquee_si_actif(self, client):
        c, _ = client
        c.post("/templates/upload", data={
            "nom": "X", "type": "10x15",
            "fichier": (io.BytesIO(_png_bytes()), "x.png"),
        }, headers=HEADERS, content_type="multipart/form-data")
        from web.db import connexion
        with connexion() as conn:
            row = conn.execute("SELECT id FROM template WHERE nom='X'").fetchone()
        c.post(f"/templates/activer/{row['id']}", headers=HEADERS)
        r = c.post(f"/templates/supprimer/{row['id']}", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        with connexion() as conn:
            still = conn.execute("SELECT COUNT(*) AS n FROM template WHERE id = ?", (row["id"],)).fetchone()
        assert still["n"] == 1  # pas supprimé
