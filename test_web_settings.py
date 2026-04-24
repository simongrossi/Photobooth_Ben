"""test_web_settings.py — tests de l'éditeur d'overrides config."""
from __future__ import annotations

import base64
import json

import pytest

from web.app import create_app

HEADERS = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")
    overrides_path = str(data / "config_overrides.json")
    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", overrides_path)
    import web.db
    import web.routes.settings_route as sr
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(sr, "CONFIG_OVERRIDES_PATH", overrides_path)
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), overrides_path


class TestLecture:
    def test_affiche_les_reglages_whitelistes(self, ctx):
        c, _ = ctx
        r = c.get("/settings/", headers=HEADERS)
        assert r.status_code == 200
        assert b"TEMPS_DECOMPTE" in r.data
        assert b"NOM_IMPRIMANTE_10X15" in r.data


class TestEnregistrement:
    def test_ecrire_int_creer_le_fichier(self, ctx):
        c, overrides_path = ctx
        # On doit passer tous les champs pour simuler un submit complet.
        form = {
            "TEMPS_DECOMPTE": "4",
            "DELAI_SECURITE": "2.0",
            "NOM_IMPRIMANTE_10X15": "DNP_10x15",
            "NOM_IMPRIMANTE_STRIP": "DNP_STRIP",
            "TEMPS_ATTENTE_IMP": "20",
            "DUREE_IDLE_SLIDESHOW": "30",
            "DUREE_PAR_IMAGE_SLIDESHOW": "3.5",
            "NB_MAX_IMAGES_SLIDESHOW": "40",
            "STRIP_BURST_DELAI_S": "2.5",
            "WATERMARK_TEXT": "Mariage",
            "GRAIN_INTENSITE": "8",
            "SEUIL_DISQUE_CRITIQUE_MB": "500",
            "SEUIL_TEMP_CRITIQUE_C": "75",
            # booléens laissés décochés
        }
        r = c.post("/settings/", data=form, headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        with open(overrides_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["TEMPS_DECOMPTE"] == 4
        assert data["WATERMARK_TEXT"] == "Mariage"

    def test_entree_invalide_ignoree(self, ctx):
        c, overrides_path = ctx
        form = {
            "TEMPS_DECOMPTE": "pas un nombre",
            "DELAI_SECURITE": "2.0",
        }
        r = c.post("/settings/", data=form, headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        # DELAI_SECURITE a été enregistré
        import os
        if os.path.exists(overrides_path):
            with open(overrides_path) as f:
                data = json.load(f)
            assert "TEMPS_DECOMPTE" not in data

    def test_reset_supprime_le_fichier(self, ctx):
        c, overrides_path = ctx
        # Crée un fichier d'overrides
        with open(overrides_path, "w") as f:
            json.dump({"TEMPS_DECOMPTE": 5}, f)
        r = c.post("/settings/reset", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        import os
        assert not os.path.exists(overrides_path)


class TestWhitelist:
    def test_cle_hors_whitelist_ignoree(self, ctx):
        c, overrides_path = ctx
        form = {
            "CLE_MALVEILLANTE": "123",
            "DELAI_SECURITE": "3.0",
        }
        c.post("/settings/", data=form, headers=HEADERS)
        import os
        if os.path.exists(overrides_path):
            with open(overrides_path) as f:
                data = json.load(f)
            assert "CLE_MALVEILLANTE" not in data
