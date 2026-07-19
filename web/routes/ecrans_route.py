"""ecrans_route.py — inventaire et éditeur des écrans du kiosque.

Répond à « jamais de surprises » : pour chaque écran, la page montre le fond
*réellement* résolu (pas celui qu'on croit avoir activé) et les textes, durées,
tailles et positions en vigueur, en signalant ceux qui ont été personnalisés.

Le formulaire est généré depuis `core.ecrans.REGISTRE` : chaque champ porte son
libellé et son aide, il n'y a donc aucune table de métadonnées à maintenir en
parallèle — contrairement à `_META_REGLAGES` de settings_route, qui doit être
tenue à jour à la main sous peine de KeyError.

Écrit `data/ecrans_overrides.json`, jamais `config_overrides.json` : les deux
éditeurs ont des périmètres disjoints (test d'intersection vide dans
tests/test_ecrans.py) et se réinitialisent indépendamment.
"""
from __future__ import annotations

import io
import os
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
from PIL import Image

import config
from core import ecrans
from web import systeme
from web.auth import require_auth

bp = Blueprint("ecrans", __name__, url_prefix="/ecrans")

APERCU_MAX = (420, 264)  # ratio proche du 1280×800 du kiosque

# Écrans dont l'aperçu positionné sait reproduire la géométrie du kiosque.
# Volontairement restreint : un aperçu approximatif serait pire qu'aucun
# aperçu, puisqu'on réglerait des positions en se fiant à une image fausse.
ECRANS_AVEC_APERCU = ("accueil",)

# Regroupement du formulaire, dans l'ordre d'affichage. Une nature absente
# d'ici verrait ses champs disparaître SILENCIEUSEMENT du formulaire — un test
# vérifie donc que cette liste couvre toutes les natures du registre.
GROUPES_PAR_NATURE = (
    (ecrans.TEXTE, "Textes affichés"),
    (ecrans.COULEUR, "Couleurs"),
    (ecrans.DUREE, "Durées"),
    (ecrans.TAILLE, "Tailles"),
    (ecrans.POSITION, "Positions et opacités"),
    (ecrans.BASCULE, "Options"),
)

# Images servies à l'aperçu, par clé fixe (jamais un chemin depuis la requête).
_IMAGES_APERCU = {
    "icone-10x15": "PATH_IMG_10X15",
    "icone-strip": "PATH_IMG_STRIP",
}


def _parser_valeur(valeur_brute: str, type_attendu: type):
    """Convertit une saisie de formulaire vers le type cible. ValueError si KO.

    Même sémantique que settings_route._parser_valeur : les deux formulaires
    doivent se comporter pareil pour l'utilisateur.
    """
    if type_attendu is bool:
        return valeur_brute.lower() in ("true", "1", "on", "yes")
    if type_attendu is config.Couleur:
        # Laisser passer tel quel : `valeur_ecran_valide` rejettera ce qui n'est
        # pas un #rrggbb, avec le même message d'erreur que les autres types.
        return valeur_brute
    if type_attendu is int:
        return int(valeur_brute)
    if type_attendu is float:
        return float(valeur_brute)
    if type_attendu is str:
        if not valeur_brute:
            raise ValueError("chaîne vide")
        return valeur_brute
    raise ValueError(f"type inconnu : {type_attendu}")


def _etat_kiosque_pour_gabarit() -> dict:
    """Ce que l'admin doit savoir avant de proposer un redémarrage."""
    etat = ecrans.lire_etat_kiosque()
    return {
        "connu": etat is not None,
        "en_ligne": ecrans.heartbeat_est_frais(etat),
        "session_active": ecrans.session_kiosque_active(etat),
        "redemarrage_requis": ecrans.redemarrage_requis(),
        "service": systeme.etat_kiosque(),
    }


def _vue_champ(champ: ecrans.ChampEditable, overrides: dict) -> dict:
    """Aplatit un champ pour le gabarit (Jinja n'accède pas aux dataclass frozen
    aussi commodément que les dicts, et on veut les bornes à côté de la valeur)."""
    bornes = champ.bornes
    type_attendu, mini, maxi = bornes if bornes else (str, None, None)
    return {
        "cle": champ.cle,
        "libelle": champ.libelle,
        "nature": champ.nature,
        "aide": champ.aide,
        "unite": champ.unite,
        "valeur": champ.defaut,
        "personnalise": champ.cle in overrides,
        "type_nom": type_attendu.__name__,
        "mini": mini,
        "maxi": maxi,
        "est_bool": type_attendu is bool,
        "est_texte": type_attendu is str,
        "est_couleur": type_attendu is config.Couleur,
        # Le formulaire manipule du #rrggbb ; config garde des tuples RGB.
        "hexa": config.Couleur.vers_hexa(champ.defaut) if type_attendu is config.Couleur else "",
        # Les floats ont besoin d'un pas explicite, sinon le champ number
        # n'accepte que les entiers dans la plupart des navigateurs.
        "pas": "0.1" if type_attendu is float else "1",
    }


@bp.route("/", methods=["GET"])
@require_auth
def index():
    """Inventaire : un écran par carte, avec son fond réel et ses réglages."""
    overrides = ecrans.charger_overrides()
    assets = ecrans.resoudre_assets()
    cartes = []
    for e in ecrans.REGISTRE:
        champs = [_vue_champ(c, overrides) for c in e.champs]
        cartes.append({
            "id": e.id,
            "libelle": e.libelle,
            "description": e.description,
            "asset": assets[e.id],
            "champs": champs,
            "nb_personnalises": sum(c["personnalise"] for c in champs),
        })
    return render_template(
        "ecrans.html",
        cartes=cartes,
        nb_overrides=len(overrides),
        overrides_path=config.ECRANS_OVERRIDES_PATH,
        kiosque=_etat_kiosque_pour_gabarit(),
    )


@bp.route("/apercu/<ecran_id>", methods=["GET"])
@require_auth
def apercu(ecran_id: str):
    """Vignette du fond réellement résolu pour cet écran.

    Sert l'asset tel qu'il est sur disque : c'est tout l'intérêt, l'admin voit
    l'image que le kiosque chargera, pas celle qu'il a cru activer.
    """
    e = ecrans.ecran(ecran_id)
    if e is None:
        abort(404)
    asset = ecrans.resoudre_assets()[ecran_id]
    if not asset.existe or not asset.chemin:
        abort(404)
    try:
        with Image.open(asset.chemin) as img:
            img = img.convert("RGB")
            img.thumbnail(APERCU_MAX)
            tampon = io.BytesIO()
            img.save(tampon, format="PNG")
    except OSError:
        abort(404)
    tampon.seek(0)
    return send_file(tampon, mimetype="image/png")


@bp.route("/police.ttf", methods=["GET"])
@require_auth
def police():
    """Sert la police effective du kiosque, pour le @font-face de l'aperçu.

    Sans elle, l'aperçu mesurerait les textes avec une police système et les
    débordements observés ne correspondraient à rien.
    """
    chemin = config.POLICE_EFFECTIVE
    if not os.path.isfile(chemin):
        abort(404)
    return send_file(chemin, mimetype="font/ttf")


@bp.route("/image/<cle>", methods=["GET"])
@require_auth
def image(cle: str):
    """Sert une image d'interface référencée par clé fixe (icônes de l'accueil)."""
    attribut = _IMAGES_APERCU.get(cle)
    if attribut is None:
        abort(404)
    chemin = getattr(config, attribut, None)
    if not chemin or not os.path.isfile(chemin):
        abort(404)
    return send_file(chemin)


def _geometrie_apercu(ecran_id: str) -> Optional[dict]:
    """Constantes nécessaires pour rejouer la géométrie de l'écran en HTML.

    Reproduit les formules de `_render_accueil_normal` (Photobooth_start.py) —
    tout changement là-bas doit être répercuté ici, un test compare les deux.
    """
    if ecran_id not in ECRANS_AVEC_APERCU:
        return None
    return {
        "largeur": config.WIDTH,
        "hauteur": config.HEIGHT,
        # axe_y_centre = (HEIGHT // 2) - 60
        "axe_y_centre": (config.HEIGHT // 2) - 60,
        "decalage_label": 20,          # px sous l'icône (constante du rendu)
        "zoom_factor": config.ZOOM_FACTOR,
        "bandeau_couleur": config.Couleur.vers_hexa(config.BANDEAU_COULEUR),
        "couleur_texte_repos": config.Couleur.vers_hexa(config.COULEUR_TEXTE_REPOS),
        "couleur_texte_on": config.Couleur.vers_hexa(config.COULEUR_TEXTE_ON),
        "alpha_texte_repos": config.ALPHA_TEXTE_REPOS,
    }


@bp.route("/<ecran_id>", methods=["GET"])
@require_auth
def editer(ecran_id: str):
    """Formulaire d'un écran, groupé par nature de réglage."""
    e = ecrans.ecran(ecran_id)
    if e is None:
        abort(404)
    overrides = ecrans.charger_overrides()
    champs = [_vue_champ(c, overrides) for c in e.champs]
    groupes = []
    for nature, titre in GROUPES_PAR_NATURE:
        du_groupe = [c for c in champs if c["nature"] == nature]
        if du_groupe:
            groupes.append({"titre": titre, "champs": du_groupe})
    return render_template(
        "ecran_editeur.html",
        ecran=e,
        asset=ecrans.resoudre_assets()[ecran_id],
        groupes=groupes,
        nb_personnalises=sum(c["personnalise"] for c in champs),
        kiosque=_etat_kiosque_pour_gabarit(),
        geometrie=_geometrie_apercu(ecran_id),
    )


@bp.route("/<ecran_id>", methods=["POST"])
@require_auth
def enregistrer(ecran_id: str):
    """Enregistre les réglages d'un écran.

    Un champ laissé vide supprime son override (retour au défaut du code), même
    sémantique que la page Réglages. Une valeur hors bornes est refusée AVANT
    écriture : le fichier sur disque reste toujours applicable tel quel.
    """
    e = ecrans.ecran(ecran_id)
    if e is None:
        abort(404)

    overrides = ecrans.charger_overrides()
    action = request.form.get("action", "save")
    n_modifs = 0
    erreurs: list[str] = []

    for champ in e.champs:
        bornes = champ.bornes
        if bornes is None:
            continue
        type_attendu, mini, maxi = bornes

        if type_attendu is bool:
            valeur_brute = "true" if request.form.get(champ.cle) == "on" else "false"
        else:
            valeur_brute = request.form.get(champ.cle, "").strip()
            if not valeur_brute:
                # Champ vide = retour au défaut.
                if champ.cle in overrides:
                    del overrides[champ.cle]
                    n_modifs += 1
                continue

        try:
            valeur = _parser_valeur(valeur_brute, type_attendu)
        except ValueError:
            erreurs.append(f"{champ.libelle} : « {valeur_brute} » n'est pas un {type_attendu.__name__} valide.")
            continue

        validee = config.valeur_ecran_valide(champ.cle, valeur)
        if validee is None:
            if type_attendu is config.Couleur:
                erreurs.append(
                    f"{champ.libelle} : « {valeur_brute} » n'est pas une couleur "
                    "valide (format attendu : #rrggbb, par exemple #ff0000)."
                )
            else:
                unite = f" {champ.unite}" if champ.unite else ""
                attendu = "longueur" if type_attendu is str else "valeur"
                erreurs.append(
                    f"{champ.libelle} : {attendu} hors bornes (attendu entre {mini} et {maxi}{unite})."
                )
            continue

        # Les couleurs sont stockées en #rrggbb : lisible dans le fichier, et
        # directement réutilisable par le sélecteur HTML au rechargement.
        a_stocker = config.Couleur.vers_hexa(validee) if type_attendu is config.Couleur else validee

        if overrides.get(champ.cle) != a_stocker:
            # Réenregistrer le défaut du code n'a pas à créer d'override.
            if validee == getattr(config, champ.cle, object()) and champ.cle not in overrides:
                continue
            overrides[champ.cle] = a_stocker
            n_modifs += 1

    for erreur in erreurs:
        flash(erreur, "error")

    if erreurs:
        flash("Aucune modification enregistrée : corrigez les erreurs ci-dessus.", "error")
        return redirect(url_for("ecrans.editer", ecran_id=ecran_id))

    if n_modifs:
        ecrans.ecrire_overrides(overrides)

    if action == "apply" and n_modifs:
        succes, message = systeme.executer_action("redemarrer-kiosque")
        flash(message, "success" if succes else "error")
    elif n_modifs:
        flash(
            f"{n_modifs} réglage(s) enregistré(s). Effet au prochain redémarrage du kiosque.",
            "success",
        )
    else:
        flash("Aucun changement.", "info")

    return redirect(url_for("ecrans.editer", ecran_id=ecran_id))


@bp.route("/reset", methods=["POST"])
@require_auth
def reset():
    """Supprime ecrans_overrides.json. Ne touche pas aux Réglages."""
    if ecrans.reinitialiser_overrides():
        flash(
            "Réglages d'écran supprimés. Effet au prochain redémarrage du kiosque. "
            "(Les Réglages généraux sont inchangés.)",
            "success",
        )
    else:
        flash("Aucun réglage d'écran personnalisé à supprimer.", "info")
    return redirect(url_for("ecrans.index"))


@bp.route("/redemarrer", methods=["POST"])
@require_auth
def redemarrer():
    """Applique les réglages en attente en redémarrant le kiosque."""
    succes, message = systeme.executer_action("redemarrer-kiosque")
    flash(message, "success" if succes else "error")
    return redirect(url_for("ecrans.index"))
