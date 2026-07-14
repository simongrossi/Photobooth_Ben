"""test_session.py — tests unitaires de core/session.py.

Couvre : l'enum Etat, le dataclass SessionState (reset), l'écriture JSONL
(ecrire_metadata_session), et le flow complet (terminer_session_et_revenir_accueil).
Isolation via monkeypatch de PATH_DATA vers tmp_path.
"""
from __future__ import annotations

import json
import os

import pytest

from core import session as sess
from core.session import (
    Etat, SessionState, ecrire_metadata_session, terminer_session_et_revenir_accueil,
)


@pytest.fixture
def session_vide():
    return SessionState(last_activity_ts=100.0)


@pytest.fixture
def isoler_path_data(monkeypatch, tmp_path):
    monkeypatch.setattr(sess, "PATH_DATA", str(tmp_path))
    return str(tmp_path)


# --- Etat enum ---


class TestEtat:
    def test_4_etats(self):
        assert {e.value for e in Etat} == {"ACCUEIL", "DECOMPTE", "VALIDATION", "FIN"}

    def test_comparaison_is(self):
        s = SessionState()
        assert s.etat is Etat.ACCUEIL


# --- SessionState ---


class TestSessionState:
    def test_defauts(self, session_vide):
        assert session_vide.etat is Etat.ACCUEIL
        assert session_vide.mode_actuel is None
        assert session_vide.photos_validees == []
        assert session_vide.last_activity_ts == 100.0

    def test_reset_pour_accueil(self, session_vide):
        session_vide.etat = Etat.FIN
        session_vide.mode_actuel = "strips"
        session_vide.photos_validees = ["a.jpg", "b.jpg"]
        session_vide.id_session_timestamp = "2026-04-20_12h00_00"
        session_vide.path_montage = "/tmp/x.jpg"
        session_vide.img_preview_cache = object()

        session_vide.reset_pour_accueil()

        assert session_vide.etat is Etat.ACCUEIL
        assert session_vide.mode_actuel is None
        assert session_vide.photos_validees == []
        assert session_vide.id_session_timestamp == ""
        assert session_vide.path_montage == ""
        assert session_vide.img_preview_cache is None

    def test_reset_preserve_last_activity_ts(self, session_vide):
        session_vide.last_activity_ts = 42.0
        session_vide.reset_pour_accueil()
        assert session_vide.last_activity_ts == 42.0


# --- ecrire_metadata_session ---


class TestEcrireMetadata:
    def test_append_ligne_jsonl(self, isoler_path_data, session_vide):
        session_vide.id_session_timestamp = "2026-04-21_14h00_00"
        session_vide.mode_actuel = "strips"

        ecrire_metadata_session(session_vide, "printed", 3, 78.5)

        chemin = os.path.join(isoler_path_data, "sessions.jsonl")
        assert os.path.exists(chemin)
        with open(chemin, encoding="utf-8") as f:
            ligne = f.readline()
        entry = json.loads(ligne)
        assert entry["session_id"] == "2026-04-21_14h00_00"
        assert entry["mode"] == "strips"
        assert entry["issue"] == "printed"
        assert entry["nb_photos"] == 3
        assert entry["duree_s"] == 78.5
        assert "ts" in entry

    def test_append_multiple(self, isoler_path_data, session_vide):
        session_vide.id_session_timestamp = "s1"
        ecrire_metadata_session(session_vide, "printed", 1, 40.0)
        session_vide.id_session_timestamp = "s2"
        ecrire_metadata_session(session_vide, "abandoned", 1, 20.0)

        chemin = os.path.join(isoler_path_data, "sessions.jsonl")
        with open(chemin, encoding="utf-8") as f:
            lignes = f.readlines()
        assert len(lignes) == 2
        assert json.loads(lignes[0])["issue"] == "printed"
        assert json.loads(lignes[1])["issue"] == "abandoned"

    def test_session_id_vide_serialise_null(self, isoler_path_data, session_vide):
        session_vide.id_session_timestamp = ""
        ecrire_metadata_session(session_vide, "capture_failed", 0, 5.0)

        chemin = os.path.join(isoler_path_data, "sessions.jsonl")
        with open(chemin, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["session_id"] is None

    def test_duree_arrondie_a_1_decimale(self, isoler_path_data, session_vide):
        ecrire_metadata_session(session_vide, "printed", 1, 12.345678)
        chemin = os.path.join(isoler_path_data, "sessions.jsonl")
        with open(chemin, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["duree_s"] == 12.3

    def test_chemin_invalide_ne_crashe_pas(self, monkeypatch, session_vide):
        """Si PATH_DATA pointe vers un dossier inaccessible, le log est warn, pas de crash."""
        monkeypatch.setattr(sess, "PATH_DATA", "/nonexistent/path/xxx")
        ecrire_metadata_session(session_vide, "printed", 1, 30.0)


# --- terminer_session_et_revenir_accueil ---


class TestTerminerSession:
    def test_ecrit_metadata_puis_reset(self, isoler_path_data, session_vide):
        session_vide.mode_actuel = "10x15"
        session_vide.photos_validees = ["p1.jpg"]
        session_vide.id_session_timestamp = "2026-04-21_15h00_00"
        session_vide.session_start_ts = 0.0
        session_vide.etat = Etat.FIN

        terminer_session_et_revenir_accueil(session_vide, "printed")

        # Metadata écrite
        chemin = os.path.join(isoler_path_data, "sessions.jsonl")
        with open(chemin, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["issue"] == "printed"
        assert entry["nb_photos"] == 1

        # Session reset
        assert session_vide.etat is Etat.ACCUEIL
        assert session_vide.mode_actuel is None
        assert session_vide.photos_validees == []
