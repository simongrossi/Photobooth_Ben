"""kiosque_route.py — assets du kiosque : fond d'accueil, police, slides perso.

Trois catégories d'assets globaux (pas de dimension 10×15/strip) :
- `accueil` : fond d'écran de l'accueil. Activation → copie vers
  `FILE_BG_ACCUEIL_ACTIF` ; le kiosque le préfère au défaut à son prochain boot.
- `police`  : .ttf/.otf des textes à l'écran. Activation → `POLICE_FICHIER_ACTIF`.
- `slide`   : visuels perso ajoutés à la rotation du slideshow d'attente. Pas
  d'« actif » : tout fichier présent dans `PATH_SLIDESHOW_PERSO` tourne (le
  slideshow rescanne toutes les 30 s → effet à chaud).

« Défaut » = suppression du fichier actif (le kiosque retombe sur ses assets
versionnés). Aucun fichier versionné n'est écrasé.
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
from PIL import Image, ImageDraw, ImageFont

from config import (
    FILE_BG_ACCUEIL_ACTIF,
    FILE_BG_TRANSITION_ACTIF,
    PATH_ACCUEIL_BIBLIO,
    PATH_FONTS_BIBLIO,
    PATH_SLIDESHOW_PERSO,
    PATH_TRANSITION_BIBLIO,
    POLICE_FICHIER_ACTIF,
)
from web.auth import require_auth
from web.db import connexion

bp = Blueprint("kiosque", __name__, url_prefix="/kiosque")

CATEGORIES = ("accueil", "transition", "police", "slide")
EXTENSIONS_PAR_CATEGORIE = {
    "accueil": (".png", ".jpg", ".jpeg"),
    "transition": (".png", ".jpg", ".jpeg"),
    "police": (".ttf", ".otf"),
    "slide": (".png", ".jpg", ".jpeg"),
}
LIBELLES_CATEGORIE = {
    "accueil": "Fond d'accueil",
    "transition": "Fond de transition",
    "police": "Police des textes",
    "slide": "Slides du diaporama",
}
AIDES_CATEGORIE = {
    "accueil": "JPG/PNG plein écran — l'écran d'attente principal.",
    "transition": "JPG/PNG plein écran — annulation, reprise, attente d'impression. "
                  "Sans fond dédié, l'écran reprend le fond d'accueil.",
    "police": ".ttf/.otf — tous les textes affichés par le kiosque.",
    "slide": "JPG/PNG — ajoutés à la rotation du diaporama d'attente.",
}
THUMB_MAX = (240, 240)

# Cibles actives lues par le kiosque au boot ('slide' n'a pas de cible : tous tournent).
_CIBLE_ACTIVE = {
    "accueil": FILE_BG_ACCUEIL_ACTIF,
    "transition": FILE_BG_TRANSITION_ACTIF,
    "police": POLICE_FICHIER_ACTIF,
}

# Dossier bibliothèque par catégorie.
_RACINE_PAR_CATEGORIE = {
    "accueil": PATH_ACCUEIL_BIBLIO,
    "transition": PATH_TRANSITION_BIBLIO,
    "police": PATH_FONTS_BIBLIO,
    "slide": PATH_SLIDESHOW_PERSO,
}


@dataclass
class AssetRow:
    id: int
    nom: str
    categorie: str
    fichier: str
    actif: bool
    uploaded_at: str
    taille_ko: int


def _safe_filename(nom: str) -> str:
    """Ne garde que [A-Za-z0-9._-]. Vide si rien de valable."""
    import re
    base = os.path.basename(nom)
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)


def _chemin_fichier(fichier: str, categorie: str) -> str:
    racine_cat = _RACINE_PAR_CATEGORIE.get(categorie)
    if racine_cat is None:
        abort(404)
    chemin = os.path.realpath(os.path.join(racine_cat, fichier))
    racine = os.path.realpath(racine_cat)
    if not chemin.startswith(racine + os.sep):
        abort(404)
    return chemin


def _lister() -> list[AssetRow]:
    with connexion() as conn:
        rows = conn.execute(
            "SELECT id, nom, categorie, fichier, actif, uploaded_at, taille_octets "
            "FROM asset_kiosque ORDER BY categorie, uploaded_at DESC"
        ).fetchall()
    return [
        AssetRow(
            id=r["id"], nom=r["nom"], categorie=r["categorie"], fichier=r["fichier"],
            actif=bool(r["actif"]), uploaded_at=r["uploaded_at"],
            taille_ko=r["taille_octets"] // 1024,
        )
        for r in rows
    ]


def _valider_contenu(categorie: str, contenu: bytes) -> bool:
    """Valide réellement le fichier : image PIL ou fonte truetype chargeable."""
    try:
        if categorie == "police":
            ImageFont.truetype(io.BytesIO(contenu), 24)
        else:
            with Image.open(io.BytesIO(contenu)) as img:
                img.verify()
        return True
    except Exception:
        return False


@bp.route("/", methods=["GET"])
@require_auth
def index():
    assets = _lister()
    actifs = {a.categorie: a.nom for a in assets if a.actif}
    return render_template(
        "kiosque.html",
        assets=assets,
        actifs=actifs,
        racines=_RACINE_PAR_CATEGORIE,
        categories=CATEGORIES,
        libelles=LIBELLES_CATEGORIE,
        aides=AIDES_CATEGORIE,
        extensions=EXTENSIONS_PAR_CATEGORIE,
        # Une catégorie sans cible n'a pas de notion d'« actif » (cas de `slide`).
        categories_avec_actif=tuple(_CIBLE_ACTIVE),
    )


@bp.route("/upload", methods=["POST"])
@require_auth
def upload():
    nom_affiche = (request.form.get("nom") or "").strip()
    categorie = (request.form.get("categorie") or "").strip()
    f = request.files.get("fichier")

    if categorie not in CATEGORIES:
        flash("Catégorie invalide.", "error")
        return redirect(url_for("kiosque.index"))
    if not f or not f.filename:
        flash("Aucun fichier fourni.", "error")
        return redirect(url_for("kiosque.index"))
    extensions = EXTENSIONS_PAR_CATEGORIE[categorie]
    if not f.filename.lower().endswith(extensions):
        libelle = ", ".join(e.lstrip(".").upper() for e in extensions)
        flash(f"Extension non autorisée : {libelle} uniquement.", "error")
        return redirect(url_for("kiosque.index"))

    racine = _RACINE_PAR_CATEGORIE[categorie]
    os.makedirs(racine, exist_ok=True)
    nom_fichier = _safe_filename(f.filename)
    if not nom_fichier:
        flash("Nom de fichier invalide.", "error")
        return redirect(url_for("kiosque.index"))
    nom_fichier = f"{categorie}__{nom_fichier}"
    cible = os.path.join(racine, nom_fichier)

    contenu = f.read()
    if not _valider_contenu(categorie, contenu):
        flash("Fichier non reconnu (image ou police corrompue).", "error")
        return redirect(url_for("kiosque.index"))

    with open(cible, "wb") as out:
        out.write(contenu)

    taille = os.path.getsize(cible)
    with connexion() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO asset_kiosque (nom, categorie, fichier, actif, taille_octets) "
            "VALUES (?, ?, ?, 0, ?)",
            (nom_affiche or nom_fichier, categorie, nom_fichier, taille),
        )
    flash(f"Asset « {nom_affiche or nom_fichier} » uploadé.", "success")
    return redirect(url_for("kiosque.index"))


@bp.route("/activer/<int:asset_id>", methods=["POST"])
@require_auth
def activer(asset_id: int):
    with connexion() as conn:
        row = conn.execute(
            "SELECT categorie, fichier, nom FROM asset_kiosque WHERE id = ?", (asset_id,),
        ).fetchone()
        if row is None:
            abort(404)
        categorie = row["categorie"]
        cible_active = _CIBLE_ACTIVE.get(categorie)
        if cible_active is None:
            # 'slide' : pas d'activation, tous les fichiers présents tournent.
            abort(400)
        source = _chemin_fichier(row["fichier"], categorie)
        if not os.path.isfile(source):
            flash("Fichier source introuvable sur disque.", "error")
            return redirect(url_for("kiosque.index"))

        os.makedirs(os.path.dirname(cible_active), exist_ok=True)
        shutil.copyfile(source, cible_active)

        conn.execute("UPDATE asset_kiosque SET actif = 0 WHERE categorie = ?", (categorie,))
        conn.execute("UPDATE asset_kiosque SET actif = 1 WHERE id = ?", (asset_id,))
    flash(
        f"« {row['nom']} » activé ({categorie}) — effet au prochain redémarrage du kiosque.",
        "success",
    )
    return redirect(url_for("kiosque.index"))


@bp.route("/defaut/<categorie>", methods=["POST"])
@require_auth
def defaut(categorie: str):
    """Retour à l'asset par défaut : supprime le fichier actif. Idempotent."""
    cible_active = _CIBLE_ACTIVE.get(categorie)
    if cible_active is None:
        abort(404)
    try:
        os.remove(cible_active)
    except FileNotFoundError:
        pass
    with connexion() as conn:
        conn.execute("UPDATE asset_kiosque SET actif = 0 WHERE categorie = ?", (categorie,))
    flash(f"Retour au {categorie} par défaut — effet au prochain redémarrage du kiosque.", "success")
    return redirect(url_for("kiosque.index"))


@bp.route("/supprimer/<int:asset_id>", methods=["POST"])
@require_auth
def supprimer(asset_id: int):
    with connexion() as conn:
        row = conn.execute(
            "SELECT fichier, categorie, actif FROM asset_kiosque WHERE id = ?", (asset_id,),
        ).fetchone()
        if row is None:
            abort(404)
        if row["actif"]:
            flash("Impossible de supprimer un asset actif — repassez au défaut d'abord.", "error")
            return redirect(url_for("kiosque.index"))
        chemin = _chemin_fichier(row["fichier"], row["categorie"])
        try:
            os.remove(chemin)
        except FileNotFoundError:
            pass
        conn.execute("DELETE FROM asset_kiosque WHERE id = ?", (asset_id,))
    flash("Asset supprimé.", "success")
    return redirect(url_for("kiosque.index"))


@bp.route("/thumb/<int:asset_id>")
@require_auth
def thumb(asset_id: int):
    with connexion() as conn:
        row = conn.execute(
            "SELECT fichier, categorie FROM asset_kiosque WHERE id = ?", (asset_id,),
        ).fetchone()
    if row is None:
        abort(404)
    chemin = _chemin_fichier(row["fichier"], row["categorie"])
    if not os.path.isfile(chemin):
        abort(404)
    try:
        if row["categorie"] == "police":
            # Aperçu de la fonte : « Aa Bb 123 » rendu sur fond transparent.
            font = ImageFont.truetype(chemin, 42)
            img = Image.new("RGBA", (240, 80), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((10, 15), "Aa Bb 123", font=font, fill=(128, 138, 168, 255))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
        else:
            with Image.open(chemin) as img:
                img.thumbnail(THUMB_MAX)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    except OSError:
        abort(404)
