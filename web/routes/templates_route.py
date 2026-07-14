"""templates_route.py — gestion des templates deux couches (upload, liste, activation).

Deux couches par format : `overlay` (PNG par-dessus la photo, dans
`assets/overlays/`) et `fond` (image sous les photos, dans `assets/backgrounds/`).
La DB SQLite maintient un registre (nom affiché, type, couche, fichier actif).
Le kiosque lit toujours les 4 mêmes chemins (`OVERLAY_*`, `BG_*` définis dans
config.py) : activer un template = remplacer la cible par une copie du template
choisi ; désactiver (« Aucun ») = supprimer la cible (le moteur de montage gère
nativement l'absence : fond → toile blanche, overlay → photo nue).
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

from config import (
    BG_10X15_FILE,
    BG_STRIPS_FILE,
    OVERLAY_10X15,
    OVERLAY_STRIPS,
    PATH_FONDS,
    PATH_OVERLAYS,
)
from web.auth import require_auth
from web.db import connexion

bp = Blueprint("templates", __name__, url_prefix="/templates")

TYPES_AUTORISES = ("10x15", "strip")
COUCHES_AUTORISEES = ("overlay", "fond")
# L'overlay exige la transparence (PNG) ; le fond est une image pleine.
EXTENSIONS_PAR_COUCHE = {
    "overlay": (".png",),
    "fond": (".png", ".jpg", ".jpeg"),
}
THUMB_MAX = (240, 240)

# Cibles fixes lues par le kiosque à chaque montage, par (couche, type).
_CIBLE_ACTIVE = {
    ("overlay", "10x15"): OVERLAY_10X15,
    ("overlay", "strip"): OVERLAY_STRIPS,
    ("fond", "10x15"): BG_10X15_FILE,
    ("fond", "strip"): BG_STRIPS_FILE,
}

# Dossier bibliothèque par couche.
_RACINE_PAR_COUCHE = {
    "overlay": PATH_OVERLAYS,
    "fond": PATH_FONDS,
}


@dataclass
class TemplateRow:
    id: int
    nom: str
    type: str
    couche: str
    fichier: str
    actif: bool
    uploaded_at: str
    taille_ko: int


def _safe_filename(nom: str) -> str:
    """Ne garde que [A-Za-z0-9._-]. Vide si rien de valable."""
    import re
    base = os.path.basename(nom)
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)


def _chemin_fichier(fichier: str, couche: str) -> str:
    racine_couche = _RACINE_PAR_COUCHE.get(couche)
    if racine_couche is None:
        abort(404)
    chemin = os.path.realpath(os.path.join(racine_couche, fichier))
    racine = os.path.realpath(racine_couche)
    if not chemin.startswith(racine + os.sep):
        abort(404)
    return chemin


def _lister() -> list[TemplateRow]:
    with connexion() as conn:
        rows = conn.execute(
            "SELECT id, nom, type, couche, fichier, actif, uploaded_at, taille_octets "
            "FROM template ORDER BY couche, type, uploaded_at DESC"
        ).fetchall()
    return [
        TemplateRow(
            id=r["id"], nom=r["nom"], type=r["type"], couche=r["couche"],
            fichier=r["fichier"],
            actif=bool(r["actif"]), uploaded_at=r["uploaded_at"],
            taille_ko=r["taille_octets"] // 1024,
        )
        for r in rows
    ]


@bp.route("/", methods=["GET"])
@require_auth
def index():
    templates = _lister()
    actifs = {(t.couche, t.type): t.nom for t in templates if t.actif}
    return render_template(
        "templates.html",
        templates=templates,
        actifs=actifs,
        couches=COUCHES_AUTORISEES,
        types=TYPES_AUTORISES,
        path_overlays=PATH_OVERLAYS,
        path_fonds=PATH_FONDS,
    )


@bp.route("/upload", methods=["POST"])
@require_auth
def upload():
    nom_affiche = (request.form.get("nom") or "").strip()
    type_template = request.form.get("type", "").strip()
    # Défaut "overlay" : compat avec les formulaires/scripts d'avant les deux couches.
    couche = (request.form.get("couche") or "overlay").strip()
    f = request.files.get("fichier")

    if couche not in COUCHES_AUTORISEES:
        flash("Couche invalide.", "error")
        return redirect(url_for("templates.index"))
    if type_template not in TYPES_AUTORISES:
        flash("Type de template invalide.", "error")
        return redirect(url_for("templates.index"))
    if not f or not f.filename:
        flash("Aucun fichier fourni.", "error")
        return redirect(url_for("templates.index"))
    extensions = EXTENSIONS_PAR_COUCHE[couche]
    if not f.filename.lower().endswith(extensions):
        libelle = ", ".join(e.lstrip(".").upper() for e in extensions)
        flash(f"Extension non autorisée : {libelle} uniquement.", "error")
        return redirect(url_for("templates.index"))

    racine = _RACINE_PAR_COUCHE[couche]
    os.makedirs(racine, exist_ok=True)
    nom_fichier = _safe_filename(f.filename)
    if not nom_fichier:
        flash("Nom de fichier invalide.", "error")
        return redirect(url_for("templates.index"))
    # Préfixe couche + type : évite les collisions entre modes ET entre couches
    # (la colonne `fichier` est UNIQUE globalement).
    nom_fichier = f"{couche}__{type_template}__{nom_fichier}"
    cible = os.path.join(racine, nom_fichier)

    # Sauvegarde + validation PIL (rejette les fichiers qui ne sont pas des images).
    contenu = f.read()
    try:
        with Image.open(io.BytesIO(contenu)) as img:
            img.verify()
    except (OSError, Image.UnidentifiedImageError):
        flash("Fichier image non reconnu ou corrompu.", "error")
        return redirect(url_for("templates.index"))

    with open(cible, "wb") as out:
        out.write(contenu)

    taille = os.path.getsize(cible)
    with connexion() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO template (nom, type, couche, fichier, actif, taille_octets) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (nom_affiche or nom_fichier, type_template, couche, nom_fichier, taille),
        )
    flash(f"Template « {nom_affiche or nom_fichier} » uploadé.", "success")
    return redirect(url_for("templates.index"))


@bp.route("/activer/<int:template_id>", methods=["POST"])
@require_auth
def activer(template_id: int):
    with connexion() as conn:
        row = conn.execute(
            "SELECT type, couche, fichier, nom FROM template WHERE id = ?", (template_id,),
        ).fetchone()
        if row is None:
            abort(404)
        type_t = row["type"]
        couche = row["couche"]
        fichier = row["fichier"]
        source = _chemin_fichier(fichier, couche)
        if not os.path.isfile(source):
            flash("Fichier source introuvable sur disque.", "error")
            return redirect(url_for("templates.index"))

        cible_active = _CIBLE_ACTIVE.get((couche, type_t))
        if cible_active is None:
            abort(400)
        os.makedirs(os.path.dirname(cible_active), exist_ok=True)
        shutil.copyfile(source, cible_active)

        conn.execute(
            "UPDATE template SET actif = 0 WHERE couche = ? AND type = ?", (couche, type_t),
        )
        conn.execute("UPDATE template SET actif = 1 WHERE id = ?", (template_id,))
    flash(f"Template « {row['nom']} » activé ({couche} {type_t}).", "success")
    return redirect(url_for("templates.index"))


@bp.route("/desactiver/<couche>/<type_t>", methods=["POST"])
@require_auth
def desactiver(couche: str, type_t: str):
    """État « Aucun » : supprime le fichier actif de la couche pour ce mode.

    Le kiosque gère nativement l'absence (fond → toile blanche, overlay → photo
    nue), effet à la photo suivante. Idempotent si déjà aucun template actif.
    """
    if couche not in COUCHES_AUTORISEES or type_t not in TYPES_AUTORISES:
        abort(404)
    cible_active = _CIBLE_ACTIVE[(couche, type_t)]
    try:
        os.remove(cible_active)
    except FileNotFoundError:
        pass
    with connexion() as conn:
        conn.execute(
            "UPDATE template SET actif = 0 WHERE couche = ? AND type = ?",
            (couche, type_t),
        )
    flash(f"Aucun template {couche} pour le mode {type_t} (désactivé).", "success")
    return redirect(url_for("templates.index"))


@bp.route("/supprimer/<int:template_id>", methods=["POST"])
@require_auth
def supprimer(template_id: int):
    with connexion() as conn:
        row = conn.execute(
            "SELECT fichier, couche, actif FROM template WHERE id = ?", (template_id,),
        ).fetchone()
        if row is None:
            abort(404)
        if row["actif"]:
            flash("Impossible de supprimer un template actif — activez-en un autre d'abord.", "error")
            return redirect(url_for("templates.index"))
        chemin = _chemin_fichier(row["fichier"], row["couche"])
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
            "SELECT fichier, couche FROM template WHERE id = ?", (template_id,),
        ).fetchone()
    if row is None:
        abort(404)
    chemin = _chemin_fichier(row["fichier"], row["couche"])
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
