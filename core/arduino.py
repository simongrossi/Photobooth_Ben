"""arduino.py — contrôleur Arduino Nano (3 boutons + 3 LEDs intégrées).

Pilote série bidirectionnel :
- **Lecture** : un thread daemon lit le port série et injecte des événements
  `pygame.KEYDOWN` avec les mêmes `TOUCHE_GAUCHE/MILIEU/DROITE` que le clavier.
  Le code existant (handle_accueil_event, handle_validation_event, handle_fin_event)
  ne voit aucune différence.
- **Écriture** : méthodes `set_led()` / `tick()` envoient des commandes à l'Arduino
  pour piloter l'état des LEDs selon la machine d'état (`Etat`).

Conçu pour dégrader proprement :
- Si `pyserial` n'est pas installé → `available = False`, tout devient no-op.
- Si le port n'est pas ouvert → idem, le photobooth reste 100 % utilisable au clavier.
- Le thread de lecture capture toutes les exceptions et log un warning.

Protocole série (115200 bauds, 8N1) — voir docs/ARDUINO.md pour le détail.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

try:
    import serial  # pyserial
except ImportError:
    serial = None  # type: ignore[assignment]

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from core.logger import log_info, log_warning


# Positions physiques des 3 boutons. Mêmes noms que les TOUCHE_* de config.py
# pour éviter l'ambiguïté. La LED intégrée de chaque bouton a sa propre couleur
# (voir docs/ARDUINO.md).
POS_GAUCHE = "L"
POS_MILIEU = "M"
POS_DROITE = "R"

# États LED supportés par le firmware Arduino.
LED_OFF = "OFF"
LED_ON = "ON"
LED_PULSE = "PULSE"      # respiration lente (invitation à presser)
LED_PULSE_FAST = "FAST"  # clignotement rapide (alerte / confirmation)


class ArduinoController:
    """Gère le port série vers l'Arduino Nano : lecture des boutons, pilotage des LEDs.

    Usage typique :
        ctrl = ArduinoController(port="/dev/ttyUSB0", key_left=K_g, key_mid=K_m, key_right=K_d)
        ctrl.start()
        ...  # dans la boucle principale
        ctrl.tick(session.etat, session.mode_actuel, abandon_armed=...)
        ...  # à la sortie
        ctrl.close()

    Si `port` est None ou si pyserial n'est pas installé, l'instance est inerte
    (toutes les méthodes sont no-op). Le photobooth reste utilisable au clavier.
    """

    def __init__(
        self,
        port: Optional[str],
        baudrate: int = 115200,
        key_left: int = 0,
        key_mid: int = 0,
        key_right: int = 0,
        connect_timeout_s: float = 2.5,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self._key_map = {POS_GAUCHE: key_left, POS_MILIEU: key_mid, POS_DROITE: key_right}
        self._connect_timeout_s = connect_timeout_s

        self._ser: Optional["serial.Serial"] = None
        self._reader: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._write_lock = threading.Lock()

        # Mémorise le dernier état LED envoyé par position pour n'écrire sur
        # le port que lors des transitions (évite de spammer le lien série à 30 FPS).
        self._last_led_state: dict[str, str] = {}
        # Signature du dernier `tick()` pour même raison côté état global.
        self._last_tick_sig: Optional[tuple] = None

        self.available = False  # passe à True après connect() réussi

    # ------------------------------------------------------------------ setup

    def start(self) -> None:
        """Ouvre le port série et lance le thread de lecture. Silencieux si échec."""
        if serial is None:
            log_warning("Arduino : pyserial non installé — contrôleur désactivé.")
            return
        if not self.port:
            log_info("Arduino : port non configuré — contrôleur désactivé.")
            return

        try:
            self._ser = serial.Serial(
                self.port, self.baudrate, timeout=0.1,
            )
        except Exception as exc:
            log_warning(f"Arduino : ouverture {self.port} échouée ({exc}) — fallback clavier.")
            self._ser = None
            return

        # Laisse l'Arduino finir son reset post-ouverture (DTR toggle → bootloader).
        # Sans ce délai, les premiers octets sont perdus.
        time.sleep(self._connect_timeout_s)
        try:
            self._ser.reset_input_buffer()
        except Exception:
            pass

        self.available = True
        self._stop.clear()
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name="arduino-reader")
        self._reader.start()
        log_info(f"🎛  Arduino connecté sur {self.port} @ {self.baudrate} bauds.")

        # LEDs éteintes au démarrage, l'état sera posé par le premier tick().
        self.all_leds_off()

    def close(self) -> None:
        """Arrête le thread de lecture et ferme le port série."""
        self._stop.set()
        if self._reader and self._reader.is_alive():
            self._reader.join(timeout=0.5)
        if self._ser:
            try:
                self.all_leds_off()
            except Exception:
                pass
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        self.available = False

    # --------------------------------------------------------------- lecture

    def _read_loop(self) -> None:
        """Thread daemon : lit ligne par ligne, injecte les événements pygame."""
        assert self._ser is not None
        buf = bytearray()
        while not self._stop.is_set():
            try:
                chunk = self._ser.read(64)
            except Exception as exc:
                log_warning(f"Arduino : erreur lecture série ({exc}) — arrêt du reader.")
                self.available = False
                return
            if not chunk:
                continue
            buf.extend(chunk)
            while b"\n" in buf:
                raw_line, _, rest = buf.partition(b"\n")
                buf = bytearray(rest)
                line = raw_line.decode("ascii", errors="ignore").strip()
                if line:
                    self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        """Route un message reçu : press bouton → event pygame, READY/log → trace."""
        if line in (POS_GAUCHE, POS_MILIEU, POS_DROITE):
            self._inject_key(line)
        elif line == "READY":
            log_info("Arduino : firmware prêt (READY reçu).")
        elif line.startswith("LOG:"):
            # Canal debug optionnel côté firmware (désactivé par défaut).
            log_info(f"Arduino/{line}")
        # autres lignes ignorées silencieusement

    def _inject_key(self, pos: str) -> None:
        """Pousse un pygame.KEYDOWN avec la touche clavier correspondante."""
        if pygame is None:
            return
        key = self._key_map.get(pos, 0)
        if not key:
            return
        try:
            evt = pygame.event.Event(pygame.KEYDOWN, {"key": key, "mod": 0, "unicode": "", "scancode": 0})
            pygame.event.post(evt)
        except Exception as exc:
            # Si pygame.event n'est pas encore initialisé ou si la file est pleine,
            # on log mais on ne crashe pas.
            log_warning(f"Arduino : injection touche échouée ({exc}).")

    # -------------------------------------------------------------- écriture

    def _send(self, cmd: str) -> None:
        if not self.available or self._ser is None:
            return
        try:
            with self._write_lock:
                self._ser.write((cmd + "\n").encode("ascii"))
        except Exception as exc:
            log_warning(f"Arduino : écriture échouée ({exc}).")
            self.available = False

    def set_led(self, pos: str, state: str) -> None:
        """Pilote la LED d'un bouton. Ne fait rien si l'état est inchangé.

        Args:
            pos: POS_GAUCHE / POS_MILIEU / POS_DROITE
            state: LED_OFF / LED_ON / LED_PULSE / LED_PULSE_FAST
        """
        if self._last_led_state.get(pos) == state:
            return
        self._last_led_state[pos] = state
        self._send(f"LED:{pos}:{state}")

    def all_leds_off(self) -> None:
        """Éteint les 3 LEDs d'un coup (raccourci pour les transitions)."""
        self._last_led_state = {POS_GAUCHE: LED_OFF, POS_MILIEU: LED_OFF, POS_DROITE: LED_OFF}
        self._send("LED:ALL:OFF")

    # --------------------------------------------------------------- tick UI

    def tick(self, etat_name: str, mode_actuel: Optional[str], abandon_armed: bool = False) -> None:
        """Met à jour les LEDs selon l'état courant de la session.

        Appelée une fois par frame dans la boucle principale. Les messages ne sont
        émis que lors des transitions, donc le coût est quasi nul en régime établi.

        Args:
            etat_name: Etat.ACCUEIL.value / DECOMPTE / VALIDATION / FIN
            mode_actuel: "10x15" / "strips" / None
            abandon_armed: True si la fenêtre de confirmation d'abandon (FIN) est active
        """
        sig = (etat_name, mode_actuel, abandon_armed)
        if sig == self._last_tick_sig:
            return
        self._last_tick_sig = sig

        if etat_name == "ACCUEIL":
            if mode_actuel is None:
                # Aucun mode choisi : on invite avec les 2 côtés (= les 2 modes).
                # Le milieu reste éteint car appuyer ne ferait rien.
                self.set_led(POS_GAUCHE, LED_PULSE)
                self.set_led(POS_MILIEU, LED_OFF)
                self.set_led(POS_DROITE, LED_PULSE)
            else:
                # Mode choisi : le vert central invite au démarrage.
                self.set_led(POS_GAUCHE, LED_ON)
                self.set_led(POS_MILIEU, LED_PULSE)
                self.set_led(POS_DROITE, LED_ON)
        elif etat_name == "DECOMPTE":
            # État non-interactif : on éteint pour ne pas inciter à presser.
            self.set_led(POS_GAUCHE, LED_OFF)
            self.set_led(POS_MILIEU, LED_OFF)
            self.set_led(POS_DROITE, LED_OFF)
        elif etat_name == "VALIDATION":
            # Les 3 boutons sont actifs → on les allume, le vert pulse (action principale).
            self.set_led(POS_GAUCHE, LED_ON)
            self.set_led(POS_MILIEU, LED_PULSE)
            self.set_led(POS_DROITE, LED_ON)
        elif etat_name == "FIN":
            if abandon_armed:
                # Fenêtre de confirmation : seul le rouge clignote vite pour réclamer le 2e appui.
                self.set_led(POS_GAUCHE, LED_OFF)
                self.set_led(POS_MILIEU, LED_OFF)
                self.set_led(POS_DROITE, LED_PULSE_FAST)
            else:
                self.set_led(POS_GAUCHE, LED_ON)
                self.set_led(POS_MILIEU, LED_PULSE)
                self.set_led(POS_DROITE, LED_ON)
