"""monitoring.py — sous-systèmes indépendants : disque + température + slideshow.

Module pur (pas de pygame, pas d'accès caméra). Expose :
- `DiskMonitor` : check périodique rate-limité de l'espace disque libre
- `TempMonitor` : idem pour la température CPU (Raspberry Pi)
- `lister_images_slideshow()` : scan des dossiers d'impression pour alimenter
  le slideshow d'attente sur l'accueil

Les deux monitors partagent le même pattern : `tick()` rate-limité, flag
`critique`, log warning sur la transition OK→critique uniquement.
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


class TempMonitor:
    """Monitore la température CPU (Raspberry Pi) et expose un flag critique.

    Lit le fichier `/sys/class/thermal/thermal_zone0/temp` (Pi / Linux standard)
    qui retourne la température en millidegrés Celsius. Sur macOS/Windows ou si
    le fichier n'existe pas, `temp_c` reste None et `critique` reste False —
    le monitor est inerte silencieusement.

    Usage :
        temp = TempMonitor(path="/sys/class/thermal/thermal_zone0/temp",
                           seuil_c=75.0, intervalle_s=30)
        while running:
            temp.tick()
            if temp.critique:
                afficher_bandeau_alerte(temp.temp_c)
    """

    def __init__(self, path: str, seuil_c: float, intervalle_s: float) -> None:
        self.path = path
        self.seuil_c = seuil_c
        self.intervalle_s = intervalle_s
        self._dernier_check_ts: float = 0.0
        self.critique: bool = False
        self.temp_c: Optional[float] = None

    def tick(self, maintenant: Optional[float] = None) -> None:
        """Check périodique (rate-limité à `intervalle_s`). Silencieux sauf
        sur la transition OK→critique où un warning est loggé."""
        if maintenant is None:
            maintenant = time.time()
        if maintenant - self._dernier_check_ts < self.intervalle_s:
            return
        self._dernier_check_ts = maintenant
        try:
            with open(self.path) as f:
                millideg = int(f.read().strip())
            self.temp_c = millideg / 1000.0
            etait_critique = self.critique
            self.critique = self.temp_c >= self.seuil_c
            if self.critique and not etait_critique:
                log_warning(
                    f"Température CPU critique : {self.temp_c:.1f} °C "
                    f"(seuil : {self.seuil_c:.0f} °C)"
                )
        except FileNotFoundError:
            # Pas un Pi / Linux standard → monitor inerte silencieusement
            self.temp_c = None
        except (OSError, ValueError) as e:
            log_warning(f"Check température échoué : {e}")


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
