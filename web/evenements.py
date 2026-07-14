"""Helpers de stockage et de partage des événements de l'admin."""
from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass

import config

from web.db import connexion

EMPLACEMENTS_TEMPLATES = (
    ("fond", "10x15"),
    ("overlay", "10x15"),
    ("fond", "strip"),
    ("overlay", "strip"),
)


@dataclass
class Evenement:
    id: str
    nom: str
    slug: str
    debut: str
    fin: str
    statut: str
    notes: str
    tags: list[str]
    created_at: str = ""
    updated_at: str = ""


def _chemin_evenement_actif() -> str:
    """Résout le chemin à l'appel pour respecter l'isolation des tests."""
    return os.path.join(config.PATH_DATA, "evenement_actif.json")


def slugifier(valeur: str) -> str:
    """Produit un slug ASCII stable et lisible."""
    valeur = unicodedata.normalize("NFKD", valeur).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", valeur.lower()).strip("-")


def parser_tags(valeur: str) -> list[str]:
    """Normalise une liste de tags séparés par des virgules, sans doublons."""
    resultat = []
    deja_vus = set()
    for brut in valeur.split(","):
        nom = " ".join(brut.strip().split())
        cle = nom.casefold()
        if nom and cle not in deja_vus:
            resultat.append(nom)
            deja_vus.add(cle)
    return resultat


def _tags_par_evenement(conn) -> dict[str, list[str]]:
    rows = conn.execute(
        "SELECT et.evenement_id, t.nom FROM evenement_tag et "
        "JOIN tag t ON t.id = et.tag_id ORDER BY t.nom COLLATE NOCASE"
    ).fetchall()
    resultat: dict[str, list[str]] = {}
    for row in rows:
        resultat.setdefault(row["evenement_id"], []).append(row["nom"])
    return resultat


def lister_evenements() -> list[Evenement]:
    with connexion() as conn:
        rows = conn.execute(
            "SELECT * FROM evenement ORDER BY "
            "CASE statut WHEN 'actif' THEN 0 WHEN 'brouillon' THEN 1 "
            "WHEN 'termine' THEN 2 ELSE 3 END, debut DESC"
        ).fetchall()
        tags = _tags_par_evenement(conn)
    return [Evenement(**dict(row), tags=tags.get(row["id"], [])) for row in rows]


def trouver_evenement(evenement_id: str) -> Evenement | None:
    with connexion() as conn:
        row = conn.execute("SELECT * FROM evenement WHERE id = ?", (evenement_id,)).fetchone()
        if row is None:
            return None
        tags = _tags_par_evenement(conn).get(evenement_id, [])
    return Evenement(**dict(row), tags=tags)


def remplacer_tags(conn, evenement_id: str, tags: list[str]) -> None:
    conn.execute("DELETE FROM evenement_tag WHERE evenement_id = ?", (evenement_id,))
    for nom in tags:
        slug = slugifier(nom)
        if not slug:
            continue
        conn.execute("INSERT OR IGNORE INTO tag (nom, slug) VALUES (?, ?)", (nom, slug))
        row = conn.execute(
            "SELECT id FROM tag WHERE nom = ? COLLATE NOCASE OR slug = ?", (nom, slug)
        ).fetchone()
        conn.execute(
            "INSERT OR IGNORE INTO evenement_tag (evenement_id, tag_id) VALUES (?, ?)",
            (evenement_id, row["id"]),
        )
    conn.execute("DELETE FROM tag WHERE id NOT IN (SELECT tag_id FROM evenement_tag)")


def selection_templates_evenement(evenement_id: str) -> dict[tuple[str, str], int | None]:
    """Retourne les quatre choix enregistrés, y compris les choix « Aucun »."""
    with connexion() as conn:
        rows = conn.execute(
            "SELECT couche, type, template_id FROM evenement_template WHERE evenement_id = ?",
            (evenement_id,),
        ).fetchall()
    selection = {(row["couche"], row["type"]): row["template_id"] for row in rows}
    return {emplacement: selection.get(emplacement) for emplacement in EMPLACEMENTS_TEMPLATES}


def enregistrer_selection_templates(conn, evenement_id: str, selection: dict) -> None:
    """Mémorise les quatre emplacements de templates d'un événement."""
    for (couche, type_t), template_id in selection.items():
        conn.execute(
            "INSERT INTO evenement_template (evenement_id, type, couche, template_id) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(evenement_id, type, couche) DO UPDATE SET template_id = excluded.template_id",
            (evenement_id, type_t, couche, template_id),
        )


def ecrire_evenement_actif(evenement: Evenement) -> None:
    """Écrit l'instantané par remplacement atomique dans le même dossier."""
    chemin = _chemin_evenement_actif()
    dossier = os.path.dirname(chemin)
    os.makedirs(dossier, exist_ok=True)
    contenu = {
        "id": evenement.id,
        "nom": evenement.nom,
        "slug": evenement.slug,
        "debut": evenement.debut,
        "fin": evenement.fin,
        "tags": evenement.tags,
    }
    temporaire = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=dossier, delete=False, prefix=".evenement-", suffix=".tmp"
        ) as fichier:
            temporaire = fichier.name
            json.dump(contenu, fichier, ensure_ascii=False, indent=2)
            fichier.write("\n")
        os.replace(temporaire, chemin)
    finally:
        if temporaire and os.path.exists(temporaire):
            os.unlink(temporaire)


def retirer_evenement_actif(evenement_id: str) -> None:
    """Retire le pointeur seulement s'il désigne encore cet événement."""
    chemin = _chemin_evenement_actif()
    try:
        with open(chemin, encoding="utf-8") as fichier:
            actif = json.load(fichier)
        if actif.get("id") == evenement_id:
            os.unlink(chemin)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return


def synchroniser_evenement_actif() -> None:
    """Répare le fichier partagé depuis la source de vérité SQLite au boot admin."""
    with connexion() as conn:
        row = conn.execute("SELECT id FROM evenement WHERE statut = 'actif'").fetchone()
    if row:
        ecrire_evenement_actif(trouver_evenement(row["id"]))
    else:
        try:
            os.unlink(_chemin_evenement_actif())
        except FileNotFoundError:
            pass


def tous_les_tags() -> list[str]:
    with connexion() as conn:
        rows = conn.execute("SELECT nom FROM tag ORDER BY nom COLLATE NOCASE").fetchall()
    return [row["nom"] for row in rows]
