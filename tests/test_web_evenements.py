"""Tests de gestion, activation, filtrage et export des événements."""
from __future__ import annotations

import base64
import io
import json
import time
import os
import zipfile

import pytest
from PIL import Image

from web import backups, exports
from web.app import create_app

HEADERS = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}


@pytest.fixture
def contexte(tmp_path, monkeypatch):
    data = tmp_path / "data"
    d10 = data / "print" / "print_10x15"
    dstrip = data / "print" / "print_strip"
    raw = data / "raw"
    overlays = tmp_path / "overlays"
    fonds = tmp_path / "fonds"
    for dossier in (d10, dstrip, raw):
        dossier.mkdir(parents=True, exist_ok=True)
    overlays.mkdir()
    fonds.mkdir()

    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")
    import config
    import web.db
    import web.routes.gallery as gallery
    import web.routes.templates_route as templates_route

    monkeypatch.setattr(config, "PATH_DATA", str(data))
    # PATH_BACKUPS est figé à l'import : sans ce patch, les sauvegardes des
    # tests atterriraient dans le vrai data/backups/ du dépôt.
    monkeypatch.setattr(config, "PATH_BACKUPS", str(data / "backups"))
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(gallery, "PATH_PRINT", str(data / "print"))
    monkeypatch.setattr(gallery, "_RACINES_AUTORISEES", {
        "10x15": str(d10),
        "strip": str(dstrip),
        "raw": str(raw),
    })
    monkeypatch.setattr(templates_route, "_CIBLE_ACTIVE", {
        ("overlay", "10x15"): str(overlays / "10x15_overlay.png"),
        ("overlay", "strip"): str(overlays / "strips_overlay.png"),
        ("fond", "10x15"): str(fonds / "10x15_background.jpg"),
        ("fond", "strip"): str(fonds / "strips_background.jpg"),
    })
    monkeypatch.setattr(templates_route, "_RACINE_PAR_COUCHE", {
        "overlay": str(overlays),
        "fond": str(fonds),
    })
    monkeypatch.setattr(
        templates_route, "PATH_MISE_EN_PAGE_10X15", str(data / "mise_en_page_10x15.json")
    )
    monkeypatch.setattr(
        templates_route, "PATH_MISE_EN_PAGE_STRIP", str(data / "mise_en_page_strip.json")
    )
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), data, d10, raw


def _creer(client, nom="Mariage Alice & Ben", tags="mariage, Lyon", **templates):
    donnees = {
        "nom": nom,
        "debut": "2026-07-18T15:00",
        "fin": "2026-07-19T03:00",
        "tags": tags,
        "notes": "Salle des fêtes",
    }
    donnees.update(templates)
    return client.post("/evenements/creer", headers=HEADERS, data=donnees, follow_redirects=True)


def _id_evenement():
    from web.evenements import lister_evenements
    return lister_evenements()[0].id


def _statut(evenement_id):
    from web.evenements import trouver_evenement
    return trouver_evenement(evenement_id).statut


def _simuler_session_kiosque(monkeypatch, *, age_s=0.0):
    from web import session_guard

    heartbeat = {
        "online": True,
        "heartbeat_ts": time.time() - age_s,
        "session_active": True,
        "etat": "VALIDATION",
        "session_id": "session-test",
    }
    monkeypatch.setattr(session_guard.ecrans, "lire_etat_kiosque", lambda: heartbeat)


def test_creation_et_tags(contexte):
    client, _, _, _ = contexte
    reponse = _creer(client)
    assert reponse.status_code == 200
    assert "Mariage Alice &amp; Ben" in reponse.get_data(as_text=True)

    from web.evenements import lister_evenements
    evenement = lister_evenements()[0]
    assert evenement.statut == "brouillon"
    assert evenement.tags == ["Lyon", "mariage"]


def test_creation_propose_les_quatre_templates(contexte):
    client, _, _, _ = contexte
    page = client.get("/evenements/", headers=HEADERS).get_data(as_text=True)
    assert 'name="template_fond_10x15"' in page
    assert 'name="template_overlay_10x15"' in page
    assert 'name="template_fond_strip"' in page
    assert 'name="template_overlay_strip"' in page
    assert "Événement actif" not in page


def test_activation_applique_les_templates_associes(contexte):
    client, data, _, _ = contexte
    overlays = data.parent / "overlays"
    fonds = data.parent / "fonds"
    (overlays / "cadre.png").write_bytes(b"overlay-evenement")
    (fonds / "strip.jpg").write_bytes(b"fond-strip-evenement")
    from web.db import connexion
    with connexion() as conn:
        overlay_id = conn.execute(
            "INSERT INTO template (nom, type, couche, fichier) VALUES (?, ?, ?, ?)",
            ("Cadre mariage", "10x15", "overlay", "cadre.png"),
        ).lastrowid
        fond_strip_id = conn.execute(
            "INSERT INTO template (nom, type, couche, fichier) VALUES (?, ?, ?, ?)",
            ("Fond bandelettes", "strip", "fond", "strip.jpg"),
        ).lastrowid

    _creer(
        client,
        template_overlay_10x15=str(overlay_id),
        template_fond_strip=str(fond_strip_id),
    )
    evenement_id = _id_evenement()
    client.post(f"/evenements/{evenement_id}/activer", headers=HEADERS)

    assert (overlays / "10x15_overlay.png").read_bytes() == b"overlay-evenement"
    assert (fonds / "strips_background.jpg").read_bytes() == b"fond-strip-evenement"
    with connexion() as conn:
        associations = conn.execute(
            "SELECT type, couche, template_id FROM evenement_template WHERE evenement_id = ?",
            (evenement_id,),
        ).fetchall()
        actifs = conn.execute("SELECT id FROM template WHERE actif = 1 ORDER BY id").fetchall()
    assert len(associations) == 4
    assert [row["id"] for row in actifs] == sorted([overlay_id, fond_strip_id])

    page = client.get("/evenements/", headers=HEADERS).get_data(as_text=True)
    assert "Événement actif" in page
    assert "Cadre mariage" in page
    assert "Fond bandelettes" in page


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


def test_activation_http_refusee_pendant_session(contexte, monkeypatch):
    client, data, _, _ = contexte
    _creer(client, "Premier")
    premier = _id_evenement()
    client.post(f"/evenements/{premier}/activer", headers=HEADERS)
    _creer(client, "Second")
    from web.evenements import lister_evenements
    second = next(e.id for e in lister_evenements() if e.nom == "Second")
    _simuler_session_kiosque(monkeypatch)

    reponse = client.post(
        f"/evenements/{second}/activer",
        headers=HEADERS,
        follow_redirects=True,
    )

    evenements = {e.id: e for e in lister_evenements()}
    assert evenements[premier].statut == "actif"
    assert evenements[second].statut == "brouillon"
    assert json.loads((data / "evenement_actif.json").read_text())["id"] == premier
    assert "Action refusée" in reponse.get_data(as_text=True)


def test_cloture_http_refusee_et_boutons_desactives(contexte, monkeypatch):
    client, data, _, _ = contexte
    _creer(client)
    evenement_id = _id_evenement()
    client.post(f"/evenements/{evenement_id}/activer", headers=HEADERS)
    _simuler_session_kiosque(monkeypatch)

    reponse = client.post(
        f"/evenements/{evenement_id}/terminer",
        headers=HEADERS,
        follow_redirects=True,
    )

    from web.evenements import trouver_evenement
    assert trouver_evenement(evenement_id).statut == "actif"
    assert (data / "evenement_actif.json").exists()
    html = reponse.get_data(as_text=True)
    assert "Session photo en cours" in html
    assert '>Terminer</button>' in html and "disabled" in html


def test_heartbeat_perime_autorise_la_cloture(contexte, monkeypatch):
    client, data, _, _ = contexte
    _creer(client)
    evenement_id = _id_evenement()
    client.post(f"/evenements/{evenement_id}/activer", headers=HEADERS)
    _simuler_session_kiosque(monkeypatch, age_s=60)

    client.post(f"/evenements/{evenement_id}/terminer", headers=HEADERS)

    from web.evenements import trouver_evenement
    assert trouver_evenement(evenement_id).statut == "termine"
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


def test_export_disque_plein(contexte, monkeypatch):
    """Le refus s'affiche sur la page événements au lieu d'un export condamné."""
    client, data, d10, raw = contexte
    _creer(client)
    evenement_id = _id_evenement()

    def _plein(fichiers, dossier):
        raise exports.EspaceInsuffisant(2_900_000_000, 1024, 512 * 1024 * 1024)

    monkeypatch.setattr(exports, "verifier_espace", _plein)
    reponse = client.get(
        f"/evenements/{evenement_id}/export.zip?inclure_raw=1",
        headers=HEADERS, follow_redirects=True,
    )
    assert reponse.status_code == 200
    assert "Disque trop plein" in reponse.get_data(as_text=True)


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

    # L'export part en tâche de fond : on suit le lien de suivi puis le fichier.
    lancement = client.get(f"/evenements/{evenement_id}/export.zip?inclure_raw=1", headers=HEADERS)
    assert lancement.status_code == 302
    tache_id = lancement.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
    assert exports.attendre(tache_id).etat == "pret"
    reponse = client.get(f"/export/{tache_id}/fichier", headers=HEADERS)
    assert reponse.status_code == 200

    # L'export d'un événement est admin-only : un viewer anonyme ne doit pas
    # récupérer l'archive via son lien de suivi.
    assert client.get(f"/export/{tache_id}").status_code == 404
    assert client.get(f"/export/{tache_id}/fichier").status_code == 404
    with zipfile.ZipFile(io.BytesIO(reponse.data)) as archive:
        noms = archive.namelist()
        assert "manifest.json" in noms
        assert "sessions.csv" in noms
        assert any(nom.startswith("photos/10x15/") for nom in noms)
        assert any(nom.startswith("photos/raw/") for nom in noms)


def _photo_dans_evenement(client, data, d10, raw):
    """Crée un événement avec une session, un montage et une photo brute."""
    _creer(client)
    evenement_id = _id_evenement()
    session_id = "2026-08-24_18h42_10"
    session = {
        "session_id": session_id, "mode": "10x15", "issue": "printed",
        "nb_photos": 1, "duree_s": 30, "ts": "2026-08-24 18:42:30",
        "event_id": evenement_id, "event_name": "Mariage Alice & Ben", "event_tags": ["mariage"],
    }
    (data / "sessions.jsonl").write_text(json.dumps(session) + "\n", encoding="utf-8")
    Image.new("RGB", (20, 20)).save(d10 / f"montage_10x15_{session_id}.jpg")
    Image.new("RGB", (20, 20)).save(raw / f"photo_{session_id}_1.jpg")
    return evenement_id


class TestSauvegardeAutomatique:
    def test_terminer_produit_une_sauvegarde_complete(self, contexte):
        client, data, d10, raw = contexte
        evenement_id = _photo_dans_evenement(client, data, d10, raw)

        client.post(f"/evenements/{evenement_id}/terminer", headers=HEADERS)
        for tache_id in list(exports._taches):
            exports.attendre(tache_id)

        [sauvegarde] = backups.lister()
        with zipfile.ZipFile(sauvegarde.chemin) as archive:
            noms = archive.namelist()
        # « toutes les photos + bruts » : montages ET photos brutes.
        assert any(n.startswith("photos/10x15/") for n in noms)
        assert any(n.startswith("photos/raw/") for n in noms), "les photos brutes doivent être incluses"
        assert "manifest.json" in noms and "sessions.csv" in noms

    def test_terminer_reste_effectif_si_la_sauvegarde_echoue(self, contexte, monkeypatch):
        """Ne pas pouvoir sauvegarder ne doit jamais empêcher de terminer."""
        client, data, d10, raw = contexte
        evenement_id = _photo_dans_evenement(client, data, d10, raw)

        def _plein(fichiers, dossier):
            raise exports.EspaceInsuffisant(2_900_000_000, 1024, 512 * 1024 * 1024)

        monkeypatch.setattr(exports, "verifier_espace", _plein)
        reponse = client.post(
            f"/evenements/{evenement_id}/terminer", headers=HEADERS, follow_redirects=True,
        )
        assert "Sauvegarde impossible" in reponse.get_data(as_text=True)
        assert backups.lister() == []
        # L'événement est bien terminé malgré l'échec de la sauvegarde.
        assert _statut(evenement_id) == "termine"

    def test_bouton_manuel_regenere(self, contexte):
        client, data, d10, raw = contexte
        evenement_id = _photo_dans_evenement(client, data, d10, raw)

        reponse = client.post(f"/evenements/{evenement_id}/sauvegarder", headers=HEADERS)
        assert reponse.status_code == 302
        assert "/export/" in reponse.headers["Location"]
        for tache_id in list(exports._taches):
            exports.attendre(tache_id)
        assert len(backups.lister()) == 1

    def test_sauvegarde_survit_a_la_purge_des_taches(self, contexte):
        """Une sauvegarde n'est pas une archive temporaire : la purge l'épargne."""
        client, data, d10, raw = contexte
        evenement_id = _photo_dans_evenement(client, data, d10, raw)
        client.post(f"/evenements/{evenement_id}/sauvegarder", headers=HEADERS)
        for tache_id in list(exports._taches):
            exports.attendre(tache_id)
        [sauvegarde] = backups.lister()

        for tache_id in list(exports._taches):
            exports.oublier(tache_id)
        exports.demarrer("declencheur.zip", "", [])  # déclenche _purger

        assert os.path.exists(sauvegarde.chemin), "la purge ne doit pas toucher aux sauvegardes"

    def test_confirmation_de_copie_supprime(self, contexte):
        client, data, d10, raw = contexte
        evenement_id = _photo_dans_evenement(client, data, d10, raw)
        client.post(f"/evenements/{evenement_id}/sauvegarder", headers=HEADERS)
        for tache_id in list(exports._taches):
            exports.attendre(tache_id)
        [sauvegarde] = backups.lister()

        reponse = client.post(
            f"/evenements/sauvegardes/{sauvegarde.nom}/copiee", headers=HEADERS, follow_redirects=True,
        )
        assert "place disque est libérée" in reponse.get_data(as_text=True)
        assert backups.lister() == []

    def test_confirmation_refuse_un_chemin_hors_backups(self, contexte):
        client, _, _, _ = contexte
        assert client.post("/evenements/sauvegardes/..%2F..%2Fsessions.jsonl/copiee",
                           headers=HEADERS).status_code in (404, 308)

    def test_telechargement_direct(self, contexte):
        client, data, d10, raw = contexte
        evenement_id = _photo_dans_evenement(client, data, d10, raw)
        client.post(f"/evenements/{evenement_id}/sauvegarder", headers=HEADERS)
        for tache_id in list(exports._taches):
            exports.attendre(tache_id)
        [sauvegarde] = backups.lister()

        reponse = client.get(f"/evenements/sauvegardes/{sauvegarde.nom}", headers=HEADERS)
        assert reponse.status_code == 200
        assert reponse.mimetype == "application/zip"
