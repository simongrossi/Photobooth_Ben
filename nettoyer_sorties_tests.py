#!/usr/bin/env python3
"""Déplace les mires/sorties de tests hors de data/print, sans les supprimer.

Usage :
    python3 nettoyer_sorties_tests.py             # inventaire seulement
    python3 nettoyer_sorties_tests.py --appliquer # déplacement vers la corbeille
"""
from __future__ import annotations

import argparse
import os

from config import PATH_CORBEILLE, PATH_PRINT
from core.monitoring import est_image_publique


def lister_sorties_tests(path_print: str = PATH_PRINT) -> list[str]:
    sorties = []
    if not os.path.isdir(path_print):
        return sorties
    for dossier, _, noms in os.walk(path_print):
        for nom in noms:
            if nom.casefold().endswith((".jpg", ".jpeg", ".png")) and not est_image_publique(nom):
                sorties.append(os.path.join(dossier, nom))
    return sorted(sorties)


def _destination_libre(destination: str) -> str:
    if not os.path.exists(destination):
        return destination
    base, extension = os.path.splitext(destination)
    compteur = 2
    while os.path.exists(f"{base}_{compteur}{extension}"):
        compteur += 1
    return f"{base}_{compteur}{extension}"


def deplacer_sorties_tests(
    sorties: list[str],
    path_print: str = PATH_PRINT,
    path_corbeille: str = PATH_CORBEILLE,
) -> list[str]:
    destinations = []
    for source in sorties:
        relatif = os.path.relpath(source, path_print)
        destination = _destination_libre(os.path.join(path_corbeille, "sorties_tests", relatif))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        os.replace(source, destination)
        destinations.append(destination)
    return destinations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--appliquer", action="store_true",
        help="déplace les fichiers détectés vers data/corbeille/sorties_tests/",
    )
    args = parser.parse_args()
    sorties = lister_sorties_tests()
    if not sorties:
        print("Aucune mire ou sortie de test détectée dans data/print.")
        return 0
    for chemin in sorties:
        print(chemin)
    if not args.appliquer:
        print(f"\n{len(sorties)} fichier(s) détecté(s). Relance avec --appliquer pour les déplacer.")
        return 0
    destinations = deplacer_sorties_tests(sorties)
    print(f"\n{len(destinations)} fichier(s) déplacé(s) vers data/corbeille/sorties_tests/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
