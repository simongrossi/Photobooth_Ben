"""gallery.py — parcours des montages imprimés avec miniatures à la volée."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from PIL import Image

from config import (
    PATH_CORBEILLE, PATH_PRINT, PATH_PRINT_10X15, PATH_PRINT_STRIP,
    PATH_RAW, PATH_SKIPPED_DELETED, PATH_SKIPPED_RETAKE
)
from web.auth import require_auth

bp = Blueprint("gallery", __name__, url_prefix="/galerie")

PAGE_SIZE = 24
THUMB_MAX = (300, 300)

# Racines autorisées : interdit la remontée vers d'autres dossiers.
_RACINES_AUTORISEES = {
    "10x15": PATH_PRINT_10X15,
    "strip": PATH_PRINT_STRIP,
    "raw": PATH_RAW,
    "deleted": PATH_SKIPPED_DELETED,
    "retake": PATH_SKIPPED_RETAKE,
}


@dataclass
class Item:
    nom: str
    mode: str
    mtime: float
    taille_ko: int


def _lister_tous(type_galerie: str = "montages") -> list[Item]:
    items: list[Item] = []

    # Déterminer quels modes inclure
    if type_galerie == "raw":
        modes_a_lister = ["raw"]
    elif type_galerie == "deleted":
        modes_a_lister = ["deleted"]
    elif type_galerie == "retake":
        modes_a_lister = ["retake"]
    elif type_galerie == "all":
        modes_a_lister = ["10x15", "strip", "raw", "deleted", "retake"]
    else:  # "montages"
        modes_a_lister = ["10x15", "strip"]

    for mode in modes_a_lister:
        dossier = _RACINES_AUTORISEES.get(mode)
        if not dossier or not os.path.isdir(dossier):
            continue
        for nom in os.listdir(dossier):
            chemin = os.path.join(dossier, nom)
            if not os.path.isfile(chemin):
                continue
            if not nom.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            try:
                st = os.stat(chemin)
            except OSError:
                continue
            items.append(Item(
                nom=nom,
                mode=mode,
                mtime=st.st_mtime,
                taille_ko=st.st_size // 1024,
            ))

    # Si on cherche les montages et qu'il y a d'anciens montages directement dans PATH_PRINT
    if type_galerie in ("montages", "all") and os.path.isdir(PATH_PRINT):
        for nom in os.listdir(PATH_PRINT):
            chemin = os.path.join(PATH_PRINT, nom)
            if not os.path.isfile(chemin):
                continue
            if not nom.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            try:
                st = os.stat(chemin)
            except OSError:
                continue
            mode = "strip" if "strip" in nom.lower() else "10x15"
            items.append(Item(
                nom=nom,
                mode=mode,
                mtime=st.st_mtime,
                taille_ko=st.st_size // 1024,
            ))

    items.sort(key=lambda i: i.mtime, reverse=True)
    return items


def _resoudre_chemin(mode: str, nom: str) -> str:
    """Résout un chemin en bloquant toute sortie du dossier autorisé."""
    racine = _RACINES_AUTORISEES.get(mode)
    if racine is None:
        abort(404)

    # Tenter de trouver dans le dossier spécifique
    chemin = os.path.realpath(os.path.join(racine, nom))
    racine_resolue = os.path.realpath(racine)
    if chemin.startswith(racine_resolue + os.sep) or chemin == racine_resolue:
        if os.path.isfile(chemin):
            return chemin

    # Pour les montages legacy (mode 10x15 ou strip), vérifier également dans PATH_PRINT
    if mode in ("10x15", "strip"):
        chemin_racine = os.path.realpath(os.path.join(PATH_PRINT, nom))
        racine_print_resolue = os.path.realpath(PATH_PRINT)
        if chemin_racine.startswith(racine_print_resolue + os.sep) or chemin_racine == racine_print_resolue:
            if os.path.isfile(chemin_racine):
                return chemin_racine

    abort(404)


def _lister_corbeille() -> list[Item]:
    """Fichiers retirés (data/corbeille/<mode>/), restaurables."""
    items: list[Item] = []
    for mode in _RACINES_AUTORISEES:
        dossier = os.path.join(PATH_CORBEILLE, mode)
        if not os.path.isdir(dossier):
            continue
        for nom in os.listdir(dossier):
            chemin = os.path.join(dossier, nom)
            if not os.path.isfile(chemin):
                continue
            try:
                st = os.stat(chemin)
            except OSError:
                continue
            items.append(Item(nom=nom, mode=mode, mtime=st.st_mtime, taille_ko=st.st_size // 1024))
    items.sort(key=lambda i: i.mtime, reverse=True)
    return items


@bp.route("/")
@require_auth
def index():
    type_galerie = request.args.get("type", "montages")
    tous = _lister_tous(type_galerie)
    page = max(1, int(request.args.get("page", "1") or "1"))
    debut = (page - 1) * PAGE_SIZE
    fin = debut + PAGE_SIZE
    items = tous[debut:fin]
    total_pages = max(1, (len(tous) + PAGE_SIZE - 1) // PAGE_SIZE)
    return render_template(
        "gallery.html",
        items=items,
        page=page,
        total_pages=total_pages,
        total=len(tous),
        corbeille=_lister_corbeille(),
        print_path=PATH_PRINT,
        type_galerie=type_galerie,
    )


@bp.route("/retirer/<mode>/<nom>", methods=["POST"])
@require_auth
def retirer(mode: str, nom: str):
    """Déplace un montage vers la corbeille : disparaît du slideshow (≤ 30 s) et
    de la galerie. Jamais de suppression définitive — restaurable."""
    chemin = _resoudre_chemin(mode, nom)
    dest_dir = os.path.join(PATH_CORBEILLE, mode)
    os.makedirs(dest_dir, exist_ok=True)
    os.replace(chemin, os.path.join(dest_dir, os.path.basename(chemin)))
    flash("Photo retirée du slideshow et de la galerie — restaurable depuis la corbeille.", "success")
    return redirect(url_for("gallery.index"))


@bp.route("/restaurer/<mode>/<nom>", methods=["POST"])
@require_auth
def restaurer(mode: str, nom: str):
    """Déplacement inverse : la photo réapparaît en galerie et dans le slideshow."""
    racine = _RACINES_AUTORISEES.get(mode)
    if racine is None:
        abort(404)
    racine_corbeille = os.path.realpath(os.path.join(PATH_CORBEILLE, mode))
    chemin = os.path.realpath(os.path.join(racine_corbeille, nom))
    if not chemin.startswith(racine_corbeille + os.sep) or not os.path.isfile(chemin):
        abort(404)
    os.replace(chemin, os.path.join(racine, os.path.basename(chemin)))
    flash("Photo restaurée.", "success")
    return redirect(url_for("gallery.index"))


@bp.route("/image/<mode>/<nom>")
@require_auth
def image(mode: str, nom: str):
    chemin = _resoudre_chemin(mode, nom)
    return send_file(chemin)


@bp.route("/thumb/<mode>/<nom>")
@require_auth
def thumb(mode: str, nom: str):
    chemin = _resoudre_chemin(mode, nom)
    try:
        with Image.open(chemin) as img:
            img.thumbnail(THUMB_MAX)
            buf = io.BytesIO()
            fmt = "JPEG" if chemin.lower().endswith((".jpg", ".jpeg")) else "PNG"
            if fmt == "JPEG" and img.mode != "RGB":
                img = img.convert("RGB")
            img.save(buf, format=fmt, quality=80)
        buf.seek(0)
        mimetype = "image/jpeg" if fmt == "JPEG" else "image/png"
        return send_file(buf, mimetype=mimetype)
    except OSError:
        abort(404)
