"""auth.py — Basic Auth à deux niveaux pour l'admin web.

Deux rôles :
- **admin** : Basic Auth (`PHOTOBOOTH_ADMIN_PASS`) — accès complet, toutes les
  actions. Décorateur `require_auth`.
- **viewer** : anonyme, consultation seule (dashboard + galerie) via le
  décorateur `require_lecture`. Activé par défaut ; `PHOTOBOOTH_ACCES_LIBRE=0`
  le coupe (tout exige alors l'admin — utile pour un événement privé, car la
  galerie est sinon visible de tout appareil du LAN/wifi).

Si `PHOTOBOOTH_ADMIN_PASS` est absente ou vide, **toutes les routes refusent
l'accès** (fail closed), viewer compris.

Destiné à un usage LAN d'événement. Pour du multi-utilisateur ou exposition
Internet, remplacer par un vrai système de session + reverse-proxy HTTPS.
"""
from __future__ import annotations

import hmac
import os
from functools import wraps

from flask import Response, request

ADMIN_USER = "admin"
ENV_VAR = "PHOTOBOOTH_ADMIN_PASS"
ENV_ACCES_LIBRE = "PHOTOBOOTH_ACCES_LIBRE"


def _mot_de_passe_attendu() -> str | None:
    pw = os.environ.get(ENV_VAR, "")
    return pw if pw else None


def _acces_libre_actif() -> bool:
    """Mode consultation anonyme activé (défaut oui ; '0' pour le couper)."""
    return os.environ.get(ENV_ACCES_LIBRE, "1") != "0"


def role_courant() -> str | None:
    """'admin' si Basic Auth valide, 'viewer' si anonyme autorisé, None sinon.

    None couvre : pas de mot de passe admin configuré (fail closed), créds
    invalides, ou anonyme alors que l'accès libre est coupé.
    """
    attendu = _mot_de_passe_attendu()
    if not attendu:
        return None
    auth = request.authorization
    if auth is not None:
        if auth.username == ADMIN_USER and hmac.compare_digest(auth.password or "", attendu):
            return "admin"
        return None
    return "viewer" if _acces_libre_actif() else None


def _unauthorized() -> Response:
    return Response(
        "Authentification requise.",
        status=401,
        headers={"WWW-Authenticate": 'Basic realm="Photobooth Admin"'},
    )


def require_lecture(f):
    """Décorateur consultation : admin OU viewer anonyme (si accès libre)."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _mot_de_passe_attendu():
            return Response(
                "Admin désactivé : variable d'environnement "
                f"{ENV_VAR} non configurée.",
                status=503,
            )
        if role_courant() is None:
            return _unauthorized()
        return f(*args, **kwargs)

    return wrapper


def require_auth(f):
    """Décorateur : refuse 401 si Basic Auth manquante ou incorrecte."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        attendu = _mot_de_passe_attendu()
        if not attendu:
            return Response(
                "Admin désactivé : variable d'environnement "
                f"{ENV_VAR} non configurée.",
                status=503,
            )
        auth = request.authorization
        if not auth or auth.username != ADMIN_USER:
            return _unauthorized()
        # comparaison timing-safe
        if not hmac.compare_digest(auth.password or "", attendu):
            return _unauthorized()
        return f(*args, **kwargs)

    return wrapper
