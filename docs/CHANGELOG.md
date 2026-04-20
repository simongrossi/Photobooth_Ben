# Changelog — Photobooth Ben

Historique des commits par sprint, du plus récent au plus ancien.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr).

---

## `WIP` — Boîtier Arduino : 3 boutons-poussoirs à LED intégrée

### Added
- `core/arduino.py` : `ArduinoController` (thread pyserial → `pygame.KEYDOWN`,
  pilotage LED selon `Etat` via `tick()`)
- `arduino/photobooth_buttons/photobooth_buttons.ino` : firmware Nano
  (3 boutons `INPUT_PULLUP` + 3 LEDs PWM, protocole L/M/R ↔ LED:*:STATE)
- `docs/ARDUINO.md` : câblage, flash, protocole, dépannage, checklist Pi
- `config.py` : clefs `ARDUINO_ENABLED`, `ARDUINO_PORT`, `ARDUINO_BAUDRATE`

### Changed
- `Photobooth_start.py` : init du contrôleur après pygame, `arduino_ctrl.tick(...)`
  dans la boucle principale, `close()` à la sortie
- `docs/ARCHITECTURE.md` : mention du nouveau module dans le graphe de dépendances
- `docs/DEPLOYMENT.md` : ajout de `python3-serial` + renvoi vers `ARDUINO.md`

### Dépendance (optionnelle)
- `pyserial` — absent = fallback silencieux sur clavier uniquement

---

## `5d04934` — Quick wins code quality (6 items)

**Code quality** sans changement fonctionnel.

### Added
- Type hints sur classes publiques (`CameraManager`, `PrinterManager`,
  `MontageGenerator*`, helpers du `logger`)
- `from __future__ import annotations` pour support typing sur Python 3.9

### Changed
- `from config import *` → liste explicite de 96 noms (dépendances visibles)
- 15 `log_error()` migrés vers `log_info` / `log_warning` / `log_critical` nommés
- Semicolons one-liner → lignes séparées (ruff E702)
- `except Exception as e: log(...)` → bloc sur 2 lignes (ruff E701)
- Variables `l` ambigües → `ligne` dans status.py (ruff E741)
- Docstrings uniformisées (1re ligne courte, présent) + ajouts manquants

### Removed
- Dead code : `_CameraProxy`, wrappers `init_camera/set_liveview`,
  `generer_preview_10x15` & cie (call sites migrés vers classes),
  `imprimante_prete`, `imprimer_fichier_auto` (appels remplacés par `printer_mgr.send`)
- Imports inutilisés dans main : cv2, numpy, gphoto2, subprocess

### Stats
- 7 fichiers touchés, -138 / +118 lignes
- `ruff check .` : 0 warning
- Tests : 18/18 passent

---

## `1609da0` — Item 8 : split en dossiers `core/` + `ui/`

### Added
- Package `core/` : logger, camera, montage, printer
- Package `ui/` avec `helpers.py` et `__init__.py` qui re-exporte
- `core/__init__.py` + `ui/__init__.py` documentant leur rôle

### Changed
- Imports dans main : `from core.X import ...` et `from ui import ...`
- Cross-module : `core.camera` et `core.printer` importent `from core.logger`

### Renamed (git mv — historique préservé)
- `camera.py` → `core/camera.py`
- `logger.py` → `core/logger.py`
- `montage.py` → `core/montage.py`
- `printer.py` → `core/printer.py`
- `ui.py` → `ui/helpers.py`

---

## `9524d6d` — Items 9+11 (partiel) : extraction render functions

### Added
- `render_decompte(session)` : preview caméra + capture + transition
- `render_validation(session)` : aperçu + bandeau + burst countdown. Retourne `True` si auto-advance.
- `render_fin(session)` : aperçu final + overlay confirmation abandon

### Changed
- Main loop dispatch simplifié : chaque état (sauf ACCUEIL) est 1-3 lignes
- Main file : -231 / +228 lignes

### Non extrait
- `render_accueil` (complexité slideshow + `continue` interne)
- Event handlers par état (nombreux `continue` à refactor)

---

## `a9c8a20` — Item 7 : UIContext + ui.py

### Added
- `UIContext` singleton : `screen`, `clock`, fontes injectés au boot
- `ui.py` (348 lignes) : setup_sounds, jouer_son, draw_text_shadow_soft,
  inserer_background, obtenir_couleur_pulse, get_pygame_surf{_cropped},
  LoaderAnimation, afficher_message_plein_ecran, executer_avec_spinner,
  ecran_erreur, ecran_attente_impression, splash_connexion_camera
- `splash_connexion_camera(camera_mgr)` prend `camera_mgr` en paramètre (DI)

### Changed
- Main file : -230 lignes (1367 → 1137)
- `threading` retiré des imports du main (déplacé dans ui.py)

---

## `f00d3ad` — Item 10 : SessionState dataclass

### Added
- `@dataclass class SessionState` encapsulant 10 variables de session
  (etat, mode_actuel, photos_validees, id_session_timestamp, session_start_ts,
  path_montage, img_preview_cache, dernier_clic_time, abandon_confirm_until,
  last_activity_ts)
- Méthode `reset_pour_accueil()` centralisant le reset en fin de session

### Changed
- 133 références globales migrées vers `session.X`
- `terminer_session_et_revenir_accueil` appelle `session.reset_pour_accueil()`

### Removed
- Code mort : `selection`, `path_montage_hd` (jamais utilisés)
- Toutes les déclarations `global X` dispersées

---

## `247965f` — README.md + déplacement docs/ + mode burst strip

### Added
- `README.md` à la racine : démarrage rapide, architecture, observabilité, tests
- Mode burst strip : auto-validation photos 1 et 2 après `STRIP_BURST_DELAI_S`
  (désactivé par défaut `STRIP_MODE_BURST = False`)
- Countdown visible "Photo suivante dans Xs" en mode burst

### Moved
- `IDEAS.md` + `ROADMAP.md` → `docs/` (via `git mv`)

---

## `b400d7e` — Refactor modulaire + features événementiel (Sprints 1-6)

**Le gros bootstrap.** Voir commit message complet pour le détail.

### Sprints 1 — Stabilité
- Fuites PIL corrigées (`with Image.open`)
- Retry 3× + backoff sur capture gphoto2, rate-limit reconnexion USB
- Débounce `>=` au lieu de `>`
- `except` nus remplacés, `import sys` manquant ajouté

### Sprint 2 — UX événementiel
- Splash caméra boot avec retry visible
- Flash blanc 80 ms + son shutter, beep décompte, success impression
- Écran "Préparation impression..." avec spinner animé
- Écrans d'erreur visibles (capture, imprimante) avec timeout
- Vérification `lpstat` avant envoi CUPS
- Confirmation abandon double-press en état FIN
- Slideshow d'attente après 30 s idle
- Compteur "Photo N/3" renforcé en mode strip

### Sprint 3 — Performance
- Threading PIL avec spinner animé
- Cache `BANDEAU_CACHE` (surfaces statiques)
- Loader GC optim (buffer réutilisé au lieu de 300 surfaces/frame)
- Purge `PATH_TEMP` au startup + check disque continu

### Sprint 4 — Architecture (1re étape)
- `core/camera.py` : `CameraManager` avec `threading.Lock` + retry
- `core/montage.py` : `MontageGenerator10x15` / `MontageGeneratorStrip`
- `core/printer.py` : `PrinterManager` CUPS
- `core/logger.py` : `RotatingFileHandler` + helpers nommés
- `terminer_session_et_revenir_accueil` (consolidation 5 sites)
- `Etat` Enum remplace strings
- Validation config au chargement (18 assertions)

### Sprint 5 — Observabilité
- Logging rotatif 2 Mo × 5 = 10 Mo max
- `sessions.jsonl` metadata par session
- [status.py](../status.py) : diagnostic pré-événement autonome
- [stats.py](../stats.py) : rapport fin de soirée avec histogramme horaire
- Monitoring disque continu avec bandeau rouge écran < 500 Mo

### Sprint 6 — Features événementiel
- Slideshow idle ACCUEIL
- Compteur photo strip renforcé

### Tests
- [test_montage.py](../test_montage.py) : 18 tests pytest, isolation via monkeypatch

### Documentation
- [ROADMAP.md](ROADMAP.md) : items actionnables priorisés
- [IDEAS.md](IDEAS.md) : pool d'idées + références open-source
  (PIBOOTH, photobooth-app, RaspAP, nodogsplash)

---

## `be5eb16` — Initial commit

Code mono-fichier historique. ~1086 lignes dans `Photobooth_start.py`, fonctionnel
mais avec fuites mémoire, retry absent, duplications de code, config non validée.
Point de départ du refactor documenté dans les sprints suivants.
