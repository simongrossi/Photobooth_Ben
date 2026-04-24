"""templates_route.py — gestion des overlays PNG (upload, liste, activation).

Les fichiers vivent dans `assets/overlays/`. La DB SQLite maintient un registre
(nom affiché, type, fichier actif). Le kiosque lit toujours le même chemin
`OVERLAY_10X15` / `OVERLAY_STRIPS` (défini dans config.py) : activer un
template = remplacer ce fichier par une copie du template choisi.
"""
from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from PIL import Image

from config import OVERLAY_10X15, OVERLAY_STRIPS, PATH_OVERLAYS
from web.auth import require_auth
from web.db import connexion

bp = Blueprint("templates", __name__, url_prefix="/templates")

TYPES_AUTORISES = ("10x15", "strip")
EXTENSIONS_AUTORISEES = (".png",)
THUMB_MAX = (240, 240)

# Cible où le kiosque lit l'overlay effectivement utilisé.
_CIBLE_ACTIVE = {
    "10x15": OVERLAY_10X15,
    "strip": OVERLAY_STRIPS,
}


@dataclass
class TemplateRow:
    id: int
    nom: str
    type: str
    fichier: str
    actif: bool
    uploaded_at: str
    taille_ko: int


def _safe_filename(nom: str) -> str:
    """Ne garde que [A-Za-z0-9._-]. Vide si rien de valable."""
    import re
    base = os.path.basename(nom)
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)


def _chemin_fichier(fichier: str) -> str:
    chemin = os.path.realpath(os.path.join(PATH_OVERLAYS, fichier))
    racine = os.path.realpath(PATH_OVERLAYS)
    if not chemin.startswith(racine + os.sep):
        abort(404)
    return chemin


def _lister() -> list[TemplateRow]:
    with connexion() as conn:
        rows = conn.execute(
            "SELECT id, nom, type, fichier, actif, uploaded_at, taille_octets "
            "FROM template ORDER BY type, uploaded_at DESC"
        ).fetchall()
    return [
        TemplateRow(
            id=r["id"], nom=r["nom"], type=r["type"], fichier=r["fichier"],
            actif=bool(r["actif"]), uploaded_at=r["uploaded_at"],
            taille_ko=r["taille_octets"] // 1024,
        )
        for r in rows
    ]


@bp.route("/", methods=["GET"])
@require_auth
def index():
    return render_template(
        "templates.html",
        templates=_lister(),
        path_overlays=PATH_OVERLAYS,
    )


@bp.route("/upload", methods=["POST"])
@require_auth
def upload():
    nom_affiche = (request.form.get("nom") or "").strip()
    type_template = request.form.get("type", "").strip()
    f = request.files.get("fichier")

    if type_template not in TYPES_AUTORISES:
        flash("Type de template invalide.", "error")
        return redirect(url_for("templates.index"))
    if not f or not f.filename:
        flash("Aucun fichier fourni.", "error")
        return redirect(url_for("templates.index"))
    if not f.filename.lower().endswith(EXTENSIONS_AUTORISEES):
        flash("Extension non autorisée : PNG uniquement.", "error")
        return redirect(url_for("templates.index"))

    os.makedirs(PATH_OVERLAYS, exist_ok=True)
    nom_fichier = _safe_filename(f.filename)
    if not nom_fichier:
        flash("Nom de fichier invalide.", "error")
        return redirect(url_for("templates.index"))
    # Préfixer avec le type pour éviter les collisions entre modes.
    nom_fichier = f"{type_template}__{nom_fichier}"
    cible = os.path.join(PATH_OVERLAYS, nom_fichier)

    # Sauvegarde + validation PIL (rejette les fichiers qui ne sont pas des PNG).
    contenu = f.read()
    try:
        with Image.open(io.BytesIO(contenu)) as img:
            img.verify()
    except (OSError, Image.UnidentifiedImageError):
        flash("Fichier non reconnu comme PNG valide.", "error")
        return redirect(url_for("templates.index"))

    with open(cible, "wb") as out:
        out.write(contenu)

    taille = os.path.getsize(cible)
    with connexion() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO template (nom, type, fichier, actif, taille_octets) "
            "VALUES (?, ?, ?, 0, ?)",
            (nom_affiche or nom_fichier, type_template, nom_fichier, taille),
        )
    flash(f"Template « {nom_affiche or nom_fichier} » uploadé.", "success")
    return redirect(url_for("templates.index"))


@bp.route("/activer/<int:template_id>", methods=["POST"])
@require_auth
def activer(template_id: int):
    with connexion() as conn:
        row = conn.execute(
            "SELECT type, fichier, nom FROM template WHERE id = ?", (template_id,),
        ).fetchone()
        if row is None:
            abort(404)
        type_t = row["type"]
        fichier = row["fichier"]
        source = _chemin_fichier(fichier)
        if not os.path.isfile(source):
            flash("Fichier source introuvable sur disque.", "error")
            return redirect(url_for("templates.index"))

        cible_active = _CIBLE_ACTIVE.get(type_t)
        if cible_active is None:
            abort(400)
        os.makedirs(os.path.dirname(cible_active), exist_ok=True)
        shutil.copyfile(source, cible_active)

        conn.execute("UPDATE template SET actif = 0 WHERE type = ?", (type_t,))
        conn.execute("UPDATE template SET actif = 1 WHERE id = ?", (template_id,))
    flash(f"Template « {row['nom']} » activé pour le mode {type_t}.", "success")
    return redirect(url_for("templates.index"))


@bp.route("/supprimer/<int:template_id>", methods=["POST"])
@require_auth
def supprimer(template_id: int):
    with connexion() as conn:
        row = conn.execute(
            "SELECT fichier, actif FROM template WHERE id = ?", (template_id,),
        ).fetchone()
        if row is None:
            abort(404)
        if row["actif"]:
            flash("Impossible de supprimer un template actif — activez-en un autre d'abord.", "error")
            return redirect(url_for("templates.index"))
        chemin = _chemin_fichier(row["fichier"])
        try:
            os.remove(chemin)
        except FileNotFoundError:
            pass
        conn.execute("DELETE FROM template WHERE id = ?", (template_id,))
    flash("Template supprimé.", "success")
    return redirect(url_for("templates.index"))


@bp.route("/thumb/<int:template_id>")
@require_auth
def thumb(template_id: int):
    with connexion() as conn:
        row = conn.execute(
            "SELECT fichier FROM template WHERE id = ?", (template_id,),
        ).fetchone()
    if row is None:
        abort(404)
    chemin = _chemin_fichier(row["fichier"])
    if not os.path.isfile(chemin):
        abort(404)
    try:
        with Image.open(chemin) as img:
            img.thumbnail(THUMB_MAX)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    except OSError:
        abort(404)
