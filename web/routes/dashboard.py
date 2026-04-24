"""dashboard.py — vue d'ensemble (stats, disque, température)."""
from __future__ import annotations

import os

from flask import Blueprint, render_template

from config import (
    INTERVALLE_CHECK_DISQUE_S,
    INTERVALLE_CHECK_TEMP_S,
    PATH_DATA,
    PATH_PRINT,
    SEUIL_DISQUE_CRITIQUE_MB,
    SEUIL_TEMP_CRITIQUE_C,
    TEMP_PATH,
)
from core.monitoring import DiskMonitor, TempMonitor
from stats import calculer_stats, load_sessions
from web.auth import require_auth

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


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

    return render_template(
        "dashboard.html",
        stats=stats,
        disk=disk,
        temp=temp,
        sessions_path=sessions_path,
        print_path=PATH_PRINT,
    )
