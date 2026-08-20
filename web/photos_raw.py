"""photos_raw.py — lecture et regroupement des photos brutes de `data/raw/`.

Le kiosque nomme ses captures `photo_<id_session>_<index>.jpg`, avec un
`id_session` horodaté (`2026-08-20_14h32_07`). Une session vaut une photo en
10×15 et trois en strip.

Partagé par la galerie (extraction de l'identifiant) et par l'aperçu du rendu
final (choix des photos de test).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from config import PATH_RAW

SESSION_ID_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}h\d{2}_\d{2}")

EXTENSIONS = (".jpg", ".jpeg", ".png")


def extraire_session_id(nom: str) -> str | None:
    """Extrait l'identifiant timestamp commun aux fichiers d'une session."""
    resultat = SESSION_ID_RE.search(nom)
    return resultat.group(0) if resultat else None


@dataclass(frozen=True)
class SessionRaw:
    """Les photos brutes d'une même session, triées par index de capture."""

    id_session: str
    photos: tuple[str, ...]


def lister_sessions(minimum_photos: int = 1) -> list[SessionRaw]:
    """Sessions présentes dans `data/raw/`, la plus récente d'abord.

    `minimum_photos` filtre les sessions trop courtes : un aperçu strip a besoin
    de trois photos. Les fichiers hors convention de nommage sont ignorés — ils
    n'appartiennent à aucune session.
    """
    try:
        noms = os.listdir(PATH_RAW)
    except (FileNotFoundError, NotADirectoryError):
        return []

    groupes: dict[str, list[str]] = {}
    for nom in noms:
        if not nom.casefold().endswith(EXTENSIONS):
            continue
        chemin = os.path.join(PATH_RAW, nom)
        if not os.path.isfile(chemin):
            continue
        id_session = extraire_session_id(nom)
        if id_session is None:
            continue
        groupes.setdefault(id_session, []).append(chemin)

    sessions = [
        SessionRaw(id_session=id_session, photos=tuple(sorted(chemins)))
        for id_session, chemins in groupes.items()
        if len(chemins) >= minimum_photos
    ]
    # L'identifiant est un horodatage : le tri lexicographique décroissant
    # équivaut au tri chronologique, sans dépendre des mtimes.
    sessions.sort(key=lambda s: s.id_session, reverse=True)
    return sessions



def session_par_id(id_session: str, minimum_photos: int = 1) -> SessionRaw | None:
    """Retourne une session précise, ou None si absente ou trop courte."""
    for session in lister_sessions(minimum_photos=minimum_photos):
        if session.id_session == id_session:
            return session
    return None
