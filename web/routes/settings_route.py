"""settings_route.py — éditeur de config_overrides.json (whitelist stricte).

Lit/écrit `data/config_overrides.json` et peut redémarrer uniquement le service
du kiosque pour appliquer immédiatement les changements.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

import config
from config import CONFIG_OVERRIDES_PATH, _CONFIG_OVERRIDES_WHITELIST
from web import systeme
from web.auth import require_auth

bp = Blueprint("settings", __name__, url_prefix="/settings")



@dataclass
class Reglage:
    cle: str
    type_nom: str  # "int" | "float" | "bool" | "str"
    valeur_actuelle: Any
    overridee: bool
    groupe: str
    libelle: str
    description: str
    unite: str = ""


@dataclass
class GroupeReglages:
    cle: str
    titre: str
    description: str
    reglages: list[Reglage]


_GROUPES = (
    ("experience", "Expérience", "Rythme de prise de vue et sécurité des interactions."),
    ("impression", "Impression", "Files d'impression et délai affiché aux invités."),
    ("diaporama", "Diaporama", "Déclenchement et rotation des souvenirs à l'écran."),
    ("bandelettes", "Bandelettes", "Enchaînement automatique des trois prises de vue."),
    ("style", "Style photo", "Signature visuelle appliquée aux montages générés."),
    ("systeme", "Système", "Surveillance du Raspberry Pi et contrôleur Arduino."),
)

_META_REGLAGES = {
    "TEMPS_DECOMPTE": ("experience", "Durée du décompte", "Temps avant le déclenchement de la photo.", "s"),
    "DELAI_SECURITE": ("experience", "Délai anti-rebond", "Ignore les doubles pressions involontaires.", "s"),
    "NOM_IMPRIMANTE_10X15": ("impression", "Imprimante 10×15", "Nom exact de la file CUPS grand format.", ""),
    "NOM_IMPRIMANTE_STRIP": ("impression", "Imprimante bandelettes", "Nom exact de la file CUPS strips.", ""),
    "ACTIVER_IMPRESSION": ("impression", "Autoriser l'impression", "Active l'envoi des montages vers CUPS.", ""),
    "ACTIVER_IMPRESSIONS_MULTIPLES": ("impression", "Impressions multiples", "Permet aux invités de choisir plusieurs copies avant l'impression.", ""),
    "TEMPS_ATTENTE_IMP": ("impression", "Attente annoncée", "Durée indicative affichée pendant l'impression.", "s"),
    "ACTIVER_QUOTA_IMPRESSIONS": ("impression", "Bridage par quota", "Bloque l'impression quand le quota de feuilles est atteint.", ""),
    "QUOTA_IMPRESSIONS_INITIAL": ("impression", "Quota initial", "Feuilles autorisées à la création du compteur (fichier quota_impressions.json).", "feuilles"),
    "QUOTA_IMPRESSIONS_INCREMENT": ("impression", "Incrément de déblocage", "Feuilles ajoutées à chaque déblocage (code kiosque ou bouton admin).", "feuilles"),
    "ACTIVER_DIAPORAMA_VEILLE": ("diaporama", "Diaporama en veille", "Fait défiler les souvenirs après une période d'inactivité.", ""),
    "DUREE_IDLE_SLIDESHOW": ("diaporama", "Démarrer après inactivité", "Temps sans interaction avant le diaporama.", "s"),
    "DUREE_PAR_IMAGE_SLIDESHOW": ("diaporama", "Durée par image", "Temps d'affichage de chaque souvenir.", "s"),
    "NB_MAX_IMAGES_SLIDESHOW": ("diaporama", "Nombre maximal d'images", "Limite la mémoire utilisée par le diaporama.", "images"),
    "STRIP_MODE_BURST": ("bandelettes", "Mode rafale", "Enchaîne automatiquement les trois photos.", ""),
    "STRIP_BURST_DELAI_S": ("bandelettes", "Pause entre les photos", "Délai de respiration entre deux prises.", "s"),
    "WATERMARK_ENABLED": ("style", "Filigrane", "Ajoute un texte discret sur le montage final.", ""),
    "WATERMARK_TEXT": ("style", "Texte du filigrane", "Nom de l'événement ou message à afficher.", ""),
    "GRAIN_ENABLED": ("style", "Grain photo", "Ajoute une texture argentique au rendu.", ""),
    "GRAIN_INTENSITE": ("style", "Intensité du grain", "Force de la texture appliquée aux photos.", "%"),
    "SEUIL_DISQUE_CRITIQUE_MB": ("systeme", "Alerte espace disque", "Seuil sous lequel l'interface signale un danger.", "Mo"),
    "SEUIL_TEMP_CRITIQUE_C": ("systeme", "Alerte température CPU", "Seuil thermique critique du Raspberry Pi.", "°C"),
    "ARDUINO_ENABLED": ("systeme", "Boîtier Arduino", "Active les trois boutons physiques et leurs LED.", ""),
}


def _type_nom(t: type) -> str:
    return {bool: "bool", int: "int", float: "float", str: "str"}[t]


def _charger_overrides() -> dict:
    if not os.path.exists(CONFIG_OVERRIDES_PATH):
        return {}
    try:
        with open(CONFIG_OVERRIDES_PATH, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _ecrire_overrides(overrides: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_OVERRIDES_PATH), exist_ok=True)
    # Écriture atomique : fichier temporaire + rename.
    tmp = CONFIG_OVERRIDES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, CONFIG_OVERRIDES_PATH)


def _redemarrer_kiosque() -> tuple[bool, str]:
    """Redémarre seulement le kiosque (délégué à web.systeme, liste blanche)."""
    ok, message = systeme.executer_action("redemarrer-kiosque")
    if ok:
        return True, "Réglages appliqués : le service kiosque a été redémarré."
    return False, message


def _lister_reglages() -> list[Reglage]:
    overrides = _charger_overrides()
    reglages: list[Reglage] = []
    for cle, type_attendu in _CONFIG_OVERRIDES_WHITELIST.items():
        groupe, libelle, description, unite = _META_REGLAGES[cle]
        reglages.append(Reglage(
            cle=cle,
            type_nom=_type_nom(type_attendu),
            valeur_actuelle=overrides.get(cle, getattr(config, cle)),
            overridee=cle in overrides,
            groupe=groupe,
            libelle=libelle,
            description=description,
            unite=unite,
        ))
    return reglages


def _grouper_reglages(reglages: list[Reglage]) -> list[GroupeReglages]:
    return [
        GroupeReglages(
            cle=cle,
            titre=titre,
            description=description,
            reglages=[reglage for reglage in reglages if reglage.groupe == cle],
        )
        for cle, titre, description in _GROUPES
    ]


def _parser_valeur(valeur_brute: str, type_attendu: type) -> Any:
    """Convertit une string de formulaire vers le type cible. Lève ValueError si KO."""
    if type_attendu is bool:
        return valeur_brute.lower() in ("true", "1", "on", "yes")
    if type_attendu is int:
        return int(valeur_brute)
    if type_attendu is float:
        return float(valeur_brute)
    if type_attendu is str:
        if not valeur_brute:
            raise ValueError("chaîne vide")
        return valeur_brute
    raise ValueError(f"type inconnu : {type_attendu}")


@bp.route("/", methods=["GET"])
@require_auth
def index():
    reglages = _lister_reglages()
    return render_template(
        "settings.html",
        groupes=_grouper_reglages(reglages),
        nb_overrides=sum(reglage.overridee for reglage in reglages),
        overrides_path=CONFIG_OVERRIDES_PATH,
    )


@bp.route("/", methods=["POST"])
@require_auth
def save():
    overrides = _charger_overrides()
    action = request.form.get("action", "save")
    n_modifs = 0
    erreurs: list[str] = []

    for cle, type_attendu in _CONFIG_OVERRIDES_WHITELIST.items():
        # Checkboxes absentes du form = False ; les vraies str passent en texte.
        if type_attendu is bool:
            valeur_brute = "true" if request.form.get(cle) == "on" else "false"
        else:
            valeur_brute = request.form.get(cle, "").strip()
            if not valeur_brute:
                # Champ vide = suppression de l'override (retour au défaut).
                if cle in overrides:
                    del overrides[cle]
                    n_modifs += 1
                continue

        try:
            valeur = _parser_valeur(valeur_brute, type_attendu)
        except ValueError as e:
            erreurs.append(f"{cle} : {e}")
            continue

        valeur_validee = config.valeur_config_valide(cle, valeur)
        if valeur_validee is None:
            bornes = getattr(config, "_CONFIG_OVERRIDES_BOURNES", {}).get(cle)
            if bornes:
                mini, maxi = bornes
                if type_attendu is str:
                    erreurs.append(f"{cle} : longueur hors bornes [{mini}, {maxi}] caractères.")
                else:
                    erreurs.append(f"{cle} : valeur hors bornes [{mini}, {maxi}].")
            else:
                erreurs.append(f"{cle} : valeur invalide.")
            continue
        valeur = valeur_validee

        # N'enregistrer que si différent du défaut hardcodé du config.py (pour un
        # fichier overrides propre) OU si déjà présent (permet de forcer une
        # valeur identique au défaut — utile pour tracer une décision explicite).
        # Ici on choisit la version simple : on enregistre toujours la saisie.
        if overrides.get(cle) != valeur:
            overrides[cle] = valeur
            n_modifs += 1

    if erreurs:
        for e in erreurs:
            flash(e, "error")

    if n_modifs:
        # 1. Sauvegarde du fichier existant pour retour arrière
        backup_path = CONFIG_OVERRIDES_PATH + ".bak"
        existait = os.path.exists(CONFIG_OVERRIDES_PATH)
        if existait:
            try:
                shutil.copy2(CONFIG_OVERRIDES_PATH, backup_path)
            except OSError:
                pass

        # 2. Écriture du nouveau fichier
        _ecrire_overrides(overrides)

        # 3. Test de pré-vol dans un sous-processus
        preflight_ok = False
        erreur_detail = ""
        try:
            res = subprocess.run(
                [sys.executable, "-c", "import config"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=config.BASE_DIR,
            )
            if res.returncode == 0:
                preflight_ok = True
            else:
                erreur_detail = (res.stderr or res.stdout or "").strip()
        except Exception as e:
            erreur_detail = str(e)

        # 4. Traitement du résultat du pré-vol
        if preflight_ok:
            # Succès : on conserve la config comme dernière configuration valide connue
            try:
                shutil.copy2(CONFIG_OVERRIDES_PATH, CONFIG_OVERRIDES_PATH + ".last_valid")
            except OSError:
                pass
            if os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except OSError:
                    pass
        else:
            # Échec : on annule et on restaure le backup
            if existait:
                try:
                    shutil.copy2(backup_path, CONFIG_OVERRIDES_PATH)
                except OSError:
                    pass
            else:
                if os.path.exists(CONFIG_OVERRIDES_PATH):
                    try:
                        os.remove(CONFIG_OVERRIDES_PATH)
                    except OSError:
                        pass
            
            # Suppression du fichier .bak
            if os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except OSError:
                    pass

            n_modifs = 0
            flash(f"La configuration est invalide et ferait planter le kiosque (les réglages ont été restaurés) : {erreur_detail[:300]}", "error")

    if erreurs:
        if n_modifs:
            flash(f"{n_modifs} réglage(s) valide(s) enregistré(s), sans redémarrage.", "info")
    elif action == "apply" and n_modifs > 0:
        succes, message = _redemarrer_kiosque()
        flash(message, "success" if succes else "error")
    elif n_modifs:
        flash(f"{n_modifs} réglage(s) enregistré(s).", "success")
    elif not erreurs:
        flash("Aucun changement.", "info")

    return redirect(url_for("settings.index"))


@bp.route("/reset", methods=["POST"])
@require_auth
def reset():
    """Supprime config_overrides.json — retour aux défauts du code."""
    if os.path.exists(CONFIG_OVERRIDES_PATH):
        os.remove(CONFIG_OVERRIDES_PATH)
        flash("Overrides supprimés. Redémarrez le kiosque pour appliquer.", "success")
    else:
        flash("Aucun override à supprimer.", "info")
    return redirect(url_for("settings.index"))
