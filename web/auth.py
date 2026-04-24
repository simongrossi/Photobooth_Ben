"""auth.py — Basic Auth simple pour l'admin web.

Mot de passe lu dans la variable d'environnement `PHOTOBOOTH_ADMIN_PASS`. Si
la variable est absente ou vide, **toutes les routes refusent l'accès** (fail
closed) : impossible de démarrer l'admin sans configurer un mot de passe.

Destiné à un usage LAN d'événement (un seul admin, réseau privé). Pour du
multi-utilisateur ou exposition Internet, remplacer par un vrai système de
session + reverse-proxy HTTPS.
"""
from __future__ import annotations

import hmac
import os
from functools import wraps

from flask import Response, request

ADMIN_USER = "admin"
ENV_VAR = "PHOTOBOOTH_ADMIN_PASS"


def _mot_de_passe_attendu() -> str | None:
    pw = os.environ.get(ENV_VAR, "")
    return pw if pw else None


def _unauthorized() -> Response:
    return Response(
        "Authentification requise.",
        status=401,
        headers={"WWW-Authenticate": 'Basic realm="Photobooth Admin"'},
    )


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
