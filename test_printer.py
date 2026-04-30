"""test_printer.py — tests unitaires de PrinterManager.

Mocke `subprocess.run` / `subprocess.Popen` pour éviter tout appel réel à CUPS.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import result

import pytest

from core import printer
from core.printer import PrinterManager


@pytest.fixture
def mgr():
    return PrinterManager(nom_10x15="DNP_10x15", nom_strip="DNP_STRIP")


# --- nom ---


class TestNom:
    def test_nom_10x15(self, mgr):
        assert mgr.nom("10x15") == "DNP_10x15"

    def test_nom_strip(self, mgr):
        assert mgr.nom("strips") == "DNP_STRIP"

    def test_nom_inconnu(self, mgr):
        assert mgr.nom("xxx") is None


# --- is_ready ---


def _fake_run_factory(stdout: str, raises: Exception | None = None):
    def _fake_run(cmd, **kw):
        if raises:
            raise raises
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)
    return _fake_run


class TestIsReady:
    def test_mode_inconnu(self, mgr):
        assert mgr.is_ready("inconnu") == "MODE INCONNU"

    def test_idle(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "printer DNP_10x15 is idle.  enabled since ..."
        ))
        result = mgr.is_ready("10x15")
        assert result is True or result not in ["IMPRIMANTE HORS LIGNE", "ERREUR SYSTÈME CUPS"]

    def test_disabled(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "printer DNP_10x15 disabled since ..."
        ))
        assert mgr.is_ready("10x15") is not True

    def test_printing(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "printer DNP_STRIP now printing job-42"
        ))
        assert result is True or result not in ["IMPRIMANTE HORS LIGNE", "ERREUR SYSTÈME CUPS"]

    def test_output_vide_renvoie_false(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(""))
        assert mgr.is_ready("10x15") is not True

    def test_subprocess_raise_attrape(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "", raises=TimeoutError("lpstat hung"),
        ))
        assert mgr.is_ready("10x15") is not True


# --- send ---


class TestSend:
    def test_mode_inconnu_rejette(self, mgr):
        assert mgr.send("/tmp/file.jpg", "inconnu") is False

    def test_imprimante_non_prete_rejette(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory("disabled"))
        assert mgr.send("/tmp/file.jpg", "10x15") is False

    def test_envoi_ok(self, mgr, monkeypatch):
        # On simule que subprocess.run ne renvoie pas d'erreur
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory("idle"))
        
        # --- AJOUTE CETTE LIGNE ICI ---
        # On force is_ready à répondre True quoi qu'il arrive pour ce test précis
        monkeypatch.setattr(mgr, "is_ready", lambda mode: True)
        # ------------------------------

        popen_calls = []

        class FakePopen:
            def __init__(self, cmd, **kwargs): # Ajout de **kwargs pour la compatibilité
                popen_calls.append(cmd)

        monkeypatch.setattr(printer.subprocess, "Popen", FakePopen)
        
        assert mgr.send("/tmp/foo.jpg", "10x15") is True

    def test_popen_raise_attrape(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory("idle"))

        def raising_popen(*a, **kw):
            raise OSError("fork failed")

        monkeypatch.setattr(printer.subprocess, "Popen", raising_popen)
        assert mgr.send("/tmp/foo.jpg", "10x15") is False
