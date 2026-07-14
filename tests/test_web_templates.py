"""test_web_templates.py — tests upload/activation/suppression de templates."""
from __future__ import annotations

import base64
import io
import os

import pytest
from PIL import Image

from web.app import create_app
from web.db import connexion

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
    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    monkeypatch.setattr(config, "PATH_OVERLAYS", str(overlays))
    monkeypatch.setattr(config, "PATH_FONDS", str(fonds))
    monkeypatch.setattr(config, "OVERLAY_10X15", str(overlays / "10x15_overlay.png"))
    monkeypatch.setattr(config, "OVERLAY_STRIPS", str(overlays / "strips_overlay.png"))
    monkeypatch.setattr(config, "BG_10X15_FILE", str(fonds / "10x15_background.jpg"))
    monkeypatch.setattr(config, "BG_STRIPS_FILE", str(fonds / "strips_background.jpg"))
    monkeypatch.setattr(config, "PATH_MISE_EN_PAGE_10X15", str(data / "mise_en_page_10x15.json"))
    monkeypatch.setattr(config, "PATH_MISE_EN_PAGE_STRIP", str(data / "mise_en_page_strip.json"))
    monkeypatch.setattr(config, "PATH_RAW", str(raw))
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
    monkeypatch.setattr(tr, "PATH_MISE_EN_PAGE_10X15", str(data / "mise_en_page_10x15.json"))
    monkeypatch.setattr(tr, "PATH_MISE_EN_PAGE_STRIP", str(data / "mise_en_page_strip.json"))
    monkeypatch.setattr(tr, "PATH_RAW", str(raw))

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


class TestAssociationEvenement:
    @staticmethod
    def _creer_evenement(statut="brouillon"):
        with connexion() as conn:
            conn.execute(
                "INSERT INTO evenement (id, nom, slug, debut, fin, statut) "
                "VALUES ('evt-1', 'Mariage Été', 'mariage-ete', "
                "'2026-07-18T15:00', '2026-07-19T03:00', ?)",
                (statut,),
            )

    def test_carte_propose_les_evenements(self, client):
        c, _, _ = client
        self._creer_evenement()
        c.post("/templates/upload", data={
            "nom": "Cadre fleurs", "type": "10x15", "couche": "overlay",
            "fichier": (io.BytesIO(_png_bytes()), "fleurs.png"),
        }, headers=HEADERS, content_type="multipart/form-data")

        html = c.get("/templates/", headers=HEADERS).get_data(as_text=True)
        assert "Associer à un événement" in html
        assert "Mariage Été" in html
        assert "/templates/associer/" in html

    def test_associer_a_evenement_actif_applique_le_template(self, client):
        c, overlays, _ = client
        self._creer_evenement(statut="actif")
        c.post("/templates/upload", data={
            "nom": "Cadre actif", "type": "10x15", "couche": "overlay",
            "fichier": (io.BytesIO(_png_bytes()), "actif.png"),
        }, headers=HEADERS, content_type="multipart/form-data")
        with connexion() as conn:
            template_id = conn.execute(
                "SELECT id FROM template WHERE nom = 'Cadre actif'"
            ).fetchone()["id"]

        reponse = c.post(
            f"/templates/associer/{template_id}",
            data={"evenement_id": "evt-1"},
            headers=HEADERS,
            follow_redirects=True,
        )

        assert reponse.status_code == 200
        assert "associé à « Mariage Été »" in reponse.get_data(as_text=True)
        assert os.path.isfile(os.path.join(overlays, "10x15_overlay.png"))
        with connexion() as conn:
            association = conn.execute(
                "SELECT template_id FROM evenement_template WHERE evenement_id = 'evt-1' "
                "AND type = '10x15' AND couche = 'overlay'"
            ).fetchone()
        assert association["template_id"] == template_id


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
        assert {"photo_x", "photo_y", "photo_largeur", "photo_hauteur"} <= colonnes
        assert "zones_strip" in colonnes


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


class TestEditeurMiseEnPage:
    def test_page_editeur_affiche_calques_et_controles(self, client):
        c, _, _ = client
        template_id = _uploader(c, "Cadre editable", "10x15", "overlay", _png_bytes(), "cadre.png")

        r = c.get(f"/templates/editer/{template_id}", headers=HEADERS)

        html = r.get_data(as_text=True)
        assert r.status_code == 200
        assert "Positionner la photo" in html
        assert 'name="photo_x"' in html
        assert f"/templates/fichier/{template_id}" in html

    def test_enregistre_geometrie_et_la_publie_si_actif(self, client):
        import json
        import web.db

        c, _, _ = client
        template_id = _uploader(c, "Cadre actif", "10x15", "overlay", _png_bytes(), "actif.png")
        c.post(f"/templates/activer/{template_id}", headers=HEADERS)

        r = c.post(f"/templates/editer/{template_id}", data={
            "photo_x": "120", "photo_y": "90",
            "photo_largeur": "1500", "photo_hauteur": "1000",
        }, headers=HEADERS, follow_redirects=True)

        assert r.status_code == 200
        with connexion() as conn:
            row = conn.execute(
                "SELECT photo_x, photo_y, photo_largeur, photo_hauteur FROM template WHERE id = ?",
                (template_id,),
            ).fetchone()
        assert tuple(row) == (120, 90, 1500, 1000)
        chemin = os.path.join(os.path.dirname(web.db.DB_PATH), "mise_en_page_10x15.json")
        with open(chemin, encoding="utf-8") as fichier:
            actif = json.load(fichier)
        assert actif["template_id"] == template_id
        assert actif["largeur"] == 1500

    def test_refuse_zone_hors_canvas(self, client):
        c, _, _ = client
        template_id = _uploader(c, "Cadre invalide", "10x15", "overlay", _png_bytes(), "ko.png")

        r = c.post(f"/templates/editer/{template_id}", data={
            "photo_x": "1700", "photo_y": "0",
            "photo_largeur": "500", "photo_hauteur": "500",
        }, headers=HEADERS, follow_redirects=True)

        assert "rester entièrement" in r.get_data(as_text=True)
        with connexion() as conn:
            row = conn.execute("SELECT photo_x FROM template WHERE id = ?", (template_id,)).fetchone()
        assert row["photo_x"] is None

    def test_overlay_actif_prioritaire_sur_fond(self, client):
        import json
        import web.db

        c, _, _ = client
        fond_id = _uploader(c, "Fond position", "10x15", "fond", _jpg_bytes(), "fond.jpg")
        overlay_id = _uploader(c, "Overlay position", "10x15", "overlay", _png_bytes(), "ov.png")
        for template_id, x in ((fond_id, 40), (overlay_id, 200)):
            c.post(f"/templates/editer/{template_id}", data={
                "photo_x": str(x), "photo_y": "100",
                "photo_largeur": "1200", "photo_hauteur": "800",
            }, headers=HEADERS)
            c.post(f"/templates/activer/{template_id}", headers=HEADERS)

        chemin = os.path.join(os.path.dirname(web.db.DB_PATH), "mise_en_page_10x15.json")
        with open(chemin, encoding="utf-8") as fichier:
            actif = json.load(fichier)
        assert actif["template_id"] == overlay_id
        assert actif["x"] == 200

    def test_photo_exemple_fallback_disponible(self, client):
        c, _, _ = client
        r = c.get("/templates/photo-exemple", headers=HEADERS)
        assert r.status_code == 200
        assert r.mimetype == "image/jpeg"

    def test_page_editeur_strip_affiche_trois_zones(self, client):
        c, _, _ = client
        template_id = _uploader(c, "Cadre strip", "strip", "overlay", _png_bytes(), "strip.png")

        r = c.get(f"/templates/editer/{template_id}", headers=HEADERS)

        html = r.get_data(as_text=True)
        assert r.status_code == 200
        assert "Positionner les trois photos" in html
        assert 'name="photo_1_x"' in html
        assert 'name="photo_2_x"' in html
        assert 'name="photo_3_x"' in html

    def test_enregistre_et_publie_geometrie_strip_active(self, client):
        import json
        import web.db

        c, _, _ = client
        template_id = _uploader(c, "Strip actif", "strip", "overlay", _png_bytes(), "actif-strip.png")
        c.post(f"/templates/activer/{template_id}", headers=HEADERS)
        donnees = {}
        for i, y in enumerate((50, 600, 1150), start=1):
            donnees.update({
                f"photo_{i}_x": "60", f"photo_{i}_y": str(y),
                f"photo_{i}_largeur": "480", f"photo_{i}_hauteur": "320",
            })

        r = c.post(
            f"/templates/editer/{template_id}", data=donnees,
            headers=HEADERS, follow_redirects=True,
        )

        assert r.status_code == 200
        with connexion() as conn:
            row = conn.execute(
                "SELECT zones_strip FROM template WHERE id = ?", (template_id,),
            ).fetchone()
        assert json.loads(row["zones_strip"])[1]["y"] == 600
        chemin = os.path.join(os.path.dirname(web.db.DB_PATH), "mise_en_page_strip.json")
        with open(chemin, encoding="utf-8") as fichier:
            actif = json.load(fichier)
        assert actif["template_id"] == template_id
        assert len(actif["photos"]) == 3

    def test_refuse_zone_strip_hors_canvas(self, client):
        c, _, _ = client
        template_id = _uploader(c, "Strip invalide", "strip", "fond", _jpg_bytes(), "ko-strip.jpg")
        donnees = {}
        for i, y in enumerate((0, 600, 1700), start=1):
            donnees.update({
                f"photo_{i}_x": "0", f"photo_{i}_y": str(y),
                f"photo_{i}_largeur": "500", f"photo_{i}_hauteur": "300",
            })

        r = c.post(
            f"/templates/editer/{template_id}", data=donnees,
            headers=HEADERS, follow_redirects=True,
        )

        assert "rester entièrement" in r.get_data(as_text=True)
        with connexion() as conn:
            row = conn.execute(
                "SELECT zones_strip FROM template WHERE id = ?", (template_id,),
            ).fetchone()
        assert row["zones_strip"] is None
