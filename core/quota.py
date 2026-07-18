"""quota.py — compteur persistant de feuilles DNP + bridage par quota.

Module pur (pas de pygame). Le compteur vit dans `data/quota_impressions.json`,
fichier partagé entre le kiosque (incrément à chaque feuille envoyée à CUPS)
et l'admin web (affichage + déblocage). Le total de tirages ne repart JAMAIS
à zéro, même après redémarrage : chaque opération relit le fichier, le modifie
puis l'écrit atomiquement (tmp + os.replace).

Concurrence kiosque/web : pas de verrou fichier — la fenêtre de course entre
relecture et écriture est de quelques millisecondes, et son pire effet est une
feuille non comptée. Risque accepté pour rester simple.

Format du fichier :
    {"tirages_total": 142, "quota": 200, "derniere_maj": "2026-07-18 14:03:22"}

- `tirages_total` : feuilles DNP physiques envoyées (ne décroît jamais).
- `quota` : plafond cumulé, augmenté par `debloquer()` (jamais remis à zéro).
- restant = max(0, quota - tirages_total).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime

from config import PATH_QUOTA_IMPRESSIONS as PATH_QUOTA
from config import QUOTA_IMPRESSIONS_INITIAL as QUOTA_INITIAL
from core.logger import log_warning


def _etat_initial() -> dict:
    return {"tirages_total": 0, "quota": QUOTA_INITIAL, "derniere_maj": None}


def _charger_brut() -> dict:
    """Lit le fichier quota. Absent → état initial. Corrompu → renommé
    `.corrompu-<ts>` (forensique) puis état initial, sans lever d'exception."""
    if not os.path.exists(PATH_QUOTA):
        return _etat_initial()
    try:
        with open(PATH_QUOTA, encoding="utf-8") as f:
            brut = json.load(f)
        if not isinstance(brut, dict):
            raise ValueError(f"structure inattendue : {type(brut).__name__}")
        tirages = brut.get("tirages_total")
        quota = brut.get("quota")
        if not isinstance(tirages, int) or isinstance(tirages, bool) or tirages < 0:
            raise ValueError(f"tirages_total invalide : {tirages!r}")
        if not isinstance(quota, int) or isinstance(quota, bool) or quota < 0:
            raise ValueError(f"quota invalide : {quota!r}")
        return {"tirages_total": tirages, "quota": quota, "derniere_maj": brut.get("derniere_maj")}
    except (OSError, ValueError, json.JSONDecodeError) as e:
        chemin_corrompu = f"{PATH_QUOTA}.corrompu-{int(time.time())}"
        log_warning(f"Fichier quota illisible ({e}) — conservé sous {chemin_corrompu}")
        try:
            os.replace(PATH_QUOTA, chemin_corrompu)
        except OSError:
            pass
        return _etat_initial()


def _ecrire_brut(etat: dict) -> None:
    """Écriture atomique (tmp + os.replace) avec horodatage `derniere_maj`."""
    etat["derniere_maj"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dossier = os.path.dirname(PATH_QUOTA)
    if dossier:
        os.makedirs(dossier, exist_ok=True)
    tmp = f"{PATH_QUOTA}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH_QUOTA)


def charger_etat() -> dict:
    """Retourne l'état courant {"tirages_total", "quota", "derniere_maj"}."""
    return _charger_brut()


def quota_restant() -> int:
    """Feuilles encore imprimables : max(0, quota - tirages_total)."""
    etat = _charger_brut()
    return max(0, etat["quota"] - etat["tirages_total"])


def enregistrer_tirage(nb: int = 1) -> dict:
    """Comptabilise `nb` feuilles DNP envoyées et persiste. Retourne l'état."""
    etat = _charger_brut()
    etat["tirages_total"] += nb
    _ecrire_brut(etat)
    return etat


def debloquer(increment: int) -> dict:
    """Augmente le plafond de `increment` feuilles et persiste. Retourne l'état."""
    etat = _charger_brut()
    etat["quota"] += increment
    _ecrire_brut(etat)
    return etat


class SaisieSequence:
    """Machine pure de saisie d'un code sur les boutons (ex. G→D→M).

    `presser(touche)` retourne :
    - "en_cours"  : touche correcte, séquence incomplète ;
    - "complete"  : séquence entièrement saisie ;
    - "reset"     : mauvaise touche, progression remise à zéro.
    """

    def __init__(self, sequence: tuple[int, ...]):
        self.sequence = tuple(sequence)
        self.progression = 0

    def presser(self, touche: int) -> str:
        if touche == self.sequence[self.progression]:
            self.progression += 1
            if self.progression == len(self.sequence):
                return "complete"
            return "en_cours"
        self.progression = 0
        return "reset"

    def reinitialiser(self) -> None:
        self.progression = 0
