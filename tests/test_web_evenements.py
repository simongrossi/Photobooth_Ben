"""Tests de gestion, activation, filtrage et export des événements."""
from __future__ import annotations

import base64
import io
import json
import zipfile

import pytest
from PIL import Image

from web.app import create_app

HEADERS = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}


@pytest.fixture
def contexte(tmp_path, monkeypatch):
    data = tmp_path / "data"
    d10 = data / "print" / "print_10x15"
    dstrip = data / "print" / "print_strip"
    raw = data / "raw"
    for dossier in (d10, dstrip, raw):
        dossier.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")
    import config
    import web.db
    import web.routes.gallery as gallery

    monkeypatch.setattr(config, "PATH_DATA", str(data))
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(gallery, "PATH_PRINT", str(data / "print"))
    monkeypatch.setattr(gallery, "_RACINES_AUTORISEES", {
        "10x15": str(d10),
        "strip": str(dstrip),
        "raw": str(raw),
    })
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), data, d10, raw


def _creer(client, nom="Mariage Alice & Ben", tags="mariage, Lyon"):
    return client.post("/evenements/creer", headers=HEADERS, data={
        "nom": nom,
        "debut": "2026-07-18T15:00",
        "fin": "2026-07-19T03:00",
        "tags": tags,
        "notes": "Salle des fêtes",
    }, follow_redirects=True)


def _id_evenement():
    from web.evenements import lister_evenements
    return lister_evenements()[0].id


def test_creation_et_tags(contexte):
    client, _, _, _ = contexte
    reponse = _creer(client)
    assert reponse.status_code == 200
    assert "Mariage Alice &amp; Ben" in reponse.get_data(as_text=True)

    from web.evenements import lister_evenements
    evenement = lister_evenements()[0]
    assert evenement.statut == "brouillon"
    assert evenement.tags == ["Lyon", "mariage"]


def test_activation_exclusive_et_fichier_partage(contexte):
    client, data, _, _ = contexte
    _creer(client, "Premier")
    premier = _id_evenement()
    _creer(client, "Second")
    second = next(e.id for e in __import__("web.evenements", fromlist=["lister_evenements"]).lister_evenements() if e.nom == "Second")

    client.post(f"/evenements/{premier}/activer", headers=HEADERS)
    client.post(f"/evenements/{second}/activer", headers=HEADERS)

    from web.evenements import lister_evenements
    evenements = {e.id: e for e in lister_evenements()}
    assert evenements[second].statut == "actif"
    assert evenements[premier].statut == "termine"
    actif = json.loads((data / "evenement_actif.json").read_text(encoding="utf-8"))
    assert actif["id"] == second


def test_terminer_retire_le_fichier_actif(contexte):
    client, data, _, _ = contexte
    _creer(client)
    evenement_id = _id_evenement()
    client.post(f"/evenements/{evenement_id}/activer", headers=HEADERS)
    client.post(f"/evenements/{evenement_id}/terminer", headers=HEADERS)
    assert not (data / "evenement_actif.json").exists()


def test_dates_invalides_refusees(contexte):
    client, _, _, _ = contexte
    reponse = client.post("/evenements/creer", headers=HEADERS, data={
        "nom": "Impossible",
        "debut": "2026-07-19T03:00",
        "fin": "2026-07-18T15:00",
    }, follow_redirects=True)
    assert "postérieure" in reponse.get_data(as_text=True)


def test_filtres_dashboard_et_galerie(contexte):
    client, data, d10, _ = contexte
    _creer(client)
    evenement_id = _id_evenement()
    session_id = "2026-07-18_18h42_10"
    (data / "sessions.jsonl").write_text(json.dumps({
        "session_id": session_id,
        "mode": "10x15",
        "issue": "printed",
        "nb_photos": 1,
        "duree_s": 30,
        "ts": "2026-07-18 18:42:30",
        "event_id": evenement_id,
        "event_name": "Mariage Alice & Ben",
        "event_tags": ["mariage", "Lyon"],
    }) + "\n", encoding="utf-8")
    Image.new("RGB", (20, 20)).save(d10 / f"montage_10x15_{session_id}.jpg")

    galerie = client.get(f"/galerie/?evenement={evenement_id}", headers=HEADERS)
    assert "Mariage Alice &amp; Ben" in galerie.get_data(as_text=True)
    assert client.get("/galerie/?tag=inconnu", headers=HEADERS).get_data(as_text=True).count("montage_10x15") == 0


def test_export_zip(contexte):
    client, data, d10, raw = contexte
    _creer(client)
    evenement_id = _id_evenement()
    session_id = "2026-07-18_18h42_10"
    session = {
        "session_id": session_id, "mode": "10x15", "issue": "printed",
        "nb_photos": 1, "duree_s": 30, "ts": "2026-07-18 18:42:30",
        "event_id": evenement_id, "event_name": "Mariage Alice & Ben", "event_tags": ["mariage"],
    }
    (data / "sessions.jsonl").write_text(json.dumps(session) + "\n", encoding="utf-8")
    Image.new("RGB", (20, 20)).save(d10 / f"montage_10x15_{session_id}.jpg")
    Image.new("RGB", (20, 20)).save(raw / f"photo_{session_id}_1.jpg")

    reponse = client.get(f"/evenements/{evenement_id}/export.zip?inclure_raw=1", headers=HEADERS)
    assert reponse.status_code == 200
    with zipfile.ZipFile(io.BytesIO(reponse.data)) as archive:
        noms = archive.namelist()
        assert "manifest.json" in noms
        assert "sessions.csv" in noms
        assert any(nom.startswith("photos/10x15/") for nom in noms)
        assert any(nom.startswith("photos/raw/") for nom in noms)
