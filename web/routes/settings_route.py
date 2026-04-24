"""settings_route.py — éditeur de config_overrides.json (whitelist stricte).

Lit/écrit uniquement `data/config_overrides.json`. Les changements prennent
effet au prochain démarrage du kiosque (affiché dans l'UI).
"""
from __future__ import annotations

import json
import os
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
from web.auth import require_auth

bp = Blueprint("settings", __name__, url_prefix="/settings")


@dataclass
class Reglage:
    cle: str
    type_nom: str  # "int" | "float" | "bool" | "str"
    valeur_actuelle: Any
    overridee: bool


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


def _lister_reglages() -> list[Reglage]:
    overrides = _charger_overrides()
    reglages: list[Reglage] = []
    for cle, type_attendu in _CONFIG_OVERRIDES_WHITELIST.items():
        reglages.append(Reglage(
            cle=cle,
            type_nom=_type_nom(type_attendu),
            valeur_actuelle=getattr(config, cle),
            overridee=cle in overrides,
        ))
    return reglages


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
    return render_template(
        "settings.html",
        reglages=_lister_reglages(),
        overrides_path=CONFIG_OVERRIDES_PATH,
    )


@bp.route("/", methods=["POST"])
@require_auth
def save():
    overrides = _charger_overrides()
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
        _ecrire_overrides(overrides)
        flash(
            f"{n_modifs} réglage(s) enregistré(s). Redémarrez le kiosque pour appliquer.",
            "success",
        )
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
