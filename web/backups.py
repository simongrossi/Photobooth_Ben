"""backups.py — sauvegardes ZIP complètes des événements terminés.

Terminer un événement déclenche la construction d'une archive contenant **tout**
l'événement, photos brutes comprises, déposée dans `data/backups/`. Elle y
attend d'être copiée sur une clé USB à la main.

Ces archives pèsent plusieurs Go et **ne sont jamais purgées automatiquement** :
seule une confirmation explicite de copie depuis l'admin les supprime. Perdre
les photos d'un événement parce qu'un ménage automatique est passé avant la
copie serait irrattrapable ; un disque qui se remplit, lui, se voit et se
corrige. Le revers est réel — voir `docs/ADMIN.md` — d'où l'avertissement
affiché dès qu'une sauvegarde attend.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime

import config

# Nom de fichier : <slug>__<horodatage>.zip. Le double underscore sépare sans
# ambiguïté, un slug pouvant contenir des tirets simples.
_MOTIF_NOM = re.compile(r"^(?P<slug>[a-z0-9-]+)__(?P<horodatage>\d{8}-\d{4})\.zip$")


@dataclass
class Sauvegarde:
    nom: str
    slug: str
    horodatage: str
    chemin: str
    taille: int
    mtime: float

    @property
    def date_lisible(self) -> str:
        try:
            return datetime.strptime(self.horodatage, "%Y%m%d-%H%M").strftime("%d/%m/%Y à %H:%M")
        except ValueError:
            return self.horodatage


def dossier() -> str:
    """Dossier des sauvegardes, créé au besoin."""
    os.makedirs(config.PATH_BACKUPS, exist_ok=True)
    return config.PATH_BACKUPS


def nom_pour(slug: str, moment: datetime | None = None) -> str:
    moment = moment or datetime.now()
    return f"{slug}__{moment.strftime('%Y%m%d-%H%M')}.zip"


def chemin_pour(slug: str, moment: datetime | None = None) -> str:
    return os.path.join(dossier(), nom_pour(slug, moment))


def lister(slug: str | None = None) -> list[Sauvegarde]:
    """Sauvegardes présentes, de la plus récente à la plus ancienne."""
    racine = config.PATH_BACKUPS
    if not os.path.isdir(racine):
        return []
    trouvees: list[Sauvegarde] = []
    for entree in os.scandir(racine):
        if not entree.is_file():
            continue
        correspondance = _MOTIF_NOM.match(entree.name)
        if correspondance is None:
            continue
        if slug is not None and correspondance.group("slug") != slug:
            continue
        try:
            st = entree.stat()
        except OSError:
            continue
        trouvees.append(Sauvegarde(
            nom=entree.name,
            slug=correspondance.group("slug"),
            horodatage=correspondance.group("horodatage"),
            chemin=entree.path,
            taille=st.st_size,
            mtime=st.st_mtime,
        ))
    trouvees.sort(key=lambda s: s.mtime, reverse=True)
    return trouvees


def resoudre(nom: str) -> str | None:
    """Chemin d'une sauvegarde, ou None si le nom ne désigne pas une archive valide.

    Le nom doit correspondre au motif attendu **et** se résoudre dans
    `data/backups/` : ni traversée de chemin, ni lien symbolique sortant.
    """
    if _MOTIF_NOM.match(nom) is None:
        return None
    racine = os.path.realpath(config.PATH_BACKUPS)
    chemin = os.path.realpath(os.path.join(racine, nom))
    if not chemin.startswith(racine + os.sep) or not os.path.isfile(chemin):
        return None
    return chemin


def supprimer(nom: str) -> bool:
    """Supprime une sauvegarde copiée. Renvoie False si le nom est invalide."""
    chemin = resoudre(nom)
    if chemin is None:
        return False
    try:
        os.unlink(chemin)
    except OSError:
        return False
    return True
