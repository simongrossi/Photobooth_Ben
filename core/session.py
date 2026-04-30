"""session.py — état de session photobooth + métadonnées.

Module pur (pas de pygame, pas d'accès caméra). Expose :
- `Etat` enum : les 4 états de la machine (ACCUEIL/DECOMPTE/VALIDATION/FIN)
- `SessionState` dataclass : toutes les variables mutables d'une session
- `ecrire_metadata_session()` : append JSONL vers `data/sessions.jsonl`
- `terminer_session_et_revenir_accueil()` : metadata + reset SessionState

Extrait de Photobooth_start.py (split boucle principale).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from config import PATH_DATA
from core.logger import log_warning


class Etat(Enum):
    """Les 4 états de la machine principale du photobooth."""
    ACCUEIL = "ACCUEIL"
    DECOMPTE = "DECOMPTE"
    VALIDATION = "VALIDATION"
    FIN = "FIN"


@dataclass
class SessionState:
    """État mutable d'une session photobooth + état transverse (idle, confirm abandon)."""

    etat: Etat = Etat.ACCUEIL
    mode_actuel: Optional[str] = None
    photos_validees: list = field(default_factory=list)
    id_session_timestamp: str = ""
    session_start_ts: float = 0.0
    path_montage: str = ""
    img_preview_cache: object = None   # pygame.Surface | None
    dernier_clic_time: float = 0.0
    abandon_confirm_until: float = 0.0  # timestamp limite de la fenêtre de confirmation
    last_activity_ts: float = 0.0       # pour déclenchement slideshow idle

    def reset_pour_accueil(self) -> None:
        """Reset complet après fin de session (printed/abandoned/capture_failed/print_failed/print_disabled).
        Préserve les compteurs temporels (last_activity_ts, etc.)."""
        self.etat = Etat.ACCUEIL
        self.mode_actuel = None
        self.photos_validees = []
        self.id_session_timestamp = ""
        self.img_preview_cache = None
        self.path_montage = ""


def ecrire_metadata_session(
    session: SessionState, issue: str, nb_photos: int, duree_s: float,
) -> None:
    """Ajoute une ligne JSON dans `data/sessions.jsonl`.

    Format append-only : une ligne par session terminée. Non-bloquant — toute
    erreur est loggée en warning (session en cours continue).

    Args:
        session: la session terminée (lit `id_session_timestamp`, `mode_actuel`).
        issue: "printed" | "abandoned" | "capture_failed" | "print_failed" |
            "print_disabled" (consommé par stats.py).
        nb_photos: nombre de photos effectivement capturées.
        duree_s: durée en secondes depuis `session_start_ts`.
    """
    try:
        entry = {
            "session_id": session.id_session_timestamp or None,
            "mode": session.mode_actuel,
            "issue": issue,
            "nb_photos": nb_photos,
            "duree_s": round(duree_s, 1),
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        chemin = os.path.join(PATH_DATA, "sessions.jsonl")
        with open(chemin, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log_warning(f"Écriture metadata session échouée : {e}")


def terminer_session_et_revenir_accueil(session: SessionState, issue: str) -> None:
    """Centralise la fin de session : écrit la metadata + reset du SessionState.

    Le caller reste responsable de mettre à jour `session.dernier_clic_time`
    après l'appel.

    Args:
        session: la session à terminer (sera reset).
        issue: "printed" | "abandoned" | "capture_failed" | "print_failed" |
            "print_disabled".
    """
    duree_s = time.time() - session.session_start_ts
    ecrire_metadata_session(session, issue, len(session.photos_validees), duree_s)
    session.reset_pour_accueil()
