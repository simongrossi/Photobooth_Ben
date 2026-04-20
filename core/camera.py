"""camera.py — gestion de la caméra Canon via gphoto2.

Encapsule la caméra avec `threading.Lock` (thread-safe pour le capture en spinner
thread), rate-limit de reconnexion USB, et API explicite (init, set_liveview,
get_preview_frame, capture_hq, is_connected).

Sprint 4.1 + 4.6 : extrait de Photobooth_start.py. Dépendances : pygame.surfarray
(pour convertir le frame gphoto2 en Surface), cv2 (décodage JPEG), numpy (buffer),
gphoto2 (pilote caméra).
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Optional

import cv2
import gphoto2 as gp
import numpy as np
import pygame

from core.logger import log_info, log_warning, log_critical


class CameraManager:
    """Encapsule la caméra Canon/gphoto2 avec reconnexion rate-limitée et thread-safety."""

    _DELAI_RECONNEXION: float = 2.0  # secondes min entre deux tentatives d'init en cas d'échec

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._cam: Optional[gp.Camera] = None
        self._last_init_attempt: float = 0.0

    # ---- API publique ----
    @property
    def is_connected(self) -> bool:
        return self._cam is not None

    @property
    def raw_camera(self) -> Optional[gp.Camera]:
        """Accès bas niveau à l'objet gphoto2.Camera (pour compat avec code legacy)."""
        return self._cam

    def init(self) -> bool:
        """Tente d'initialiser la caméra. Retourne True/False."""
        with self._lock:
            return self._init_unlocked()

    def set_liveview(self, state: int) -> None:
        """Active (1) ou désactive (0) le LiveView sur la caméra courante."""
        with self._lock:
            self._set_liveview_unlocked(state)

    def get_preview_frame(self) -> Optional[pygame.Surface]:
        """Retourne une pygame.Surface du preview courant, ou None.
        Applique rate-limit sur les tentatives de reconnexion (évite de marteler gphoto2)."""
        with self._lock:
            # Si pas de caméra : tentative de reconnexion discrète (rate-limitée)
            if self._cam is None:
                maintenant = time.time()
                if maintenant - self._last_init_attempt < self._DELAI_RECONNEXION:
                    return None
                self._last_init_attempt = maintenant
                self._init_unlocked()
                if self._cam:
                    self._set_liveview_unlocked(1)
                return None

            try:
                capture = self._cam.capture_preview()
                file_bits = capture.get_data_and_size()
                image_data = np.frombuffer(memoryview(file_bits), dtype=np.uint8)
                frame = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
                if frame is not None:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = cv2.flip(frame, 1)
                    frame = np.rot90(frame)
                    return pygame.surfarray.make_surface(frame)
            except gp.GPhoto2Error:
                # perte gphoto2 → on force la reconnexion au prochain appel
                self._cam = None
            except Exception:
                pass
            return None

    def capture_hq(self, chemin_complet: str) -> bool:
        """Capture HQ via subprocess gphoto2 avec retry 3× + backoff.
        Ferme la session LiveView avant, la relance après. Retourne True si fichier présent."""
        with self._lock:
            # Fermeture LiveView
            if self._cam:
                try:
                    log_info("Fermeture LiveView pour capture...")
                    self._set_liveview_unlocked(0)
                    time.sleep(0.5)
                    self._cam.exit()
                    print("Session gphoto2 fermée proprement.")
                except Exception as e:
                    log_warning(f"Fermeture caméra : {e}")
                self._cam = None
            else:
                log_warning("Camera non initialisée (None), tentative de capture directe...")

            # Capture avec retry
            log_info(f"📸 Capture HQ en cours : {os.path.basename(chemin_complet)}")
            capture_ok = False
            for tentative in range(3):
                try:
                    subprocess.run([
                        "gphoto2",
                        "--capture-image-and-download",
                        "--filename", chemin_complet,
                        "--force-overwrite",
                    ], check=True, timeout=15)
                    capture_ok = True
                    break
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    log_warning(f"Tentative capture {tentative+1}/3 échouée : {e}")
                    if tentative < 2:
                        time.sleep(0.5 * (2 ** tentative))
            if not capture_ok:
                log_critical("Capture HQ abandonnée après 3 tentatives")

            # Relance LiveView
            log_info("Relancement du LiveView...")
            self._init_unlocked()
            if self._cam:
                try:
                    self._set_liveview_unlocked(1)
                except Exception as e:
                    log_warning(f"Impossible de relancer le LiveView : {e}")

            return capture_ok and os.path.exists(chemin_complet)

    # ---- Privés (supposent lock tenu) ----
    def _init_unlocked(self) -> bool:
        # Nettoyage des processus système qui bloquent souvent l'USB sur Linux
        subprocess.run(["pkill", "-f", "gvfs-gphoto2-volume-monitor"], capture_output=True)
        subprocess.run(["pkill", "-f", "gphoto2"], capture_output=True)
        try:
            cam = gp.Camera()
            cam.init()
            self._cam = cam
            log_info("📸 Canon initialisée avec succès !")
            return True
        except Exception:
            # On ne log pas en boucle pour ne pas saturer le log texte
            self._cam = None
            return False

    def _set_liveview_unlocked(self, state: int) -> None:
        if not self._cam:
            return
        try:
            cfg = self._cam.get_config()
            vf = cfg.get_child_by_name("viewfinder")
            vf.set_value(state)
            self._cam.set_config(cfg)
        except Exception as e:
            log_warning(f"Impossible de régler le LiveView : {e}")
