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
