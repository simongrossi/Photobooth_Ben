"""test_web_gallery.py — tests de la route galerie (listing, thumbs, sécurité chemins)."""
from __future__ import annotations

import base64
import io
import json
import os
import zipfile

import pytest
from PIL import Image

from web import exports
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
        assert b"Aucune image" in r.data

    def test_masquer_sorties_de_tests(self, client):
        import web.routes.gallery as gallery

        dossier_strip = gallery._RACINES_AUTORISEES["strip"]
        _png(os.path.join(dossier_strip, "montage_strip_test_session_CLEAN.jpg"))
        _png(os.path.join(dossier_strip, "montage_strip_2026-04-20_22h10_01_CLEAN.jpg"))
        _png(os.path.join(dossier_strip, "montage_strip_soakstrip_42_CLEAN.jpg"))

        r = client.get("/galerie/", headers=HEADERS)

        assert b"montage_strip_test_session" not in r.data
        assert b"montage_strip_2026-04-20_22h10_01" not in r.data
        assert b"montage_strip_soakstrip_42" not in r.data


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

    def test_thumb_strip_conserve_300_px_de_large(self, client):
        import web.routes.gallery as gallery

        chemin = os.path.join(gallery._RACINES_AUTORISEES["strip"], "strip_001.jpg")
        _png(chemin, taille=(600, 1800))

        r = client.get("/galerie/thumb/strip/strip_001.jpg", headers=HEADERS)

        assert r.status_code == 200
        img = Image.open(io.BytesIO(r.data))
        assert img.size == (300, 900)

    def test_thumb_est_cache_apres_premiere_generation(self, client, monkeypatch):
        import web.routes.gallery as gallery

        vrai_open = gallery.Image.open
        appels = []

        def compter_open(*args, **kwargs):
            appels.append(args[0])
            return vrai_open(*args, **kwargs)

        monkeypatch.setattr(gallery.Image, "open", compter_open)

        premier = client.get("/galerie/thumb/10x15/photo_001.jpg", headers=HEADERS)
        second = client.get("/galerie/thumb/10x15/photo_001.jpg", headers=HEADERS)

        assert premier.status_code == second.status_code == 200
        assert premier.data == second.data
        assert len(appels) == 1
        assert "max-age=86400" in second.headers["Cache-Control"]


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
        
        # 1. Tout (défaut)
        r = c.get("/galerie/", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "m1.jpg" in html
        assert "raw_1.jpg" in html
        assert "del_1.jpg" in html
        assert "ret_1.jpg" in html
        assert '?type=all" class="btn-filter active"' in html
        
        # 2. Montages
        r = c.get("/galerie/?type=montages", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "m1.jpg" in html
        assert "raw_1.jpg" not in html

        # 3. Raw
        r = c.get("/galerie/?type=raw", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "raw_1.jpg" in html
        assert "m1.jpg" not in html
        
        # 4. Deleted
        r = c.get("/galerie/?type=deleted", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "del_1.jpg" in html
        assert "m1.jpg" not in html
        
        # 5. Retake
        r = c.get("/galerie/?type=retake", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "ret_1.jpg" in html
        assert "m1.jpg" not in html

    def test_filtre_inconnu_revient_sur_tout(self, client):
        r = client.get("/galerie/?type=inconnu", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "photo_001.jpg" in html
        assert "strip_001.jpg" in html
        assert '?type=all" class="btn-filter active"' in html


class TestExportZip:
    def _telecharger(self, client, requete="/galerie/export.zip", headers=HEADERS):
        """Suit le flux différé : lancement → attente de la tâche → fichier."""
        lancement = client.get(requete, headers=headers)
        assert lancement.status_code == 302, lancement.status_code
        tache_id = lancement.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
        assert exports.attendre(tache_id).etat == "pret"
        return client.get(f"/export/{tache_id}/fichier", headers=headers)

    def _archive(self, reponse):
        return zipfile.ZipFile(io.BytesIO(reponse.data))

    def test_zip_contient_toutes_les_images_du_filtre(self, client):
        r = self._telecharger(client)
        assert r.status_code == 200
        assert r.mimetype == "application/zip"
        with self._archive(r) as archive:
            noms = set(archive.namelist())
        assert "photos/10x15/photo_001.jpg" in noms
        assert "photos/strip/strip_001.jpg" in noms

    def test_zip_respecte_le_filtre_de_type(self, client):
        r = self._telecharger(client, "/galerie/export.zip?type=montages")
        with self._archive(r) as archive:
            photos = sorted(n for n in archive.namelist() if n.startswith("photos/"))
        assert photos == ["photos/10x15/photo_001.jpg", "photos/strip/strip_001.jpg"]

    def test_zip_type_sans_image_redirige_vers_la_galerie(self, client):
        # Aucune photo brute dans la fixture : le filtre doit vider la sélection.
        r = client.get("/galerie/export.zip?type=raw", headers=HEADERS)
        assert r.status_code == 302
        assert "/export/" not in r.headers["Location"]

    def test_manifeste_decrit_les_filtres(self, client):
        r = self._telecharger(client, "/galerie/export.zip?type=montages")
        with self._archive(r) as archive:
            manifeste = json.loads(archive.read("manifest.json"))
        assert manifeste["filtres"]["type"] == "montages"
        assert manifeste["nb_fichiers"] == len(manifeste["fichiers"])

    def test_selection_vide_redirige_avec_message(self, client):
        r = client.get("/galerie/export.zip?evenement=inconnu", headers=HEADERS)
        assert r.status_code == 302
        assert "/galerie/" in r.headers["Location"]

    def test_nom_de_fichier_rappelle_le_filtre(self, client):
        r = self._telecharger(client, "/galerie/export.zip?type=montages")
        assert "photobooth-montages-" in r.headers["Content-Disposition"]

    def test_lecture_seule_autorisee(self, client):
        assert self._telecharger(client, headers={}).status_code == 200

    def test_page_de_suivi_affiche_la_progression(self, client):
        lancement = client.get("/galerie/export.zip", headers=HEADERS)
        tache_id = lancement.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
        page = client.get(f"/export/{tache_id}", headers=HEADERS)
        assert page.status_code == 200
        assert b"progression__barre" in page.data
        exports.attendre(tache_id)
        etat = client.get(f"/export/{tache_id}/etat", headers=HEADERS).get_json()
        assert etat["etat"] == "pret"
        assert etat["pourcent"] == 100
        assert etat["faits"] == etat["total"] == 2

    def test_disque_plein_refuse_avec_un_message(self, client, monkeypatch):
        """Refus lisible plutôt qu'un export voué à saturer le disque."""
        def _plein(fichiers, dossier):
            raise exports.EspaceInsuffisant(2_900_000_000, 1024, 512 * 1024 * 1024)

        monkeypatch.setattr(exports, "verifier_espace", _plein)
        r = client.get("/galerie/export.zip", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert "Disque trop plein" in r.get_data(as_text=True)
        assert "2.7 Go d&#39;archive" in r.get_data(as_text=True)

    def test_tache_inconnue(self, client):
        assert client.get("/export/inexistante", headers=HEADERS).status_code == 404
        assert client.get("/export/inexistante/etat", headers=HEADERS).status_code == 404
        assert client.get("/export/inexistante/fichier", headers=HEADERS).status_code == 404

    def test_refuse_sans_acces_libre_ni_admin(self, client, monkeypatch):
        monkeypatch.setenv("PHOTOBOOTH_ACCES_LIBRE", "0")
        r = client.get("/galerie/export.zip")
        assert r.status_code == 401
