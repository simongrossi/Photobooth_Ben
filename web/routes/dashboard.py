"""dashboard.py — vue d'ensemble : santé matériel, jour courant, totaux, historique."""
from __future__ import annotations

import os
from datetime import date

from flask import Blueprint, render_template

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
from core.monitoring import DiskMonitor, TempMonitor
from core.printer import PrinterManager
from stats import calculer_stats, load_sessions, stats_du_jour, stats_par_jour
from web.auth import require_auth

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

# Singleton module (pattern projet) — monkeypatché dans les tests.
printer_mgr = PrinterManager(NOM_IMPRIMANTE_10X15, NOM_IMPRIMANTE_STRIP)


def _pastille_imprimante(mode: str, libelle: str) -> dict:
    """is_ready renvoie True (prête) ou une chaîne d'erreur (contrat PrinterManager)."""
    resultat = printer_mgr.is_ready(mode)
    if resultat is True:
        return {"libelle": libelle, "etat": "ok", "detail": "prête"}
    return {"libelle": libelle, "etat": "err", "detail": str(resultat)}


def _construire_sante(disk: DiskMonitor, temp: TempMonitor) -> list[dict]:
    sante = [
        _pastille_imprimante("10x15", "Imprimante 10×15"),
        _pastille_imprimante("strips", "Imprimante strip"),
    ]
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
@require_auth
def index():
    sessions_path = os.path.join(PATH_DATA, "sessions.jsonl")
    sessions = load_sessions(sessions_path) or []
    stats = calculer_stats(sessions)

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

    jour = stats_du_jour(sessions, date.today().strftime("%Y-%m-%d"))
    historique = stats_par_jour(sessions, limite=14)
    max_total = max((j["total"] for j in historique), default=0)
    for j in historique:
        j["pct_barre"] = round(j["total"] * 100 / max_total) if max_total else 0

    total = stats.get("total", 0)
    taux_imprimees = round(stats.get("printed", 0) * 100 / total) if total else None

    return render_template(
        "dashboard.html",
        sante=_construire_sante(disk, temp),
        jour=jour,
        date_affichee=date.today().strftime("%d/%m/%Y"),
        stats=stats,
        taux_imprimees=taux_imprimees,
        historique=historique,
        sessions_path=sessions_path,
        print_path=PATH_PRINT,
    )
