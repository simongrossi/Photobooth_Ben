"""apercu_route.py — aperçu du rendu final d'un template, sans impression.

Compose une photo de test avec les calques choisis en passant par le moteur du
kiosque (`core.montage`), pour montrer à l'écran exactement ce qui sortirait de
l'imprimante. Rien n'est activé, rien n'est écrit dans `data/`.

Distinct de l'aperçu CSS de l'éditeur de mise en page, qui empile des `<img>`
et ignore le recadrage, le filigrane, le grain et la rotation des calques strip.
"""
from __future__ import annotations

import io
import json
from typing import Optional

from flask import Blueprint, Response, abort, render_template, request, send_file

from config import MONTAGE_10X15_SIZE, MONTAGE_STRIP_SIZE
from core.mise_en_page import MiseEnPage10x15, MiseEnPageStrip
from core.montage import MontageGenerator10x15, MontageGeneratorStrip
from web import photos_raw
from web.auth import require_auth
from web.db import connexion
from web.session_guard import etat_verrou_session

# La résolution « id de template → fichier sur disque » et les géométries par
# défaut appartiennent au domaine templates ; on les réutilise plutôt que de les
# recopier. Import à sens unique : templates_route ne connaît pas l'aperçu.
from web.routes.templates_route import (
    _chemin_fichier,
    _mise_en_page_defaut,
    _mise_en_page_strip_defaut,
)

bp = Blueprint("apercu", __name__, url_prefix="/templates/apercu")

FORMATS = ("10x15", "strip")
PHOTOS_PAR_FORMAT = {"10x15": 1, "strip": 3}
TAILLE_PAR_FORMAT = {"10x15": MONTAGE_10X15_SIZE, "strip": MONTAGE_STRIP_SIZE}
QUALITE_APERCU = 88
AUCUN = "aucun"


def _format_demande() -> str:
    format_t = request.args.get("format", "10x15")
    if format_t not in FORMATS:
        abort(400, "Format inconnu.")
    return format_t


def _resoudre_calque(couche: str, format_t: str):
    """Retourne (chemin, ligne DB) pour une couche. Chemin vide = aucun calque.

    Sans paramètre, on prend le template actif de cette couche ; s'il n'y en a
    pas, on rend sans le calque — c'est déjà ce que fait le kiosque quand la
    cible n'existe pas sur le disque.
    """
    valeur = request.args.get(couche)
    if valeur == AUCUN:
        return "", None
    if valeur:
        try:
            template_id = int(valeur)
        except ValueError:
            abort(400, "Identifiant de template invalide.")
        with connexion() as conn:
            row = conn.execute(
                "SELECT * FROM template WHERE id = ? AND couche = ? AND type = ?",
                (template_id, couche, format_t),
            ).fetchone()
        if row is None:
            abort(404)
    else:
        with connexion() as conn:
            row = conn.execute(
                "SELECT * FROM template WHERE actif = 1 AND couche = ? AND type = ?",
                (couche, format_t),
            ).fetchone()
        if row is None:
            return "", None
    return _chemin_fichier(row["fichier"], couche), row


def _mise_en_page_de(row, format_t):
    """Géométrie personnalisée d'un template, ou None s'il n'en a pas."""
    if row is None:
        return None
    if format_t == "strip":
        if not row["zones_strip"]:
            return None
        try:
            return MiseEnPageStrip(photos=tuple(
                MiseEnPage10x15(**zone) for zone in json.loads(row["zones_strip"])
            ))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    champs = ("photo_x", "photo_y", "photo_largeur", "photo_hauteur")
    if any(row[champ] is None for champ in champs):
        return None
    return MiseEnPage10x15(
        x=row["photo_x"], y=row["photo_y"],
        largeur=row["photo_largeur"], hauteur=row["photo_hauteur"],
    )


def _mise_en_page_retenue(row_overlay, row_fond, format_t):
    """Overlay prioritaire, puis fond, puis le défaut de config.py.

    Même règle de priorité que `_synchroniser_mise_en_page_active()`, pour que
    l'aperçu montre ce que le kiosque produirait une fois le template activé.
    """
    for row in (row_overlay, row_fond):
        mise_en_page = _mise_en_page_de(row, format_t)
        if mise_en_page is not None:
            return mise_en_page
    return _mise_en_page_strip_defaut() if format_t == "strip" else _mise_en_page_defaut()


def _session_demandee(format_t: str) -> Optional[photos_raw.SessionRaw]:
    """Session de photos à composer, ou None s'il n'y en a aucune d'utilisable."""
    besoin = PHOTOS_PAR_FORMAT[format_t]
    id_session = request.args.get("session")
    if id_session:
        session = photos_raw.session_par_id(id_session, minimum_photos=besoin)
        if session is None:
            abort(400, f"Session introuvable ou comptant moins de {besoin} photo(s).")
        return session
    sessions = photos_raw.lister_sessions(minimum_photos=besoin)
    return sessions[0] if sessions else None


def _composer(format_t, photos, bg_path, overlay_path, mise_en_page):
    generateur = MontageGeneratorStrip if format_t == "strip" else MontageGenerator10x15
    return generateur.composer_apercu(
        photos,
        bg_path=bg_path,
        overlay_path=overlay_path,
        mise_en_page=mise_en_page,
    )


@bp.route("/", methods=["GET"], strict_slashes=False)
@require_auth
def index():
    verrou = etat_verrou_session()
    options = {}
    with connexion() as conn:
        for format_t in FORMATS:
            for couche in ("fond", "overlay"):
                options[f"{couche}_{format_t}"] = conn.execute(
                    "SELECT id, nom, actif FROM template WHERE couche = ? AND type = ? "
                    "ORDER BY actif DESC, nom",
                    (couche, format_t),
                ).fetchall()
    sessions_10x15 = photos_raw.lister_sessions(minimum_photos=1)
    sessions_strip = photos_raw.lister_sessions(minimum_photos=3)
    return render_template(
        "apercu.html",
        formats=FORMATS,
        options=options,
        sessions_10x15=sessions_10x15,
        sessions_strip=sessions_strip,
        substitution=not sessions_10x15,
        verrou_actif=verrou["actif"],
    )


@bp.route("/rendu", methods=["GET"])
@require_auth
def rendu():
    format_t = _format_demande()
    if etat_verrou_session()["actif"]:
        return Response(
            "Aperçu indisponible pendant une session en cours. "
            "Attends le retour à l'accueil.",
            status=409,
            mimetype="text/plain; charset=utf-8",
        )

    bg_path, row_fond = _resoudre_calque("fond", format_t)
    overlay_path, row_overlay = _resoudre_calque("overlay", format_t)
    mise_en_page = _mise_en_page_retenue(row_overlay, row_fond, format_t)
    session = _session_demandee(format_t)
    besoin = PHOTOS_PAR_FORMAT[format_t]

    if session is None:
        with photos_raw.photo_substitution() as chemin:
            image = _composer(
                format_t, [chemin] * besoin, bg_path, overlay_path, mise_en_page,
            )
    else:
        image = _composer(
            format_t, list(session.photos[:besoin]), bg_path, overlay_path, mise_en_page,
        )

    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=QUALITE_APERCU)
    image.close()
    buf.seek(0)
    reponse = send_file(buf, mimetype="image/jpeg")
    reponse.headers["Cache-Control"] = "no-store"
    return reponse
