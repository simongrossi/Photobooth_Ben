"""test_web_systeme.py — contrôle du kiosque : liste blanche, exécution, état."""
from __future__ import annotations

import base64
import subprocess
import time
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

    def test_refuse_redemarrage_pendant_session(self, monkeypatch):
        heartbeat = {
            "online": True,
            "heartbeat_ts": time.time(),
            "session_active": True,
            "etat": "DECOMPTE",
        }
        monkeypatch.setattr(systeme.ecrans, "lire_etat_kiosque", lambda: heartbeat)
        appels = []
        monkeypatch.setattr(
            systeme.subprocess,
            "run",
            lambda *args, **kwargs: appels.append(args) or SimpleNamespace(returncode=0),
        )

        ok, message = systeme.executer_action("redemarrer-kiosque")
        assert ok is False
        assert "DECOMPTE" in message
        assert appels == []

    def test_heartbeat_perime_autorise_recuperation(self, monkeypatch):
        heartbeat = {
            "online": True,
            "heartbeat_ts": 1.0,
            "session_active": True,
            "etat": "FIN",
        }
        monkeypatch.setattr(systeme.ecrans, "lire_etat_kiosque", lambda: heartbeat)
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0))
        assert systeme.executer_action("redemarrer-kiosque")[0] is True


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
    from core import ecrans
    monkeypatch.setattr(ecrans, "ETAT_KIOSQUE_PATH", str(data / "kiosque_etat.json"))
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

    def test_dashboard_affiche_heartbeat_et_verrouille_boutons(self, client, monkeypatch):
        heartbeat = {
            "online": True,
            "heartbeat_ts": time.time(),
            "derniere_activite_ts": time.time() - 3,
            "session_active": True,
            "etat": "VALIDATION",
            "camera_connected": True,
            "arduino_enabled": True,
            "arduino_available": True,
            "dernier_tirage_reussi_ts": time.time() - 20,
            "dernier_tirage_reussi_mode": "10x15",
        }
        monkeypatch.setattr(systeme.ecrans, "lire_etat_kiosque", lambda: heartbeat)
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0, stdout="active\n"))

        html = client.get("/dashboard/", headers=HEADERS_OK).get_data(as_text=True)
        assert "Écran courant : <strong>VALIDATION</strong>" in html
        assert "Caméra : connectée" in html
        assert "Arduino : connecté" in html
        assert "Dernier tirage" in html
        assert "Session en cours" in html
        assert html.count("disabled") >= 3
