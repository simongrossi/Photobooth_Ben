"""dashboard.py — vue d'ensemble : santé matériel, jour courant, totaux, historique."""
from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

import config

from config import (
    INTERVALLE_CHECK_DISQUE_S,
    INTERVALLE_CHECK_TEMP_S,
    NOM_IMPRIMANTE_10X15,
    NOM_IMPRIMANTE_STRIP,
    PATH_DATA,
    PATH_PRINT,
    SEUIL_DISQUE_CRITIQUE_MB,
    SEUIL_TEMP_CRITIQUE_C,
    TEMP_PATH,
)
from core import ecrans, quota
from core.monitoring import DiskMonitor, TempMonitor
from core.performance import ecrire_performance
from core.printer import PrinterManager
from stats import calculer_stats, filtrer_sessions, load_sessions, stats_du_jour, stats_par_jour
from web import systeme
from web.auth import require_auth, require_lecture
from web.evenements import lister_evenements, tous_les_tags

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

# Singleton module (pattern projet) — monkeypatché dans les tests.
printer_mgr = PrinterManager(NOM_IMPRIMANTE_10X15, NOM_IMPRIMANTE_STRIP)

HEURES_ORDRE = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6, 7]

PERIODES = {
    "aujourdhui": {"libelle": "Aujourd'hui", "nb_jours": 1},
    "2jours": {"libelle": "2 derniers jours", "nb_jours": 2},
    "7jours": {"libelle": "7 derniers jours", "nb_jours": 7},
    "toutes": {"libelle": "Tout depuis le début", "nb_jours": None},
}


def _maintenant_serveur() -> datetime:
    """Heure locale effective de la machine qui héberge l'admin."""
    return datetime.now().astimezone()


def _contexte_heure_serveur() -> dict:
    maintenant = _maintenant_serveur()
    decalage = maintenant.utcoffset()
    return {
        "serveur_epoch_ms": round(maintenant.timestamp() * 1000),
        "serveur_offset_minutes": int(decalage.total_seconds() // 60) if decalage else 0,
        "serveur_heure_texte": maintenant.strftime("%d/%m/%Y %H:%M:%S"),
    }


@bp.route("/heure")
@require_lecture
def heure_serveur():
    """Point de resynchronisation de l'horloge persistante du dashboard."""
    return jsonify(_contexte_heure_serveur())


def _filtrer_sessions_par_periode(
    sessions: list[dict], periode: str, aujourd_hui: date | None = None,
) -> tuple[list[dict], str]:
    """Filtre par jours calendaires, aujourd'hui étant inclus dans la période."""
    # Compatibilité avec les anciens liens/bookmarks du dashboard.
    if periode == "recent":
        periode = "7jours"
    if periode not in PERIODES:
        periode = "7jours"
    if periode == "toutes":
        return sessions, periode

    aujourd_hui = aujourd_hui or date.today()
    date_seuil = aujourd_hui - timedelta(days=PERIODES[periode]["nb_jours"] - 1)
    resultat = []
    for session in sessions:
        try:
            date_session = date.fromisoformat(session.get("ts", "")[:10])
        except (TypeError, ValueError):
            continue
        if date_seuil <= date_session <= aujourd_hui:
            resultat.append(session)
    return resultat, periode


def _pastille_imprimante(mode: str, libelle: str) -> dict:
    """Résume la file CUPS avant de vérifier l'état physique."""
    jobs = printer_mgr.jobs_en_attente(mode)
    if jobs:
        suffixe = "job" if jobs == 1 else "jobs"
        return {"libelle": libelle, "etat": "warn", "detail": f"{jobs} {suffixe} en file"}
    resultat = printer_mgr.is_ready(mode)
    if resultat is True:
        detail = "prête · file vide" if jobs == 0 else "prête · file inconnue"
        return {"libelle": libelle, "etat": "ok", "detail": detail}
    return {"libelle": libelle, "etat": "err", "detail": str(resultat)}


def _age_texte(timestamp: object, maintenant: float) -> str:
    try:
        age = max(0, int(maintenant - float(timestamp)))
    except (TypeError, ValueError):
        return "inconnue"
    if age < 60:
        return f"il y a {age} s"
    if age < 3600:
        return f"il y a {age // 60} min"
    return datetime.fromtimestamp(float(timestamp)).strftime("%d/%m %H:%M")


def _vue_heartbeat(etat: dict | None, maintenant: float | None = None) -> dict:
    maintenant = maintenant or time.time()
    frais = ecrans.heartbeat_est_frais(etat, maintenant=maintenant)
    if not etat:
        return {
            "disponible": False,
            "frais": False,
            "session_active": False,
            "etat": "INCONNU",
            "heartbeat_age": "jamais reçu",
            "activite_age": "inconnue",
        }
    return {
        **etat,
        "disponible": True,
        "frais": frais,
        "session_active": bool(frais and etat.get("session_active")),
        "etat": etat.get("etat", "INCONNU"),
        "heartbeat_age": _age_texte(etat.get("heartbeat_ts"), maintenant),
        "activite_age": _age_texte(etat.get("derniere_activite_ts"), maintenant),
        "dernier_tirage_age": _age_texte(etat.get("dernier_tirage_reussi_ts"), maintenant),
    }


def _construire_sante(
    disk: DiskMonitor,
    temp: TempMonitor,
    heartbeat: dict | None = None,
) -> list[dict]:
    etats_kiosque = {"active": ("ok", "actif"), "inactive": ("warn", "arrêté"),
                     "failed": ("err", "en panne"), "indisponible": ("na", "N/A")}
    etat_k = systeme.etat_kiosque()
    etat, detail = etats_kiosque.get(etat_k, ("na", etat_k))
    sante = [
        {"libelle": "Kiosque", "etat": etat, "detail": detail},
        _pastille_imprimante("10x15", "Imprimante 10×15"),
        _pastille_imprimante("strips", "Imprimante strip"),
    ]
    vue = _vue_heartbeat(heartbeat)
    if vue["frais"]:
        sante.append({
            "libelle": "Écran",
            "etat": "warn" if vue["session_active"] else "ok",
            "detail": f"{vue['etat']} · signal {vue['heartbeat_age']}",
        })
        sante.append({
            "libelle": "Caméra",
            "etat": "ok" if vue.get("camera_connected") else "err",
            "detail": "connectée" if vue.get("camera_connected") else "déconnectée",
        })
        if not vue.get("arduino_enabled"):
            sante.append({"libelle": "Arduino", "etat": "na", "detail": "désactivé"})
        else:
            sante.append({
                "libelle": "Arduino",
                "etat": "ok" if vue.get("arduino_available") else "err",
                "detail": "connecté" if vue.get("arduino_available") else "indisponible",
            })
    else:
        detail = f"signal périmé · {vue['heartbeat_age']}" if vue["disponible"] else "jamais reçu"
        sante.extend([
            {"libelle": "Supervision", "etat": "err", "detail": detail},
            {"libelle": "Caméra", "etat": "na", "detail": "N/A"},
            {"libelle": "Arduino", "etat": "na", "detail": "N/A"},
        ])

    if heartbeat and heartbeat.get("dernier_tirage_reussi_ts"):
        mode = heartbeat.get("dernier_tirage_reussi_mode") or "mode inconnu"
        sante.append({
            "libelle": "Dernier tirage",
            "etat": "ok",
            "detail": f"{vue['dernier_tirage_age']} · {mode}",
        })
    else:
        sante.append({"libelle": "Dernier tirage", "etat": "na", "detail": "aucun signalé"})
    if disk.libre_mb is None:
        sante.append({"libelle": "Disque", "etat": "na", "detail": "N/A"})
    else:
        libre = f"{disk.libre_mb / 1024:.0f} Go" if disk.libre_mb >= 1024 else f"{disk.libre_mb:.0f} Mo"
        sante.append({"libelle": "Disque", "etat": "err" if disk.critique else "ok", "detail": libre})
    if temp.temp_c is None:
        sante.append({"libelle": "CPU", "etat": "na", "detail": "N/A"})
    else:
        sante.append({
            "libelle": "CPU",
            "etat": "err" if temp.critique else "ok",
            "detail": f"{temp.temp_c:.0f} °C",
        })
    return sante


@bp.route("/")
@require_lecture
def index():
    periode = request.args.get("periode", "7jours")
    evenement_filtre = request.args.get("evenement", "")
    tag_filtre = request.args.get("tag", "")
    sessions_path = os.path.join(config.PATH_DATA, "sessions.jsonl")
    sessions = load_sessions(sessions_path) or []
    tags_disponibles = sorted(
        set(tous_les_tags())
        | {str(tag) for session in sessions for tag in session.get("event_tags", [])},
        key=str.casefold,
    )
    sessions_filtrees = filtrer_sessions(sessions, evenement_filtre, tag_filtre)
    sessions_a_calculer, periode = _filtrer_sessions_par_periode(sessions_filtrees, periode)

    stats = calculer_stats(sessions_a_calculer)

    disk = DiskMonitor(
        path=PATH_DATA,
        seuil_mb=SEUIL_DISQUE_CRITIQUE_MB,
        intervalle_s=INTERVALLE_CHECK_DISQUE_S,
    )
    disk.intervalle_s = 0  # force un check immédiat pour le dashboard
    disk.tick()

    temp = TempMonitor(
        path=TEMP_PATH,
        seuil_c=SEUIL_TEMP_CRITIQUE_C,
        intervalle_s=INTERVALLE_CHECK_TEMP_S,
    )
    temp.intervalle_s = 0
    temp.tick()
    heartbeat_brut = ecrans.lire_etat_kiosque()
    heartbeat = _vue_heartbeat(heartbeat_brut)

    jour = stats_du_jour(sessions_filtrees, date.today().strftime("%Y-%m-%d"))
    limite_hist = 100 if periode == "toutes" else 7
    historique = stats_par_jour(sessions_a_calculer, limite=limite_hist)
    max_total = max((j["total"] for j in historique), default=0)
    for j in historique:
        j["pct_barre"] = round(j["total"] * 100 / max_total) if max_total else 0

    total = stats.get("total", 0)
    taux_imprimees = round(stats.get("printed", 0) * 100 / total) if total else None

    # Préparation des listes de répartition horaire ordonnées (début à 8h)
    heures_jour = []
    if jour.get("total", 0) > 0:
        heures_jour = [{"heure": h, "nb": jour.get("heures", {}).get(h, 0)} for h in HEURES_ORDRE]

    heures_total = []
    if stats.get("total", 0) > 0:
        heures_total = [{"heure": h, "nb": stats.get("heures", {}).get(h, 0)} for h in HEURES_ORDRE]

    quota_etat = quota.charger_etat()
    quota_rest = quota.quota_restant()
    quota_pct = (
        round(quota_etat["tirages_total"] * 100 / quota_etat["quota"]) if quota_etat["quota"] else 100
    )

    return render_template(
        "dashboard.html",
        quota_etat=quota_etat,
        quota_restant=quota_rest,
        quota_pct=min(100, quota_pct),
        quota_actif=config.ACTIVER_QUOTA_IMPRESSIONS,
        quota_increment=config.QUOTA_IMPRESSIONS_INCREMENT,
        sante=_construire_sante(disk, temp, heartbeat_brut),
        heartbeat=heartbeat,
        jour=jour,
        date_affichee=date.today().strftime("%d/%m/%Y"),
        stats=stats,
        taux_imprimees=taux_imprimees,
        historique=historique,
        heures_jour=heures_jour,
        heures_total=heures_total,
        sessions_path=sessions_path,
        print_path=PATH_PRINT,
        periode=periode,
        periodes=PERIODES,
        periode_libelle=PERIODES[periode]["libelle"],
        evenement_filtre=evenement_filtre,
        tag_filtre=tag_filtre,
        evenements=lister_evenements(),
        tags=tags_disponibles,
        **_contexte_heure_serveur(),
    )


@bp.route("/quota/debloquer", methods=["POST"])
@require_auth
def debloquer_quota():
    """Déblocage admin : augmente le plafond du même palier que le code kiosque."""
    increment = config.QUOTA_IMPRESSIONS_INCREMENT
    etat = quota.debloquer(increment)
    ecrire_performance(
        "quota_deblocage",
        source="web",
        increment=increment,
        quota=etat["quota"],
        tirages_total=etat["tirages_total"],
    )
    restant = max(0, etat["quota"] - etat["tirages_total"])
    flash(f"Quota débloqué : +{increment} impressions (restant : {restant}).", "success")
    return redirect(url_for("dashboard.index"))


@bp.route("/systeme/<action>", methods=["POST"])
@require_auth
def action_systeme(action: str):
    """Contrôle du kiosque (liste blanche web/systeme.py). Admin uniquement."""
    try:
        ok, message = systeme.executer_action(action)
    except ValueError:
        abort(404)
    flash(message, "success" if ok else "error")
    return redirect(url_for("dashboard.index"))
