"""export_route.py — page de suivi et récupération des archives ZIP différées."""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template, send_file

from web import exports
from web.auth import require_lecture, role_courant

bp = Blueprint("export", __name__, url_prefix="/export")


def _tache_accessible(tache_id: str):
    """Tâche visible par le rôle courant, sinon None.

    L'export d'un événement est réservé à l'admin : le suivi et le fichier le
    sont aussi, même si la page de suivi est par ailleurs ouverte aux viewers.
    """
    tache = exports.etat(tache_id)
    if tache is None:
        return None
    if tache.role_requis == "admin" and role_courant() != "admin":
        return None
    return tache


@bp.route("/<tache_id>")
@require_lecture
def suivi(tache_id: str):
    tache = _tache_accessible(tache_id)
    if tache is None:
        abort(404)
    return render_template("export.html", tache=tache)


@bp.route("/<tache_id>/etat")
@require_lecture
def etat(tache_id: str):
    tache = _tache_accessible(tache_id)
    if tache is None:
        return jsonify({"etat": "inconnu"}), 404
    return jsonify(tache.as_dict())


@bp.route("/<tache_id>/fichier")
@require_lecture
def fichier(tache_id: str):
    tache = _tache_accessible(tache_id)
    if tache is None or tache.etat != "pret" or not tache.chemin:
        abort(404)
    return send_file(
        tache.chemin,
        mimetype="application/zip",
        as_attachment=True,
        download_name=tache.nom_fichier,
        # Requêtes Range : un téléchargement de plusieurs Go coupé en route peut
        # reprendre là où il s'est arrêté au lieu de tout recommencer.
        conditional=True,
    )
