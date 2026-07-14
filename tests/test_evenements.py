"""Tests du partage d'événement actif et des métadonnées de session."""
from __future__ import annotations

import json

from core.evenements import charger_evenement_actif
from core.session import SessionState, ecrire_metadata_session


def test_charger_evenement_actif(tmp_path):
    chemin = tmp_path / "evenement_actif.json"
    chemin.write_text(json.dumps({
        "id": "evt-1",
        "nom": "Mariage Alice & Ben",
        "slug": "mariage-alice-ben",
        "debut": "2026-07-18T15:00",
        "fin": "2026-07-19T03:00",
        "tags": ["mariage", "Lyon"],
    }), encoding="utf-8")

    evenement = charger_evenement_actif(str(chemin))

    assert evenement["id"] == "evt-1"
    assert evenement["tags"] == ["mariage", "Lyon"]


def test_evenement_actif_absent_ou_invalide(tmp_path):
    assert charger_evenement_actif(str(tmp_path / "absent.json")) is None
    invalide = tmp_path / "invalide.json"
    invalide.write_text("pas du json", encoding="utf-8")
    assert charger_evenement_actif(str(invalide)) is None


def test_metadata_session_contient_instantane_evenement(tmp_path, monkeypatch):
    import core.session as session_module

    monkeypatch.setattr(session_module, "PATH_DATA", str(tmp_path))
    session = SessionState(
        id_session_timestamp="2026-07-18_18h42_10",
        mode_actuel="10x15",
        evenement_id="evt-1",
        evenement_nom="Mariage Alice & Ben",
        evenement_tags=["mariage", "Lyon"],
    )

    ecrire_metadata_session(session, "printed", 1, 31.2)

    entree = json.loads((tmp_path / "sessions.jsonl").read_text(encoding="utf-8"))
    assert entree["event_id"] == "evt-1"
    assert entree["event_name"] == "Mariage Alice & Ben"
    assert entree["event_tags"] == ["mariage", "Lyon"]


def test_reset_efface_evenement_de_session():
    session = SessionState(
        evenement_id="evt-1",
        evenement_nom="Mariage",
        evenement_tags=["mariage"],
        evenement_charge=True,
    )
    session.reset_pour_accueil()
    assert session.evenement_id is None
    assert session.evenement_nom is None
    assert session.evenement_tags == []
    assert session.evenement_charge is False
