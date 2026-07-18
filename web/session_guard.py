"""Verrou des mutations admin susceptibles d'altérer une session en cours.

Le kiosque et Flask vivent dans deux processus séparés. Le heartbeat atomique
de ``core.ecrans`` est donc la seule source de vérité commune. Un état périmé
ne bloque jamais l'administration : il doit rester possible de récupérer un
kiosque arrêté brutalement.
"""
from __future__ import annotations

from typing import Optional

from flask import Response, flash, redirect, url_for

from core import ecrans


def etat_verrou_session() -> dict:
    """Vue stable du verrou, calculée à partir d'une seule lecture disque."""
    etat = ecrans.lire_etat_kiosque() or {}
    actif = ecrans.session_kiosque_active(etat)
    return {
        "actif": actif,
        "ecran": etat.get("etat", "INCONNU") if actif else None,
        "session_id": etat.get("session_id") if actif else None,
    }


def refuser_mutation_pendant_session(
    endpoint_retour: str,
    *,
    action: str,
) -> Optional[Response]:
    """Retourne une redirection avec erreur si une session fraîche est active."""
    verrou = etat_verrou_session()
    if not verrou["actif"]:
        return None
    flash(
        f"Action refusée : impossible de {action} pendant une session "
        f"({verrou['ecran']}). Attends le retour à l'accueil.",
        "error",
    )
    return redirect(url_for(endpoint_retour))
