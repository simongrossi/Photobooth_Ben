"""Télémétrie de performance structurée et peu coûteuse.

Les mesures par frame restent uniquement en mémoire. Une ligne JSON n'est
écrite qu'aux transitions importantes (capture, aperçu, montage, impression,
fin de session), afin de ne jamais ajouter d'I/O dans la boucle Pygame.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Iterable, Optional

from core.logger import log_warning


PERFORMANCE_LOG = os.path.join("logs", "performance.jsonl")


def _percentile(valeurs_triees: list[float], percentile: float) -> float:
    if not valeurs_triees:
        return 0.0
    index = round((len(valeurs_triees) - 1) * percentile)
    return valeurs_triees[index]


def resumer_durees(
    valeurs_ms: Iterable[float],
    seuil_lent_ms: Optional[float] = None,
) -> dict[str, float | int | None]:
    """Résume une petite série en mémoire, sans dépendance externe."""
    valeurs = sorted(float(v) for v in valeurs_ms)
    if not valeurs:
        return {
            "count": 0,
            "avg": None,
            "p50": None,
            "p95": None,
            "max": None,
            "slow_count": 0,
        }
    return {
        "count": len(valeurs),
        "avg": round(sum(valeurs) / len(valeurs), 3),
        "p50": round(_percentile(valeurs, 0.50), 3),
        "p95": round(_percentile(valeurs, 0.95), 3),
        "max": round(valeurs[-1], 3),
        "slow_count": (
            sum(1 for valeur in valeurs if valeur > seuil_lent_ms)
            if seuil_lent_ms is not None else 0
        ),
    }


class PerformanceJournal:
    """Journal JSONL append-only avec rotation et verrou inter-threads."""

    def __init__(self, chemin: str = PERFORMANCE_LOG, max_bytes: int = 2 * 1024 * 1024, backups: int = 5):
        self.chemin = chemin
        self.max_bytes = max_bytes
        self.backups = backups
        self._lock = threading.Lock()

    def _rotation_si_necessaire(self) -> None:
        try:
            taille = os.path.getsize(self.chemin)
        except FileNotFoundError:
            return
        if taille < self.max_bytes:
            return
        if self.backups <= 0:
            os.remove(self.chemin)
            return
        dernier = f"{self.chemin}.{self.backups}"
        if os.path.exists(dernier):
            os.remove(dernier)
        for index in range(self.backups - 1, 0, -1):
            source = f"{self.chemin}.{index}"
            if os.path.exists(source):
                os.replace(source, f"{self.chemin}.{index + 1}")
        os.replace(self.chemin, f"{self.chemin}.1")

    def ecrire(self, evenement: str, **champs) -> None:
        entree = {
            "schema": 1,
            "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "event": evenement,
            **champs,
        }
        try:
            ligne = json.dumps(entree, ensure_ascii=False, separators=(",", ":")) + "\n"
            with self._lock:
                dossier = os.path.dirname(self.chemin)
                if dossier:
                    os.makedirs(dossier, exist_ok=True)
                self._rotation_si_necessaire()
                with open(self.chemin, "a", encoding="utf-8") as fichier:
                    fichier.write(ligne)
        except (OSError, TypeError, ValueError) as exc:
            log_warning(f"Écriture télémétrie performance échouée : {exc}")


_journal = PerformanceJournal()


def ecrire_performance(evenement: str, **champs) -> None:
    """Écrit une transition mesurée ; ne doit jamais être appelée par frame."""
    _journal.ecrire(evenement, **champs)
