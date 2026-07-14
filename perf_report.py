#!/usr/bin/env python3
"""Analyse les mesures matérielles de ``logs/performance.jsonl``.

Usage :
    python3 perf_report.py
    python3 perf_report.py --date 2026-07-15
    python3 perf_report.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Iterable

from core.performance import PERFORMANCE_LOG, resumer_durees


def charger_evenements(chemin: str, inclure_rotations: bool = True) -> list[dict]:
    chemins = []
    if inclure_rotations:
        rotations = [f"{chemin}.{index}" for index in range(5, 0, -1)]
        chemins.extend(path for path in rotations if os.path.isfile(path))
    if os.path.isfile(chemin):
        chemins.append(chemin)

    evenements = []
    for path in chemins:
        with open(path, encoding="utf-8") as fichier:
            for ligne in fichier:
                try:
                    entree = json.loads(ligne)
                except json.JSONDecodeError:
                    continue
                if isinstance(entree, dict) and entree.get("event"):
                    evenements.append(entree)
    return evenements


def _extraire(entree: dict, chemin: tuple[str, ...]) -> Any:
    valeur: Any = entree
    for cle in chemin:
        if not isinstance(valeur, dict):
            return None
        valeur = valeur.get(cle)
    return valeur


def _valeurs(
    evenements: Iterable[dict],
    type_evenement: str,
    chemin: tuple[str, ...],
) -> list[float]:
    resultat = []
    for entree in evenements:
        if entree.get("event") != type_evenement:
            continue
        valeur = _extraire(entree, chemin)
        if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
            resultat.append(float(valeur))
    return resultat


def _resume(evenements: list[dict], event: str, *chemin: str) -> dict:
    return resumer_durees(_valeurs(evenements, event, tuple(chemin)))


def analyser_evenements(evenements: list[dict]) -> dict:
    captures = [e for e in evenements if e.get("event") == "capture"]
    sessions = [e for e in evenements if e.get("event") == "session_end"]
    mesures = {
        "first_frame_ms": _resume(captures, "capture", "camera_preview", "first_frame_ms"),
        "preview_fps": _resume(captures, "capture", "preview_fps"),
        "camera_acquisition_p95_ms": _resume(
            captures, "capture", "camera_preview", "acquisition_ms", "p95"
        ),
        "camera_decode_p95_ms": _resume(
            captures, "capture", "camera_preview", "decode_ms", "p95"
        ),
        "countdown_render_p95_ms": _resume(
            captures, "capture", "countdown_render_ms", "p95"
        ),
        "capture_total_ms": _resume(captures, "capture", "capture_total_ms"),
        "preview_validation_ms": _resume(evenements, "preview_validation", "duration_ms"),
        "montage_final_ms": _resume(evenements, "montage_final", "duration_ms"),
        "printer_check_ms": _resume(evenements, "printer_check", "duration_ms"),
        "printer_submit_ms": _resume(evenements, "printer_submit", "duration_ms"),
        "temperature_c": _resume(captures, "capture", "temperature_c"),
        "rss_mb": _resume(captures, "capture", "rss_mb"),
    }

    alertes = []
    first_frame_p95 = mesures["first_frame_ms"]["p95"]
    preview_fps_avg = mesures["preview_fps"]["avg"]
    render_p95 = mesures["countdown_render_p95_ms"]["p95"]
    capture_p95 = mesures["capture_total_ms"]["p95"]
    validation_p95 = mesures["preview_validation_ms"]["p95"]
    montage_p95 = mesures["montage_final_ms"]["p95"]
    temperature_max = mesures["temperature_c"]["max"]

    if first_frame_p95 is not None and first_frame_p95 > 500:
        alertes.append("Première frame lente : p95 > 500 ms")
    if preview_fps_avg is not None and preview_fps_avg < 12:
        alertes.append("LiveView faible : moyenne < 12 nouvelles frames/s")
    if render_p95 is not None and render_p95 > 25:
        alertes.append("Rendu décompte chargé : p95 > 25 ms")
    if capture_p95 is not None and capture_p95 > 5000:
        alertes.append("Capture HQ lente : p95 > 5 s")
    if validation_p95 is not None and validation_p95 > 500:
        alertes.append("Aperçu de validation lent : p95 > 500 ms")
    if montage_p95 is not None and montage_p95 > 3000:
        alertes.append("Montage final lent : p95 > 3 s")
    if temperature_max is not None and temperature_max >= 75:
        alertes.append("Température élevée : maximum >= 75 °C")

    rss = _valeurs(captures, "capture", ("rss_mb",))
    rss_growth = round(rss[-1] - rss[0], 3) if len(rss) >= 5 else None
    if rss_growth is not None and rss_growth > 20:
        alertes.append("Croissance mémoire suspecte : RSS +20 Mo ou plus")

    par_mode = {}
    for mode in ("10x15", "strips"):
        sous_ensemble = [e for e in evenements if e.get("mode") == mode]
        if sous_ensemble:
            par_mode[mode] = {
                "captures": sum(e.get("event") == "capture" for e in sous_ensemble),
                "capture_total_ms": _resume(sous_ensemble, "capture", "capture_total_ms"),
                "montage_final_ms": _resume(sous_ensemble, "montage_final", "duration_ms"),
            }

    return {
        "records": len(evenements),
        "captures": len(captures),
        "sessions": len(sessions),
        "metrics": mesures,
        "rss_growth_mb": rss_growth,
        "alerts": alertes,
        "by_mode": par_mode,
    }


def afficher_rapport(rapport: dict) -> None:
    print("RAPPORT PERFORMANCE PHOTOBOOTH")
    print(f"Enregistrements : {rapport['records']} | Captures : {rapport['captures']} | Sessions : {rapport['sessions']}")
    if rapport["captures"] == 0:
        print("Aucune capture mesurée. Réaliser plusieurs sessions sur le Raspberry Pi.")
        return

    libelles = {
        "first_frame_ms": "Première frame",
        "preview_fps": "Nouvelles frames/s",
        "camera_acquisition_p95_ms": "Acquisition Canon p95",
        "camera_decode_p95_ms": "Décodage p95",
        "countdown_render_p95_ms": "Rendu décompte p95",
        "capture_total_ms": "Capture totale",
        "preview_validation_ms": "Aperçu validation",
        "montage_final_ms": "Montage final",
        "printer_check_ms": "Contrôle CUPS",
        "printer_submit_ms": "Envoi CUPS",
        "temperature_c": "Température",
        "rss_mb": "RSS",
    }
    for cle, libelle in libelles.items():
        mesure = rapport["metrics"][cle]
        if mesure["count"]:
            print(
                f"- {libelle:<24} moyenne={mesure['avg']:.1f} "
                f"p95={mesure['p95']:.1f} max={mesure['max']:.1f} n={mesure['count']}"
            )

    if rapport["rss_growth_mb"] is not None:
        print(f"- Croissance RSS          {rapport['rss_growth_mb']:+.1f} Mo")
    if rapport["alerts"]:
        print("\nAlertes :")
        for alerte in rapport["alerts"]:
            print(f"  ⚠ {alerte}")
    else:
        print("\nAucune alerte avec les seuils actuels.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=PERFORMANCE_LOG, help="Chemin du JSONL de performance")
    parser.add_argument("--date", help="Filtre YYYY-MM-DD")
    parser.add_argument("--json", action="store_true", help="Rapport JSON")
    args = parser.parse_args()

    evenements = charger_evenements(args.file)
    if args.date:
        evenements = [e for e in evenements if str(e.get("ts", "")).startswith(args.date)]
    rapport = analyser_evenements(evenements)
    if args.json:
        print(json.dumps(rapport, ensure_ascii=False, indent=2))
    else:
        afficher_rapport(rapport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
