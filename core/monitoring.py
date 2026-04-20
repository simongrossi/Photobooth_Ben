"""monitoring.py — sous-systèmes indépendants : disque + slideshow.

Module pur (pas de pygame, pas d'accès caméra). Expose :
- `DiskMonitor` : check périodique rate-limité de l'espace disque libre, avec
  transition OK→critique loggée une seule fois (évite le spam).
- `lister_images_slideshow()` : scan des dossiers d'impression pour alimenter
  le slideshow d'attente sur l'accueil.

Extraits de Photobooth_start.py (split boucle principale).
"""
from __future__ import annotations

import os
import shutil
import time
from typing import Optional

from core.logger import log_warning


class DiskMonitor:
    """Monitore l'espace disque libre avec rate-limit, expose un flag critique.

    Usage dans la boucle principale :
        disk = DiskMonitor(path="data", seuil_mb=500, intervalle_s=30)
        while running:
            disk.tick()                  # quasi-gratuit hors intervalle
            if disk.critique:
                afficher_bandeau_alerte(disk.libre_mb)

    Le warning log n'est émis qu'à la transition OK→critique (pas à chaque tick).
    """

    def __init__(self, path: str, seuil_mb: float, intervalle_s: float) -> None:
        self.path = path
        self.seuil_mb = seuil_mb
        self.intervalle_s = intervalle_s
        self._dernier_check_ts: float = 0.0
        self.critique: bool = False
        self.libre_mb: Optional[float] = None

    def tick(self, maintenant: Optional[float] = None) -> None:
        """Check périodique (rate-limité à `intervalle_s`). Silencieux sauf
        sur la transition OK→critique où un warning est loggé."""
        if maintenant is None:
            maintenant = time.time()
        if maintenant - self._dernier_check_ts < self.intervalle_s:
            return
        self._dernier_check_ts = maintenant
        try:
            self.libre_mb = shutil.disk_usage(self.path).free / (1024 ** 2)
            etait_critique = self.critique
            self.critique = self.libre_mb < self.seuil_mb
            if self.critique and not etait_critique:
                log_warning(
                    f"Espace disque critique : {self.libre_mb:.0f} Mo libres "
                    f"(seuil : {self.seuil_mb} Mo)"
                )
        except Exception as e:
            log_warning(f"Check disque périodique échoué : {e}")


def lister_images_slideshow(dossiers: list[str], nb_max: int) -> list[str]:
    """Scan les `dossiers` (typiquement PATH_PRINT_10X15 + PATH_PRINT_STRIP) pour
    alimenter le slideshow d'attente.

    Args:
        dossiers: liste de chemins à scanner.
        nb_max: nombre maximum de fichiers retournés.

    Returns:
        Les `nb_max` fichiers images les plus récents (tri mtime décroissant),
        avec leur chemin absolu. Dossiers manquants / fichiers inaccessibles
        sont ignorés silencieusement.
    """
    fichiers: list[tuple[float, str]] = []
    for dossier in dossiers:
        try:
            for nom in os.listdir(dossier):
                chemin = os.path.join(dossier, nom)
                if os.path.isfile(chemin) and nom.lower().endswith((".jpg", ".jpeg", ".png")):
                    try:
                        fichiers.append((os.path.getmtime(chemin), chemin))
                    except OSError:
                        continue
        except FileNotFoundError:
            continue
    fichiers.sort(key=lambda x: x[0], reverse=True)
    return [f[1] for f in fichiers[:nb_max]]
