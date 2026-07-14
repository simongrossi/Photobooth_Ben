"""camera.py — gestion de la caméra Canon via gphoto2.

Encapsule la caméra avec `threading.Lock`, acquisition LiveView en arrière-plan,
rate-limit de reconnexion USB, et API explicite (init, start_preview,
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
from typing import Any, Optional

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

try:
    import gphoto2 as gp
except ImportError:
    gp = None  # type: ignore[assignment]

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from core.logger import log_info, log_warning, log_critical


_GPHOTO2_ERROR = gp.GPhoto2Error if gp is not None else Exception


class CameraManager:
    """Encapsule la caméra Canon/gphoto2 avec reconnexion rate-limitée et thread-safety."""

    _DELAI_RECONNEXION: float = 2.0  # secondes min entre deux tentatives d'init en cas d'échec

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._preview_lock: threading.Lock = threading.Lock()
        self._cam: Optional[Any] = None
        self._last_init_attempt: float = 0.0
        self._deps_warning_logged: bool = False
        self._latest_preview: Optional[Any] = None
        self._latest_preview_generation: int = 0
        self._surface_preview: Optional[Any] = None
        self._surface_preview_generation: int = -1
        self._preview_stop = threading.Event()
        self._preview_thread: Optional[threading.Thread] = None

    # ---- API publique ----
    @property
    def is_connected(self) -> bool:
        return self._cam is not None

    @property
    def raw_camera(self) -> Optional[Any]:
        """Accès bas niveau à l'objet gphoto2.Camera (pour compat avec code legacy)."""
        return self._cam

    @property
    def preview_generation(self) -> int:
        """Identifiant croissant de la dernière image réellement reçue."""
        with self._preview_lock:
            return self._latest_preview_generation

    def init(self) -> bool:
        """Tente d'initialiser la caméra. Retourne True/False."""
        with self._lock:
            return self._init_unlocked()

    def set_liveview(self, state: int) -> None:
        """Active (1) ou désactive (0) le LiveView sur la caméra courante."""
        with self._lock:
            self._set_liveview_unlocked(state)

    def start_preview(self) -> None:
        """Démarre l'acquisition LiveView hors du thread Pygame.

        Le worker ne crée aucune Surface : il conserve uniquement le tableau RGB
        le plus récent. La conversion Pygame reste effectuée par le thread principal
        dans :meth:`get_preview_frame`.
        """
        if cv2 is None or np is None:
            self._log_deps_absentes()
            return
        if self._preview_thread is not None and self._preview_thread.is_alive():
            return
        self._preview_stop.clear()
        self._preview_thread = threading.Thread(
            target=self._preview_loop,
            name="camera-liveview",
            daemon=True,
        )
        self._preview_thread.start()

    def get_preview_frame(self) -> Optional[Any]:
        """Retourne immédiatement la dernière Surface disponible, ou None.

        L'appel ne contacte jamais la caméra : l'I/O gphoto2 potentiellement lente
        reste dans le worker LiveView afin de ne pas figer le décompte Pygame.
        """
        return self.get_preview_frame_info()[0]

    def get_preview_frame_info(self) -> tuple[Optional[Any], int]:
        """Retourne la Surface et la génération auxquelles elle correspond."""
        if cv2 is None or np is None or pygame is None:
            self._log_deps_absentes()
            return None, self.preview_generation
        self.start_preview()
        with self._preview_lock:
            frame = self._latest_preview
            generation = self._latest_preview_generation
            if generation == self._surface_preview_generation:
                return self._surface_preview, generation
        if frame is None:
            return None, generation
        try:
            surface = pygame.surfarray.make_surface(frame)
        except Exception:
            return None, generation
        with self._preview_lock:
            self._surface_preview = surface
            self._surface_preview_generation = generation
        return surface, generation

    def capture_hq(self, chemin_complet: str) -> bool:
        """Capture HQ via subprocess gphoto2 avec retry 3× + backoff.
        Ferme la session LiveView avant, la relance après. Retourne True si fichier présent."""
        self._stop_preview()
        self._clear_preview()
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

            resultat = capture_ok and os.path.exists(chemin_complet)

        return resultat

    def close(self) -> None:
        """Ferme proprement la session caméra si elle est ouverte."""
        self._stop_preview()
        with self._lock:
            if not self._cam:
                return
            try:
                self._set_liveview_unlocked(0)
                self._cam.exit()
                log_info("Session caméra fermée proprement.")
            except Exception as e:
                log_warning(f"Fermeture caméra : {e}")
            finally:
                self._cam = None

    def stop_preview(self, clear: bool = False) -> None:
        """Arrête l'acquisition LiveView sans fermer la session caméra."""
        self._stop_preview()
        if clear:
            self._clear_preview()

    def _stop_preview(self) -> bool:
        """Demande l'arrêt du worker et retourne s'il était actif."""
        thread = self._preview_thread
        etait_actif = thread is not None and thread.is_alive()
        self._preview_stop.set()
        if etait_actif:
            thread.join(timeout=2.0)
        if thread is None or not thread.is_alive():
            self._preview_thread = None
        return etait_actif

    def _clear_preview(self) -> None:
        with self._preview_lock:
            self._latest_preview = None
            self._surface_preview = None
            self._surface_preview_generation = -1

    def _preview_loop(self) -> None:
        """Acquiert et décode les JPEG LiveView sans bloquer l'interface."""
        while not self._preview_stop.is_set():
            frame = None
            with self._lock:
                if self._cam is None:
                    maintenant = time.time()
                    if maintenant - self._last_init_attempt >= self._DELAI_RECONNEXION:
                        self._last_init_attempt = maintenant
                        if self._init_unlocked():
                            self._set_liveview_unlocked(1)
                if self._cam is not None:
                    try:
                        capture = self._cam.capture_preview()
                        file_bits = capture.get_data_and_size()
                        image_data = np.frombuffer(memoryview(file_bits), dtype=np.uint8)
                        frame = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
                        if frame is not None:
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            frame = cv2.flip(frame, 1)
                            # pygame.surfarray attend l'axe largeur en premier.
                            # La transposition conserve le miroir historique sans
                            # imposer un second flip plein écran dans Pygame.
                            frame = np.transpose(frame, (1, 0, 2))
                    except _GPHOTO2_ERROR:
                        self._cam = None
                    except Exception:
                        frame = None
            if frame is not None:
                with self._preview_lock:
                    self._latest_preview = frame
                    self._latest_preview_generation += 1
            else:
                self._preview_stop.wait(0.05)

    # ---- Privés (supposent lock tenu) ----
    def _init_unlocked(self) -> bool:
        if gp is None:
            self._log_deps_absentes()
            self._cam = None
            return False

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

    def _log_deps_absentes(self) -> None:
        """Loggue une seule fois les dépendances optionnelles caméra manquantes."""
        if self._deps_warning_logged:
            return
        manquantes = []
        if gp is None:
            manquantes.append("gphoto2")
        if cv2 is None:
            manquantes.append("cv2")
        if np is None:
            manquantes.append("numpy")
        if pygame is None:
            manquantes.append("pygame")
        if manquantes:
            log_warning(
                "CameraManager désactivé : dépendance(s) optionnelle(s) absente(s) "
                f"({', '.join(manquantes)})"
            )
        self._deps_warning_logged = True
