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

import config
from config import PATH_DATA
from core.logger import log_warning

# États où un invité peut s'arrêter et partir. ACCUEIL en est exclu (rien à
# libérer) et DECOMPTE aussi (non interactif, il se termine tout seul).
ETATS_LIBERABLES = ("VALIDATION", "FIN")


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
    evenement_id: Optional[str] = None
    evenement_nom: Optional[str] = None
    evenement_tags: list[str] = field(default_factory=list)
    evenement_charge: bool = False
    erreur_impression: bool = False
    message_erreur_impression: str = ""
    # Échec de capture récupérable : la session reste ouverte pour proposer
    # « Réessayer » plutôt que de renvoyer l'invité à l'accueil sans recours.
    erreur_capture: bool = False
    chemin_impression: str = ""
    impressions_restantes: int = 0
    impression_en_cours: bool = False

    def reset_pour_accueil(self) -> None:
        """Reset complet après fin de session (printed/abandoned/capture_failed/print_failed/print_disabled).
        Préserve les compteurs temporels (last_activity_ts, etc.)."""
        self.etat = Etat.ACCUEIL
        self.mode_actuel = None
        self.photos_validees = []
        self.id_session_timestamp = ""
        self.img_preview_cache = None
        self.path_montage = ""
        self.evenement_id = None
        self.evenement_nom = None
        self.evenement_tags = []
        self.evenement_charge = False
        self.erreur_impression = False
        self.message_erreur_impression = ""
        self.erreur_capture = False
        self.chemin_impression = ""
        self.impressions_restantes = 0
        self.impression_en_cours = False


# ========================================================================================
# --- Libération automatique d'une session laissée sans utilisateur ---
# ========================================================================================

def secondes_avant_liberation(
    session: SessionState,
    maintenant: Optional[float] = None,
    delai: Optional[float] = None,
) -> Optional[float]:
    """Secondes restantes avant le retour automatique à l'accueil.

    None quand la libération ne s'applique pas : état non libérable (accueil,
    décompte), délai désactivé (`DUREE_IDLE_SESSION <= 0`) ou activité jamais
    horodatée. Un nombre négatif ou nul signifie que le délai est écoulé.

    Fonction pure, pour que la décision soit testable sans pygame — la boucle
    principale ne fait que l'interroger.
    """
    delai = config.DUREE_IDLE_SESSION if delai is None else delai
    if delai <= 0:
        return None
    if session.etat.value not in ETATS_LIBERABLES:
        return None
    if not session.last_activity_ts:
        return None
    return delai - ((maintenant or time.time()) - session.last_activity_ts)


def session_a_liberer(
    session: SessionState,
    maintenant: Optional[float] = None,
    delai: Optional[float] = None,
) -> bool:
    """True si la session doit être rendue à l'accueil pour cause d'inactivité."""
    restant = secondes_avant_liberation(session, maintenant, delai)
    return restant is not None and restant <= 0


def avertissement_liberation(
    session: SessionState,
    maintenant: Optional[float] = None,
    delai: Optional[float] = None,
    fenetre: Optional[float] = None,
) -> Optional[int]:
    """Secondes à afficher à l'invité, ou None s'il ne faut rien afficher.

    L'avertissement n'apparaît que dans les dernières secondes : prévenir trop
    tôt mettrait une pression inutile sur quelqu'un qui regarde simplement sa
    photo.
    """
    fenetre = config.DUREE_AVERTISSEMENT_IDLE if fenetre is None else fenetre
    restant = secondes_avant_liberation(session, maintenant, delai)
    if restant is None or restant <= 0 or restant > fenetre:
        return None
    return max(1, int(round(restant)))


def ecrire_metadata_session(
    session: SessionState, issue: str, nb_photos: int, duree_s: float,
) -> None:
    """Ajoute une ligne JSON dans `data/sessions.jsonl`.

    Format append-only : une ligne par session terminée. Non-bloquant — toute
    erreur est loggée en warning (session en cours continue).

    Args:
        session: la session terminée (lit `id_session_timestamp`, `mode_actuel`).
        issue: "printed" | "abandoned" | "capture_failed" | "print_failed" |
            "print_disabled" | "idle_timeout" (consommé par stats.py).
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
            "event_id": session.evenement_id,
            "event_name": session.evenement_nom,
            "event_tags": list(session.evenement_tags),
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
            "print_disabled" | "idle_timeout".
    """
    duree_s = time.time() - session.session_start_ts
    ecrire_metadata_session(session, issue, len(session.photos_validees), duree_s)
    session.reset_pour_accueil()
