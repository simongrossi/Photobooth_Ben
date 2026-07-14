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


def _jpg_bytes(taille=(100, 100), couleur=(0, 128, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", taille, couleur).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    fonds = tmp_path / "fonds"
    fonds.mkdir()
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    monkeypatch.setattr(config, "PATH_OVERLAYS", str(overlays))
    monkeypatch.setattr(config, "PATH_FONDS", str(fonds))
    monkeypatch.setattr(config, "OVERLAY_10X15", str(overlays / "10x15_overlay.png"))
    monkeypatch.setattr(config, "OVERLAY_STRIPS", str(overlays / "strips_overlay.png"))
    monkeypatch.setattr(config, "BG_10X15_FILE", str(fonds / "10x15_background.jpg"))
    monkeypatch.setattr(config, "BG_STRIPS_FILE", str(fonds / "strips_background.jpg"))
    import web.db
    import web.routes.templates_route as tr
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(tr, "_CIBLE_ACTIVE", {
        ("overlay", "10x15"): str(overlays / "10x15_overlay.png"),
        ("overlay", "strip"): str(overlays / "strips_overlay.png"),
        ("fond", "10x15"): str(fonds / "10x15_background.jpg"),
        ("fond", "strip"): str(fonds / "strips_background.jpg"),
    })
    monkeypatch.setattr(tr, "_RACINE_PAR_COUCHE", {
        "overlay": str(overlays),
        "fond": str(fonds),
    })
    # Les routes lisent PATH_OVERLAYS depuis le module importé — on patch aussi.
    monkeypatch.setattr(tr, "PATH_OVERLAYS", str(overlays))

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), str(overlays), str(fonds)


class TestUpload:
    def test_upload_png_valide(self, client):
        c, _, _ = client
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
        c, _, _ = client
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
        c, _, _ = client
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
        c, _, _ = client
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
        c, overlays, _ = client
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
        c, _, _ = client
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
        c, _, _ = client
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


class TestMigrationCouche:
    """La colonne `couche` doit être ajoutée aux bases créées avant son introduction."""

    def _creer_ancienne_base(self, chemin: str) -> None:
        import sqlite3
        conn = sqlite3.connect(chemin)
        conn.execute("""CREATE TABLE template (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('10x15', 'strip')),
            fichier TEXT NOT NULL UNIQUE,
            actif INTEGER NOT NULL DEFAULT 0,
            uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
            taille_octets INTEGER NOT NULL DEFAULT 0
        )""")
        conn.execute(
            "INSERT INTO template (nom, type, fichier) VALUES ('Mariage', '10x15', 'm.png')"
        )
        conn.commit()
        conn.close()

    def test_ancienne_base_migree_en_overlay(self, tmp_path):
        import sqlite3
        db = str(tmp_path / "admin.db")
        self._creer_ancienne_base(db)

        from web.db import init_db
        init_db(path=db)  # ne doit pas lever, et ajouter la colonne

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT couche FROM template WHERE nom = 'Mariage'").fetchone()
        conn.close()
        assert row["couche"] == "overlay"

    def test_init_db_idempotent_sur_base_migree(self, tmp_path):
        db = str(tmp_path / "admin.db")
        self._creer_ancienne_base(db)
        from web.db import init_db
        init_db(path=db)
        init_db(path=db)  # 2e passage : ne doit pas lever

    def test_base_neuve_a_la_colonne(self, tmp_path):
        import sqlite3
        db = str(tmp_path / "neuve.db")
        from web.db import init_db
        init_db(path=db)
        conn = sqlite3.connect(db)
        colonnes = {r[1] for r in conn.execute("PRAGMA table_info(template)")}
        conn.close()
        assert "couche" in colonnes


class TestUploadFond:
    def test_upload_fond_jpg_dans_dossier_fonds(self, client):
        c, _, fonds = client
        data = {
            "nom": "Fond mariage",
            "type": "10x15",
            "couche": "fond",
            "fichier": (io.BytesIO(_jpg_bytes()), "fond.jpg"),
        }
        r = c.post("/templates/upload", data=data,
                   headers=HEADERS, content_type="multipart/form-data",
                   follow_redirects=True)
        assert r.status_code == 200
        assert os.path.isfile(os.path.join(fonds, "fond__10x15__fond.jpg"))

    def test_upload_fond_png_accepte(self, client):
        c, _, fonds = client
        data = {
            "nom": "Fond png",
            "type": "strip",
            "couche": "fond",
            "fichier": (io.BytesIO(_png_bytes()), "fond.png"),
        }
        r = c.post("/templates/upload", data=data,
                   headers=HEADERS, content_type="multipart/form-data",
                   follow_redirects=True)
        assert r.status_code == 200
        assert os.path.isfile(os.path.join(fonds, "fond__strip__fond.png"))

    def test_upload_overlay_jpg_refuse(self, client):
        c, overlays, _ = client
        data = {
            "nom": "Mauvais overlay",
            "type": "10x15",
            "couche": "overlay",
            "fichier": (io.BytesIO(_jpg_bytes()), "cadre.jpg"),
        }
        c.post("/templates/upload", data=data,
               headers=HEADERS, content_type="multipart/form-data",
               follow_redirects=True)
        assert not os.path.isfile(os.path.join(overlays, "overlay__10x15__cadre.jpg"))

    def test_upload_couche_inconnue_refuse(self, client):
        c, overlays, fonds = client
        data = {
            "nom": "X",
            "type": "10x15",
            "couche": "cadre",
            "fichier": (io.BytesIO(_png_bytes()), "x.png"),
        }
        c.post("/templates/upload", data=data,
               headers=HEADERS, content_type="multipart/form-data",
               follow_redirects=True)
        assert os.listdir(overlays) == [] and os.listdir(fonds) == []


def _uploader(c, nom, type_t, couche, contenu, nom_fichier):
    """Helper : upload + retourne l'id du template créé."""
    c.post("/templates/upload", data={
        "nom": nom, "type": type_t, "couche": couche,
        "fichier": (io.BytesIO(contenu), nom_fichier),
    }, headers=HEADERS, content_type="multipart/form-data", follow_redirects=True)
    import sqlite3
    import web.db
    conn = sqlite3.connect(web.db.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM template WHERE nom = ?", (nom,)).fetchone()
    conn.close()
    return row["id"]


class TestActivationFond:
    def test_activer_fond_copie_vers_cible_bg(self, client):
        c, _, fonds = client
        tid = _uploader(c, "FondM", "10x15", "fond", _jpg_bytes(), "f.jpg")
        r = c.post(f"/templates/activer/{tid}", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert os.path.isfile(os.path.join(fonds, "10x15_background.jpg"))

    def test_activation_independante_entre_couches(self, client):
        """Activer un fond 10x15 ne doit PAS désactiver l'overlay 10x15."""
        c, overlays, _ = client
        tid_ov = _uploader(c, "Cadre", "10x15", "overlay", _png_bytes(), "c.png")
        tid_fd = _uploader(c, "Fond", "10x15", "fond", _jpg_bytes(), "f.jpg")
        c.post(f"/templates/activer/{tid_ov}", headers=HEADERS, follow_redirects=True)
        c.post(f"/templates/activer/{tid_fd}", headers=HEADERS, follow_redirects=True)

        import sqlite3
        import web.db
        conn = sqlite3.connect(web.db.DB_PATH)
        actifs = conn.execute("SELECT COUNT(*) FROM template WHERE actif = 1").fetchone()[0]
        conn.close()
        assert actifs == 2  # un par couche


class TestDesactivation:
    def test_desactiver_supprime_cible_et_actif(self, client):
        c, overlays, _ = client
        tid = _uploader(c, "Cadre", "10x15", "overlay", _png_bytes(), "c.png")
        c.post(f"/templates/activer/{tid}", headers=HEADERS, follow_redirects=True)
        cible = os.path.join(overlays, "10x15_overlay.png")
        assert os.path.isfile(cible)

        r = c.post("/templates/desactiver/overlay/10x15",
                   headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert not os.path.exists(cible)

        import sqlite3
        import web.db
        conn = sqlite3.connect(web.db.DB_PATH)
        actifs = conn.execute("SELECT COUNT(*) FROM template WHERE actif = 1").fetchone()[0]
        conn.close()
        assert actifs == 0

    def test_desactiver_idempotent_si_deja_aucun(self, client):
        c, _, _ = client
        r = c.post("/templates/desactiver/fond/strip",
                   headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200  # no-op poli, pas d'erreur

    def test_desactiver_couche_inconnue_404(self, client):
        c, _, _ = client
        r = c.post("/templates/desactiver/cadre/10x15", headers=HEADERS)
        assert r.status_code == 404

    def test_desactiver_type_inconnu_404(self, client):
        c, _, _ = client
        r = c.post("/templates/desactiver/overlay/13x18", headers=HEADERS)
        assert r.status_code == 404


class TestPageDeuxCouches:
    def test_page_contient_sections_et_desactivation(self, client):
        c, _, _ = client
        r = c.get("/templates/", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "Overlays" in html
        assert "Fonds" in html
        assert "/templates/desactiver/overlay/10x15" in html
        assert "/templates/desactiver/fond/strip" in html

    def test_etat_aucun_affiche_par_defaut(self, client):
        c, _, _ = client
        r = c.get("/templates/", headers=HEADERS)
        assert "Aucun" in r.get_data(as_text=True)


class TestAutoImport:
    def test_auto_import_decouvre_fichier_sur_disque(self, client):
        c, overlays, _ = client
        # Simuler un fichier d'overlay d'origine présent sur le disque
        cible = os.path.join(overlays, "10x15_overlay.png")
        with open(cible, "wb") as f:
            f.write(_png_bytes())

        # Charger la page des templates (ce qui déclenche la synchronisation)
        r = c.get("/templates/", headers=HEADERS)
        assert r.status_code == 200
        html = r.get_data(as_text=True)

        # Le template d'origine doit avoir été importé et affiché comme actif
        assert "Gabarit" in html
        assert "Actif : Gabarit" in html

        # Vérifier en DB
        from web.db import connexion
        with connexion() as conn:
            row = conn.execute(
                "SELECT nom, actif, fichier FROM template WHERE couche = 'overlay' AND type = '10x15'"
            ).fetchone()
        assert row["nom"] == "Gabarit d'origine (10x15)"
        assert row["actif"] == 1
        assert "origine" in row["fichier"]
