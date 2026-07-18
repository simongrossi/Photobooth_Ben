"""test_web_systeme.py — contrôle du kiosque : liste blanche, exécution, état."""
from __future__ import annotations

import base64
import subprocess
from types import SimpleNamespace

import pytest

from web import systeme
from web.app import create_app

HEADERS_OK = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}


def _fake_run(returncode=0, stdout="", stderr=""):
    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return run


class TestListeBlanche:
    def test_action_inconnue_leve(self):
        with pytest.raises(ValueError):
            systeme.executer_action("rm-rf")

    def test_les_trois_actions_existent(self):
        assert set(systeme.ACTIONS) == {
            "redemarrer-kiosque", "arreter-kiosque", "redemarrer-machine",
        }

    def test_commandes_utilisent_sudo_n(self):
        for cmd in systeme.ACTIONS.values():
            assert cmd[1] == "-n"          # sudo non-interactif
            assert "systemctl" in cmd[2]


class TestExecution:
    def test_succes(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0))
        ok, msg = systeme.executer_action("redemarrer-kiosque")
        assert ok is True

    def test_echec_sudo(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run",
                            _fake_run(1, stderr="sudo: a password is required"))
        ok, msg = systeme.executer_action("arreter-kiosque")
        assert ok is False
        assert "password" in msg

    def test_timeout(self, monkeypatch):
        def run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 10)
        monkeypatch.setattr(systeme.subprocess, "run", run)
        ok, msg = systeme.executer_action("redemarrer-kiosque")
        assert ok is False

    def test_commande_absente(self, monkeypatch):
        def run(cmd, **kwargs):
            raise OSError("no such file")
        monkeypatch.setattr(systeme.subprocess, "run", run)
        ok, msg = systeme.executer_action("redemarrer-machine")
        assert ok is False


class TestEtatKiosque:
    def test_actif(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0, stdout="active\n"))
        assert systeme.etat_kiosque() == "active"

    def test_arrete(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(3, stdout="inactive\n"))
        assert systeme.etat_kiosque() == "inactive"

    def test_en_panne(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(3, stdout="failed\n"))
        assert systeme.etat_kiosque() == "failed"

    def test_indisponible(self, monkeypatch):
        def run(cmd, **kwargs):
            raise OSError("systemctl introuvable")
        monkeypatch.setattr(systeme.subprocess, "run", run)
        assert systeme.etat_kiosque() == "indisponible"


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")
    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    import web.db
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


class TestRoutesSysteme:
    def test_action_valide_redirige(self, client, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0))
        r = client.post("/dashboard/systeme/redemarrer-kiosque",
                        headers=HEADERS_OK, follow_redirects=True)
        assert r.status_code == 200

    def test_action_inconnue_404(self, client):
        assert client.post("/dashboard/systeme/pwn",
                           headers=HEADERS_OK).status_code == 404

    def test_sans_auth_401(self, client):
        assert client.post("/dashboard/systeme/redemarrer-kiosque").status_code == 401

    def test_viewer_ne_voit_pas_le_panneau(self, client, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0, stdout="active\n"))
        html = client.get("/dashboard/").get_data(as_text=True)
        assert "Contrôle du kiosque" not in html

    def test_admin_voit_le_panneau(self, client, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0, stdout="active\n"))
        html = client.get("/dashboard/", headers=HEADERS_OK).get_data(as_text=True)
        assert "Contrôle du kiosque" in html
        assert "/dashboard/systeme/redemarrer-machine" in html
