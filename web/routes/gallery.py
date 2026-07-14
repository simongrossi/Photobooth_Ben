"""gallery.py — parcours des montages imprimés avec miniatures à la volée."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from PIL import Image

from config import PATH_CORBEILLE, PATH_PRINT, PATH_PRINT_10X15, PATH_PRINT_STRIP
from web.auth import require_auth

bp = Blueprint("gallery", __name__, url_prefix="/galerie")

PAGE_SIZE = 24
THUMB_MAX = (300, 300)

# Racines autorisées : interdit la remontée vers d'autres dossiers.
_RACINES_AUTORISEES = {
    "10x15": PATH_PRINT_10X15,
    "strip": PATH_PRINT_STRIP,
}


@dataclass
class Item:
    nom: str
    mode: str
    mtime: float
    taille_ko: int


def _lister_tous() -> list[Item]:
    items: list[Item] = []
    for mode, dossier in _RACINES_AUTORISEES.items():
        if not os.path.isdir(dossier):
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
    items.sort(key=lambda i: i.mtime, reverse=True)
    return items


def _resoudre_chemin(mode: str, nom: str) -> str:
    """Résout un chemin en bloquant toute sortie du dossier autorisé."""
    racine = _RACINES_AUTORISEES.get(mode)
    if racine is None:
        abort(404)
    chemin = os.path.realpath(os.path.join(racine, nom))
    racine_resolue = os.path.realpath(racine)
    if not chemin.startswith(racine_resolue + os.sep) and chemin != racine_resolue:
        abort(404)
    if not os.path.isfile(chemin):
        abort(404)
    return chemin


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
    tous = _lister_tous()
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
