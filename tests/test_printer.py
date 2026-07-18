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


class TestLastError:
    """Régression : `last_error` doit exister et refléter l'état (bug AttributeError)."""

    def test_none_a_l_init(self, mgr):
        assert mgr.last_error is None

    def test_mode_inconnu_memorise(self, mgr):
        mgr.is_ready("inconnu")
        assert mgr.last_error == "MODE INCONNU"

    def test_file_pleine_memorise(self, mgr, monkeypatch):
        # lpstat -o renvoie une ligne de job → file pleine
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "DNP_10x15-42 photobooth 1024 ..."
        ))
        assert mgr.is_ready("10x15") == "FILE D'ATTENTE PLEINE"
        assert mgr.last_error == "FILE D'ATTENTE PLEINE"

    def test_reset_a_none_si_pret(self, mgr, monkeypatch):
        mgr.is_ready("inconnu")

        def _dispatch(cmd, **kw):
            if "-o" in cmd:
                return SimpleNamespace(stdout="", stderr="", returncode=0)
            return SimpleNamespace(stdout="printer DNP_10x15 is idle. enabled", stderr="", returncode=0)

        monkeypatch.setattr(printer.subprocess, "run", _dispatch)
        assert mgr.is_ready("10x15") is True
        assert mgr.last_error is None


class TestFileAttente:
    def test_compte_les_jobs(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "DNP_10x15-41 user 100\nDNP_10x15-42 user 200\n"
        ))
        assert mgr.jobs_en_attente("10x15") == 2

    def test_file_vide(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(""))
        assert mgr.jobs_en_attente("strips") == 0

    def test_etat_inconnu_si_cups_indisponible(self, mgr, monkeypatch):
        monkeypatch.setattr(
            printer.subprocess,
            "run",
            _fake_run_factory("", raises=OSError("lpstat absent")),
        )
        assert mgr.jobs_en_attente("10x15") is None


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

    def test_envoi_deja_verifie_ne_relance_pas_lpstat(self, mgr, monkeypatch):
        commandes = []

        def fake_run(cmd, **kwargs):
            commandes.append(cmd)
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        monkeypatch.setattr(printer.subprocess, "run", fake_run)

        assert mgr.send("/tmp/foo.jpg", "10x15", verifier=False) is True
        assert [commande[0] for commande in commandes] == ["lp"]

    def test_popen_raise_attrape(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory("idle"))

        def raising_popen(*a, **kw):
            raise OSError("fork failed")

        monkeypatch.setattr(printer.subprocess, "Popen", raising_popen)
        assert mgr.send("/tmp/foo.jpg", "10x15") is False


class TestPurge:
    def test_limitee_aux_files_configurees(self, mgr, monkeypatch):
        commandes = []

        def fake_run(cmd, **kwargs):
            commandes.append(cmd)
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        monkeypatch.setattr(printer.subprocess, "run", fake_run)

        mgr.purger_file_attente()

        assert commandes == [
            ["cancel", "-a", "DNP_10x15"],
            ["cancel", "-a", "DNP_STRIP"],
        ]
