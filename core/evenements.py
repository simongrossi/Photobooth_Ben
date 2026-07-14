"""Lecture de l'événement actif partagé entre l'admin et le kiosque.

Le module reste volontairement pur et tolérant : une absence de fichier ou un
JSON invalide ne doit jamais empêcher une session photobooth de démarrer.
"""
from __future__ import annotations

import json
from typing import Any

from config import PATH_EVENEMENT_ACTIF
from core.logger import log_warning


def charger_evenement_actif(chemin: str | None = None) -> dict[str, Any] | None:
    """Retourne l'instantané actif, ou ``None`` s'il est absent/invalide."""
    chemin = chemin or PATH_EVENEMENT_ACTIF
    try:
        with open(chemin, encoding="utf-8") as fichier:
            evenement = json.load(fichier)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        log_warning(f"Lecture événement actif échouée : {exc}")
        return None

    if not isinstance(evenement, dict) or not evenement.get("id") or not evenement.get("nom"):
        log_warning("Fichier événement actif incomplet — session classée sans événement")
        return None

    tags = evenement.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return {
        "id": str(evenement["id"]),
        "nom": str(evenement["nom"]),
        "slug": str(evenement.get("slug", "")),
        "debut": evenement.get("debut"),
        "fin": evenement.get("fin"),
        "tags": [str(tag) for tag in tags if str(tag).strip()],
    }
