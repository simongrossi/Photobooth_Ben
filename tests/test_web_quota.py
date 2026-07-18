"""test_web_quota.py — tests du compteur/quota d'impressions dans l'admin web.

Couvre : la carte quota du dashboard et la route POST de déblocage
(auth requise, incrément persisté, cohérence avec la lecture côté kiosque).
"""
from __future__ import annotations

import base64
import json

import pytest

from core import quota
from web.app import create_app

HEADERS_OK = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    data_path = tmp_path / "data"
    data_path.mkdir()
    (data_path / "print").mkdir()

    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")
    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data_path))
    monkeypatch.setattr(config, "QUOTA_IMPRESSIONS_INCREMENT", 100)
    import web.db
    monkeypatch.setattr(web.db, "DB_PATH", str(data_path / "admin.db"))

    chemin_quota = str(data_path / "quota_impressions.json")
    monkeypatch.setattr(quota, "PATH_QUOTA", chemin_quota)
    monkeypatch.setattr(quota, "QUOTA_INITIAL", 100)

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), chemin_quota


class TestDashboardQuota:
    def test_affiche_la_carte_quota(self, ctx):
        c, _ = ctx
        r = c.get("/dashboard/", headers=HEADERS_OK)
        assert r.status_code == 200
        assert b"Impressions DNP" in r.data
        assert "Débloquer".encode() in r.data

    def test_affiche_consommees_et_restant(self, ctx):
        c, _ = ctx
        quota.enregistrer_tirage(30)
        page = c.get("/dashboard/", headers=HEADERS_OK).get_data(as_text=True)
        assert "30" in page      # consommées
        assert "70" in page      # restant
        assert "100" in page     # quota


class TestDebloquerQuota:
    def test_sans_auth_refuse(self, ctx):
        c, chemin = ctx
        r = c.post("/dashboard/quota/debloquer")
        assert r.status_code == 401

    def test_avec_auth_augmente_le_quota(self, ctx):
        c, chemin = ctx
        r = c.post("/dashboard/quota/debloquer", headers=HEADERS_OK)
        assert r.status_code == 302
        with open(chemin, encoding="utf-8") as f:
            assert json.load(f)["quota"] == 200

    def test_coherence_web_kiosque(self, ctx):
        """Le déblocage web est immédiatement visible côté kiosque (même fichier)."""
        c, _ = ctx
        quota.enregistrer_tirage(100)
        assert quota.quota_restant() == 0
        c.post("/dashboard/quota/debloquer", headers=HEADERS_OK)
        assert quota.quota_restant() == 100
