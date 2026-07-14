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
import json
import os
import shutil
from dataclasses import asdict, dataclass
from typing import Optional

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
from PIL import Image, ImageDraw

from config import (
    BG_10X15_FILE,
    BG_STRIPS_FILE,
    OVERLAY_10X15,
    OVERLAY_STRIPS,
    PATH_FONDS,
    PATH_MISE_EN_PAGE_10X15,
    PATH_MISE_EN_PAGE_STRIP,
    PATH_OVERLAYS,
    PATH_RAW,
    MONTAGE_10X15_FINAL_PHOTO_FIT,
    MONTAGE_10X15_FINAL_PHOTO_OFFSET,
    MONTAGE_10X15_SIZE,
    MONTAGE_STRIP_SIZE,
    STRIP_ESPACE_PHOTOS,
    STRIP_MARGE_HAUT,
    STRIP_MARGE_LATERALE,
    STRIP_PHOTO_RATIO,
    STRIP_ROTATION_DEGREES,
)
from core.mise_en_page import (
    MiseEnPage10x15,
    MiseEnPageStrip,
    ecrire_mise_en_page,
    ecrire_mise_en_page_strip,
)
from web.auth import require_auth
from web.db import connexion
from web.evenements import lister_evenements, selection_templates_evenement

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
    photo_x: Optional[int]
    photo_y: Optional[int]
    photo_largeur: Optional[int]
    photo_hauteur: Optional[int]
    zones_strip: Optional[str]

    @property
    def mise_en_page_personnalisee(self) -> bool:
        if self.type == "strip":
            return self.zones_strip is not None
        return all(
            valeur is not None
            for valeur in (self.photo_x, self.photo_y, self.photo_largeur, self.photo_hauteur)
        )


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


def _synchroniser_disque_et_db() -> None:
    """Importe automatiquement dans la base de données les fichiers physiques
    présents sur le disque (issus d'anciennes installations ou de modifs manuelles)
    si aucun template n'est actuellement actif pour ce couple (couche, type).
    """
    for (couche, type_t), cible_active in _CIBLE_ACTIVE.items():
        if not os.path.isfile(cible_active):
            continue

        # Vérifier si on a un template actif dans la DB pour ce (couche, type_t)
        with connexion() as conn:
            active_row = conn.execute(
                "SELECT id FROM template WHERE couche = ? AND type = ? AND actif = 1",
                (couche, type_t),
            ).fetchone()

        if active_row is None:
            # Il y a un fichier sur le disque mais aucun template actif enregistré !
            racine = _RACINE_PAR_COUCHE[couche]
            os.makedirs(racine, exist_ok=True)

            base_nom = os.path.basename(cible_active)
            nom_fichier = f"{couche}__{type_t}__origine_{base_nom}"
            destination = os.path.join(racine, nom_fichier)

            try:
                # Copier le fichier actif vers le nom de la bibliothèque (si pas déjà présent)
                if not os.path.exists(destination):
                    shutil.copyfile(cible_active, destination)

                taille = os.path.getsize(destination)
                nom_affiche = f"Gabarit d'origine ({type_t})"

                with connexion() as conn:
                    # Désactiver d'autres templates éventuels (par sécurité)
                    conn.execute(
                        "UPDATE template SET actif = 0 WHERE couche = ? AND type = ?",
                        (couche, type_t),
                    )
                    # Insérer ou remplacer le template d'origine comme actif
                    conn.execute(
                        "INSERT OR REPLACE INTO template (nom, type, couche, fichier, actif, taille_octets) "
                        "VALUES (?, ?, ?, ?, 1, ?)",
                        (nom_affiche, type_t, couche, nom_fichier, taille),
                    )
            except Exception as e:
                print(f"Erreur d'importation automatique du template d'origine ({couche}, {type_t}) : {e}")


def _mise_en_page_defaut() -> MiseEnPage10x15:
    return MiseEnPage10x15(
        x=MONTAGE_10X15_FINAL_PHOTO_OFFSET[0],
        y=MONTAGE_10X15_FINAL_PHOTO_OFFSET[1],
        largeur=MONTAGE_10X15_FINAL_PHOTO_FIT[0],
        hauteur=MONTAGE_10X15_FINAL_PHOTO_FIT[1],
    )


def _mise_en_page_strip_defaut() -> MiseEnPageStrip:
    largeur = MONTAGE_STRIP_SIZE[0] - (2 * STRIP_MARGE_LATERALE)
    hauteur = int(largeur * float(STRIP_PHOTO_RATIO))
    return MiseEnPageStrip(photos=tuple(
        MiseEnPage10x15(
            x=STRIP_MARGE_LATERALE,
            y=STRIP_MARGE_HAUT + i * (hauteur + STRIP_ESPACE_PHOTOS),
            largeur=largeur,
            hauteur=hauteur,
        )
        for i in range(3)
    ))


def _synchroniser_mise_en_page_active() -> None:
    """Publie les zones actives des deux formats (overlay prioritaire)."""
    with connexion() as conn:
        row = conn.execute(
            "SELECT id, photo_x, photo_y, photo_largeur, photo_hauteur FROM template "
            "WHERE actif = 1 AND type = '10x15' "
            "AND photo_x IS NOT NULL AND photo_y IS NOT NULL "
            "AND photo_largeur IS NOT NULL AND photo_hauteur IS NOT NULL "
            "ORDER BY CASE couche WHEN 'overlay' THEN 0 ELSE 1 END LIMIT 1"
        ).fetchone()
    if row is None:
        try:
            os.remove(PATH_MISE_EN_PAGE_10X15)
        except FileNotFoundError:
            pass
    else:
        mise_en_page = MiseEnPage10x15(
            x=row["photo_x"], y=row["photo_y"],
            largeur=row["photo_largeur"], hauteur=row["photo_hauteur"],
        )
        ecrire_mise_en_page(
            PATH_MISE_EN_PAGE_10X15, mise_en_page, MONTAGE_10X15_SIZE,
            template_id=row["id"],
        )

    with connexion() as conn:
        row_strip = conn.execute(
            "SELECT id, zones_strip FROM template WHERE actif = 1 AND type = 'strip' "
            "AND zones_strip IS NOT NULL "
            "ORDER BY CASE couche WHEN 'overlay' THEN 0 ELSE 1 END LIMIT 1"
        ).fetchone()
    if row_strip is None:
        try:
            os.remove(PATH_MISE_EN_PAGE_STRIP)
        except FileNotFoundError:
            pass
        return
    try:
        zones = json.loads(row_strip["zones_strip"])
        mise_en_page_strip = MiseEnPageStrip(photos=tuple(
            MiseEnPage10x15(**zone) for zone in zones
        ))
        ecrire_mise_en_page_strip(
            PATH_MISE_EN_PAGE_STRIP, mise_en_page_strip, MONTAGE_STRIP_SIZE,
            template_id=row_strip["id"],
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        try:
            os.remove(PATH_MISE_EN_PAGE_STRIP)
        except FileNotFoundError:
            pass


def appliquer_selection_templates(selection: dict[tuple[str, str], Optional[int]]) -> None:
    """Applique en DB et sur disque les quatre choix d'un événement.

    Les sources sont toutes validées avant de toucher aux cibles du kiosque.
    Une valeur ``None`` représente explicitement « Aucun template ».
    """
    attendu = set(_CIBLE_ACTIVE)
    if set(selection) != attendu:
        raise ValueError("La sélection doit définir les quatre emplacements de templates.")

    fichiers: dict[tuple[str, str], Optional[str]] = {}
    with connexion() as conn:
        for (couche, type_t), template_id in selection.items():
            if template_id is None:
                fichiers[(couche, type_t)] = None
                continue
            row = conn.execute(
                "SELECT id, type, couche, fichier FROM template WHERE id = ?",
                (template_id,),
            ).fetchone()
            if row is None or row["type"] != type_t or row["couche"] != couche:
                raise ValueError(f"Template incompatible pour {couche} {type_t}.")
            source = _chemin_fichier(row["fichier"], couche)
            if not os.path.isfile(source):
                raise FileNotFoundError(f"Fichier source introuvable pour {couche} {type_t}.")
            fichiers[(couche, type_t)] = source

        for emplacement, source in fichiers.items():
            cible = _CIBLE_ACTIVE[emplacement]
            if source is None:
                try:
                    os.remove(cible)
                except FileNotFoundError:
                    pass
            else:
                os.makedirs(os.path.dirname(cible), exist_ok=True)
                shutil.copyfile(source, cible)

        conn.execute("UPDATE template SET actif = 0")
        ids = [template_id for template_id in selection.values() if template_id is not None]
        conn.executemany("UPDATE template SET actif = 1 WHERE id = ?", ((id_,) for id_ in ids))
    _synchroniser_mise_en_page_active()


def _memoriser_pour_evenement_actif(conn, couche: str, type_t: str, template_id: Optional[int]) -> None:
    """Garde l'événement actif cohérent avec un changement manuel de template."""
    evenement = conn.execute("SELECT id FROM evenement WHERE statut = 'actif'").fetchone()
    if evenement is None:
        return
    conn.execute(
        "INSERT INTO evenement_template (evenement_id, type, couche, template_id) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(evenement_id, type, couche) DO UPDATE SET template_id = excluded.template_id",
        (evenement["id"], type_t, couche, template_id),
    )


def _lister() -> list[TemplateRow]:
    with connexion() as conn:
        rows = conn.execute(
            "SELECT id, nom, type, couche, fichier, actif, uploaded_at, taille_octets, "
            "photo_x, photo_y, photo_largeur, photo_hauteur, zones_strip "
            "FROM template ORDER BY couche, type, uploaded_at DESC"
        ).fetchall()
    return [
        TemplateRow(
            id=r["id"], nom=r["nom"], type=r["type"], couche=r["couche"],
            fichier=r["fichier"],
            actif=bool(r["actif"]), uploaded_at=r["uploaded_at"],
            taille_ko=r["taille_octets"] // 1024,
            photo_x=r["photo_x"], photo_y=r["photo_y"],
            photo_largeur=r["photo_largeur"], photo_hauteur=r["photo_hauteur"],
            zones_strip=r["zones_strip"],
        )
        for r in rows
    ]


def _associations_evenements() -> dict[int, list[dict]]:
    with connexion() as conn:
        rows = conn.execute(
            "SELECT et.template_id, e.id, e.nom, e.statut FROM evenement_template et "
            "JOIN evenement e ON e.id = et.evenement_id "
            "WHERE et.template_id IS NOT NULL ORDER BY e.nom COLLATE NOCASE"
        ).fetchall()
    resultat: dict[int, list[dict]] = {}
    for row in rows:
        resultat.setdefault(row["template_id"], []).append(dict(row))
    return resultat


@bp.route("/", methods=["GET"])
@require_auth
def index():
    _synchroniser_disque_et_db()
    _synchroniser_mise_en_page_active()
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
        evenements=[e for e in lister_evenements() if e.statut != "archive"],
        associations_evenements=_associations_evenements(),
    )


@bp.route("/associer/<int:template_id>", methods=["POST"])
@require_auth
def associer_evenement(template_id: int):
    """Affecte un template existant à la couche correspondante d'un événement."""
    evenement_id = (request.form.get("evenement_id") or "").strip()
    with connexion() as conn:
        template = conn.execute(
            "SELECT id, nom, type, couche FROM template WHERE id = ?", (template_id,),
        ).fetchone()
        if template is None:
            abort(404)
        evenement = conn.execute(
            "SELECT id, nom, statut FROM evenement WHERE id = ?", (evenement_id,),
        ).fetchone()
        if evenement is None or evenement["statut"] == "archive":
            flash("Événement introuvable ou archivé.", "error")
            return redirect(url_for("templates.index"))
        conn.execute(
            "INSERT INTO evenement_template (evenement_id, type, couche, template_id) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(evenement_id, type, couche) DO UPDATE SET template_id = excluded.template_id",
            (evenement_id, template["type"], template["couche"], template_id),
        )

    if evenement["statut"] == "actif":
        try:
            appliquer_selection_templates(selection_templates_evenement(evenement_id))
        except (ValueError, FileNotFoundError, OSError) as e:
            flash(f"Association enregistrée, mais application impossible : {e}", "error")
            return redirect(url_for("templates.index"))
    flash(
        f"Template « {template['nom']} » associé à « {evenement['nom']} » "
        f"({template['couche']} {template['type']}).",
        "success",
    )
    return redirect(url_for("templates.index"))


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
        _memoriser_pour_evenement_actif(conn, couche, type_t, template_id)
    _synchroniser_mise_en_page_active()
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
        _memoriser_pour_evenement_actif(conn, couche, type_t, None)
    _synchroniser_mise_en_page_active()
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


@bp.route("/fichier/<int:template_id>")
@require_auth
def fichier(template_id: int):
    """Retourne l'image originale utilisée comme calque par l'éditeur."""
    with connexion() as conn:
        row = conn.execute(
            "SELECT fichier, couche, type FROM template WHERE id = ?", (template_id,),
        ).fetchone()
    if row is None:
        abort(404)
    chemin = _chemin_fichier(row["fichier"], row["couche"])
    if not os.path.isfile(chemin):
        abort(404)
    if row["type"] != "strip" or request.args.get("rendu") != "1":
        return send_file(chemin, conditional=True)
    try:
        with Image.open(chemin) as source:
            image = source.convert("RGBA")
        if image.width > image.height:
            image = image.rotate(90, expand=True)
        image = image.rotate(STRIP_ROTATION_DEGREES).resize(MONTAGE_STRIP_SIZE)
        buf = io.BytesIO()
        image.save(buf, "PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    except OSError:
        abort(404)


@bp.route("/photo-exemple")
@require_auth
def photo_exemple():
    """Retourne la dernière photo brute, ou un visuel neutre si aucune n'existe."""
    try:
        candidats = [
            os.path.join(PATH_RAW, nom)
            for nom in os.listdir(PATH_RAW)
            if nom.casefold().endswith((".jpg", ".jpeg", ".png"))
            and os.path.isfile(os.path.join(PATH_RAW, nom))
        ]
    except FileNotFoundError:
        candidats = []
    if candidats:
        return send_file(max(candidats, key=os.path.getmtime), conditional=True)

    image = Image.new("RGB", (1200, 800), "#d9dde5")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 1160, 760), outline="#7b8497", width=8)
    draw.line((40, 40, 1160, 760), fill="#a0a8b7", width=5)
    draw.line((1160, 40, 40, 760), fill="#a0a8b7", width=5)
    draw.text((470, 380), "PHOTO EXEMPLE", fill="#303747")
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=88)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg")


@bp.route("/editer/<int:template_id>", methods=["GET", "POST"])
@require_auth
def editer(template_id: int):
    with connexion() as conn:
        row = conn.execute("SELECT * FROM template WHERE id = ?", (template_id,)).fetchone()
    if row is None:
        abort(404)
    if request.method == "POST":
        if row["type"] == "strip":
            try:
                mise_en_page_strip = MiseEnPageStrip(photos=tuple(
                    MiseEnPage10x15(
                        x=int(request.form[f"photo_{i}_x"]),
                        y=int(request.form[f"photo_{i}_y"]),
                        largeur=int(request.form[f"photo_{i}_largeur"]),
                        hauteur=int(request.form[f"photo_{i}_hauteur"]),
                    )
                    for i in range(1, 4)
                ))
            except (KeyError, TypeError, ValueError):
                flash("Coordonnées invalides.", "error")
                return redirect(url_for("templates.editer", template_id=template_id))
            if not mise_en_page_strip.est_valide(MONTAGE_STRIP_SIZE):
                flash("Les zones photo doivent rester entièrement dans la bandelette.", "error")
                return redirect(url_for("templates.editer", template_id=template_id))
            with connexion() as conn:
                conn.execute(
                    "UPDATE template SET zones_strip = ? WHERE id = ?",
                    (json.dumps([asdict(zone) for zone in mise_en_page_strip.photos]), template_id),
                )
            _synchroniser_mise_en_page_active()
            flash(f"Mise en page de « {row['nom']} » enregistrée.", "success")
            return redirect(url_for("templates.editer", template_id=template_id))

        try:
            mise_en_page = MiseEnPage10x15(
                x=int(request.form["photo_x"]),
                y=int(request.form["photo_y"]),
                largeur=int(request.form["photo_largeur"]),
                hauteur=int(request.form["photo_hauteur"]),
            )
        except (KeyError, TypeError, ValueError):
            flash("Coordonnées invalides.", "error")
            return redirect(url_for("templates.editer", template_id=template_id))
        if not mise_en_page.est_valide(MONTAGE_10X15_SIZE):
            flash("La zone photo doit rester entièrement dans le 10×15.", "error")
            return redirect(url_for("templates.editer", template_id=template_id))
        with connexion() as conn:
            conn.execute(
                "UPDATE template SET photo_x = ?, photo_y = ?, photo_largeur = ?, photo_hauteur = ? "
                "WHERE id = ?",
                (
                    mise_en_page.x, mise_en_page.y,
                    mise_en_page.largeur, mise_en_page.hauteur, template_id,
                ),
            )
        _synchroniser_mise_en_page_active()
        flash(f"Mise en page de « {row['nom']} » enregistrée.", "success")
        return redirect(url_for("templates.editer", template_id=template_id))

    if row["type"] == "strip":
        defaut = _mise_en_page_strip_defaut()
        valeurs = defaut
        if row["zones_strip"]:
            try:
                valeurs = MiseEnPageStrip(photos=tuple(
                    MiseEnPage10x15(**zone) for zone in json.loads(row["zones_strip"])
                ))
            except (TypeError, ValueError, json.JSONDecodeError):
                valeurs = defaut
        zones = valeurs.photos
        zones_defaut = defaut.photos
        canvas = MONTAGE_STRIP_SIZE
    else:
        valeur = _mise_en_page_defaut()
        champs = ("photo_x", "photo_y", "photo_largeur", "photo_hauteur")
        if all(row[champ] is not None for champ in champs):
            valeur = MiseEnPage10x15(
                x=row["photo_x"], y=row["photo_y"],
                largeur=row["photo_largeur"], hauteur=row["photo_hauteur"],
            )
        zones = (valeur,)
        zones_defaut = (_mise_en_page_defaut(),)
        canvas = MONTAGE_10X15_SIZE
    autre_couche = "fond" if row["couche"] == "overlay" else "overlay"
    with connexion() as conn:
        autre = conn.execute(
            "SELECT id FROM template WHERE type = ? AND couche = ? AND actif = 1",
            (row["type"], autre_couche),
        ).fetchone()
    fond_id = template_id if row["couche"] == "fond" else (autre["id"] if autre else None)
    overlay_id = template_id if row["couche"] == "overlay" else (autre["id"] if autre else None)
    return render_template(
        "template_editeur.html",
        template=row,
        zones=zones,
        canvas_w=canvas[0],
        canvas_h=canvas[1],
        fond_id=fond_id,
        overlay_id=overlay_id,
        zones_defaut=zones_defaut,
    )
