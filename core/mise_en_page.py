"""Géométrie persistante des photos dans les montages 10×15 et strip.

Le fichier JSON actif est partagé entre l'admin web (écriture atomique) et le
kiosque (lecture tolérante à chaque rendu). Une valeur absente ou invalide
retombe toujours sur la géométrie définie dans ``config.py``.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class MiseEnPage10x15:
    x: int
    y: int
    largeur: int
    hauteur: int

    def est_valide(self, canvas: tuple[int, int]) -> bool:
        canvas_w, canvas_h = canvas
        return (
            self.x >= 0
            and self.y >= 0
            and self.largeur > 0
            and self.hauteur > 0
            and self.x + self.largeur <= canvas_w
            and self.y + self.hauteur <= canvas_h
        )


@dataclass(frozen=True)
class MiseEnPageStrip:
    """Les trois zones photo d'une bandelette, dans l'ordre de capture."""

    photos: tuple[MiseEnPage10x15, MiseEnPage10x15, MiseEnPage10x15]

    def est_valide(self, canvas: tuple[int, int]) -> bool:
        return len(self.photos) == 3 and all(photo.est_valide(canvas) for photo in self.photos)


def charger_mise_en_page(
    chemin: str,
    defaut: MiseEnPage10x15,
    canvas: tuple[int, int],
) -> MiseEnPage10x15:
    """Lit une mise en page JSON, avec repli silencieux sur ``defaut``."""
    try:
        with open(chemin, encoding="utf-8") as fichier:
            donnees = json.load(fichier)
        mise_en_page = MiseEnPage10x15(
            x=int(donnees["x"]),
            y=int(donnees["y"]),
            largeur=int(donnees["largeur"]),
            hauteur=int(donnees["hauteur"]),
        )
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return defaut
    return mise_en_page if mise_en_page.est_valide(canvas) else defaut


def ecrire_mise_en_page(
    chemin: str,
    mise_en_page: MiseEnPage10x15,
    canvas: tuple[int, int],
    template_id: Optional[int] = None,
) -> None:
    """Écrit atomiquement la géométrie active après validation."""
    if not mise_en_page.est_valide(canvas):
        raise ValueError("La zone photo doit rester entièrement dans le montage.")
    donnees = {"version": 1, "format": "10x15", **asdict(mise_en_page)}
    if template_id is not None:
        donnees["template_id"] = template_id
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    temporaire = chemin + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temporaire, chemin)


def charger_mise_en_page_strip(
    chemin: str,
    defaut: MiseEnPageStrip,
    canvas: tuple[int, int],
) -> MiseEnPageStrip:
    """Lit les trois zones strip, avec repli silencieux sur ``defaut``."""
    try:
        with open(chemin, encoding="utf-8") as fichier:
            donnees = json.load(fichier)
        photos = tuple(
            MiseEnPage10x15(
                x=int(zone["x"]),
                y=int(zone["y"]),
                largeur=int(zone["largeur"]),
                hauteur=int(zone["hauteur"]),
            )
            for zone in donnees["photos"]
        )
        if len(photos) != 3:
            return defaut
        mise_en_page = MiseEnPageStrip(photos=photos)
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return defaut
    return mise_en_page if mise_en_page.est_valide(canvas) else defaut


def ecrire_mise_en_page_strip(
    chemin: str,
    mise_en_page: MiseEnPageStrip,
    canvas: tuple[int, int],
    template_id: Optional[int] = None,
) -> None:
    """Publie atomiquement les trois zones actives du mode strip."""
    if not mise_en_page.est_valide(canvas):
        raise ValueError("Les zones photo doivent rester entièrement dans la bandelette.")
    donnees = {
        "version": 1,
        "format": "strip",
        "photos": [asdict(photo) for photo in mise_en_page.photos],
    }
    if template_id is not None:
        donnees["template_id"] = template_id
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    temporaire = chemin + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temporaire, chemin)
