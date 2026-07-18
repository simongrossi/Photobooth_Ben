"""gallery.py — parcours des montages imprimés avec miniatures à la volée."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from PIL import Image

import config

from config import (
    PATH_CORBEILLE, PATH_PRINT, PATH_PRINT_10X15, PATH_PRINT_STRIP,
    PATH_RAW, PATH_SKIPPED_DELETED, PATH_SKIPPED_RETAKE
)
from core.monitoring import est_image_publique
from web.auth import require_auth, require_lecture
from stats import load_sessions
from web.evenements import lister_evenements, tous_les_tags

bp = Blueprint("gallery", __name__, url_prefix="/galerie")

PAGE_SIZE = 24
# La grille affiche chaque image sur environ 300 px de large. Une limite carrée
# réduisait les strips 1:3 à 100 px de large avant que le navigateur ne les
# réagrandisse à 300 px, ce qui rendait ces vignettes floues.
THUMB_MAX = (300, 900)
TYPES_GALERIE = {"all", "montages", "raw", "deleted", "retake"}

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
    chemin: str
    session_id: str | None = None
    event_id: str | None = None
    event_name: str | None = None
    event_tags: list[str] | None = None


_SESSION_ID_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}h\d{2}_\d{2}")


def _extraire_session_id(nom: str) -> str | None:
    """Extrait l'identifiant timestamp commun aux fichiers d'une session."""
    resultat = _SESSION_ID_RE.search(nom)
    return resultat.group(0) if resultat else None


def _lister_tous(type_galerie: str = "all") -> list[Item]:
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
        for entree in os.scandir(dossier):
            nom = entree.name
            chemin = entree.path
            if not entree.is_file():
                continue
            if not nom.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            if not est_image_publique(nom):
                continue
            try:
                st = entree.stat()
            except OSError:
                continue
            items.append(Item(
                nom=nom,
                mode=mode,
                mtime=st.st_mtime,
                taille_ko=st.st_size // 1024,
                chemin=chemin,
                session_id=_extraire_session_id(nom),
            ))

    # Si on cherche les montages et qu'il y a d'anciens montages directement dans PATH_PRINT
    if type_galerie in ("montages", "all") and os.path.isdir(PATH_PRINT):
        for entree in os.scandir(PATH_PRINT):
            nom = entree.name
            chemin = entree.path
            if not entree.is_file():
                continue
            if not nom.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            if not est_image_publique(nom):
                continue
            try:
                st = entree.stat()
            except OSError:
                continue
            mode = "strip" if "strip" in nom.lower() else "10x15"
            items.append(Item(
                nom=nom,
                mode=mode,
                mtime=st.st_mtime,
                taille_ko=st.st_size // 1024,
                chemin=chemin,
                session_id=_extraire_session_id(nom),
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
        for entree in os.scandir(dossier):
            nom = entree.name
            chemin = entree.path
            if not entree.is_file():
                continue
            try:
                st = entree.stat()
            except OSError:
                continue
            items.append(Item(
                nom=nom, mode=mode, mtime=st.st_mtime, taille_ko=st.st_size // 1024,
                chemin=chemin, session_id=_extraire_session_id(nom),
            ))
    items.sort(key=lambda i: i.mtime, reverse=True)
    return items


@bp.route("/")
@require_lecture
def index():
    type_galerie = request.args.get("type", "all")
    if type_galerie not in TYPES_GALERIE:
        type_galerie = "all"
    tous = _lister_tous(type_galerie)
    sessions = load_sessions(os.path.join(config.PATH_DATA, "sessions.jsonl")) or []
    tags_disponibles = sorted(
        set(tous_les_tags())
        | {str(tag) for session in sessions for tag in session.get("event_tags", [])},
        key=str.casefold,
    )
    sessions_par_id = {
        session.get("session_id"): session
        for session in sessions
        if session.get("session_id")
    }
    for item in tous:
        metadata = sessions_par_id.get(item.session_id, {})
        item.event_id = metadata.get("event_id")
        item.event_name = metadata.get("event_name")
        item.event_tags = metadata.get("event_tags") or []

    evenement_filtre = request.args.get("evenement", "")
    tag_filtre = request.args.get("tag", "")
    if evenement_filtre == "__sans__":
        tous = [item for item in tous if not item.event_id]
    elif evenement_filtre:
        tous = [item for item in tous if item.event_id == evenement_filtre]
    if tag_filtre:
        tous = [
            item for item in tous
            if tag_filtre.casefold() in {str(t).casefold() for t in item.event_tags}
        ]
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
        evenement_filtre=evenement_filtre,
        tag_filtre=tag_filtre,
        evenements=lister_evenements(),
        tags=tags_disponibles,
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
@require_lecture
def image(mode: str, nom: str):
    chemin = _resoudre_chemin(mode, nom)
    return send_file(chemin)


@bp.route("/thumb/<mode>/<nom>")
@require_lecture
def thumb(mode: str, nom: str):
    chemin = _resoudre_chemin(mode, nom)
    stat = os.stat(chemin)
    extension = ".jpg" if chemin.lower().endswith((".jpg", ".jpeg")) else ".png"
    signature = f"{os.path.realpath(chemin)}\0{stat.st_mtime_ns}\0{stat.st_size}\0{THUMB_MAX}"
    cle = hashlib.sha256(signature.encode()).hexdigest()[:24]
    cache_dir = os.path.join(config.PATH_DATA, "cache", "thumbs")
    os.makedirs(cache_dir, exist_ok=True)
    chemin_cache = os.path.join(cache_dir, cle + extension)
    mimetype = "image/jpeg" if extension == ".jpg" else "image/png"
    if os.path.isfile(chemin_cache):
        return send_file(chemin_cache, mimetype=mimetype, conditional=True, max_age=86400)

    chemin_temporaire = None
    try:
        with Image.open(chemin) as img:
            img.thumbnail(THUMB_MAX, Image.Resampling.LANCZOS)
            fmt = "JPEG" if extension == ".jpg" else "PNG"
            if fmt == "JPEG" and img.mode != "RGB":
                img = img.convert("RGB")
            with tempfile.NamedTemporaryFile(
                dir=cache_dir,
                prefix=".thumb-",
                suffix=extension,
                delete=False,
            ) as fichier_temporaire:
                chemin_temporaire = fichier_temporaire.name
            img.save(chemin_temporaire, format=fmt, quality=80)
        os.replace(chemin_temporaire, chemin_cache)
        return send_file(chemin_cache, mimetype=mimetype, conditional=True, max_age=86400)
    except OSError:
        if chemin_temporaire and os.path.exists(chemin_temporaire):
            os.remove(chemin_temporaire)
        abort(404)
