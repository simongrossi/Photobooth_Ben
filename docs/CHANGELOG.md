# Changelog — Photobooth Ben

Historique des commits par sprint, du plus récent au plus ancien.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr).

---

## `WIP` — Interface admin web optionnelle (v1)

### Added
- Module `web/` autonome : app Flask + Jinja2 + HTMX, service systemd séparé
  (`deploy/photobooth-admin.service`, port 8080, Basic Auth via
  `PHOTOBOOTH_ADMIN_PASS`). Communication avec le kiosque **uniquement** par
  filesystem — zéro import de `Photobooth_start` ou `ui/*`.
- 4 blueprints :
  - `/dashboard/` — sessions (réemploie `stats.calculer_stats`), disque + temp
    (réemploie `core/monitoring.DiskMonitor/TempMonitor`), histogramme horaire
  - `/galerie/` — parcours `data/print/` (10×15 + strips), miniatures PIL à la
    volée, pagination, protection path-traversal
  - `/templates/` — upload PNG → `assets/overlays/`, activation exclusive par
    mode (copie vers `OVERLAY_10X15`/`OVERLAY_STRIPS`), suppression guardée
  - `/settings/` — éditeur de `data/config_overrides.json` (whitelist stricte)
- `config.py::_appliquer_overrides()` + `_CONFIG_OVERRIDES_WHITELIST` : 18 clés
  surchargeables sans éditer le code (timings, imprimantes, slideshow,
  watermark, grain, Arduino, seuils disque/temp). Les résolutions et géométrie
  de montage restent figées. Typage strict (bool ≠ int).
- `web/db.py` : SQLite stdlib (`data/admin.db`) pour métadonnées de templates
  (id, nom, type, fichier, actif, uploaded_at). Source de vérité des fichiers
  reste `assets/overlays/`.
- `deploy/install-admin.sh` : installeur idempotent (apt/pip Flask, génère un
  mot de passe aléatoire dans `/etc/photobooth-admin.env` chmod 640, crée le
  service systemd). Indépendant de `deploy/install.sh`.
- `docs/ADMIN.md` : architecture, installation, variables d'env, liste des
  réglages whitelistés, sécurité.
- Tests : `test_web_app.py`, `test_web_gallery.py`, `test_web_templates.py`,
  `test_web_settings.py`, `test_config_overrides.py` — 32 tests couvrant auth,
  routing, upload/validation, activation exclusive, path-traversal, fusion
  d'overrides (whitelist, typage strict, JSON corrompu).

### Changed
- `.github/workflows/ci.yml` : ajoute `flask` aux deps CI (pas de `pygame` /
  `gphoto2` / `cv2` / `pyserial` toujours).
- `pyproject.toml` : `[tool.coverage.run] source` inclut `web/`.
- `CLAUDE.md`, `docs/ARCHITECTURE.md` : graphe de dépendances mis à jour pour
  refléter l'isolation de `web/*`.
- `docs/CONFIG.md` : mention des overrides et de leur whitelist.

### Stats
- Tests : 147 → **179** (+32)
- Coverage : `web/*` entre 77 % et 100 %, global 90,74 % (seuil 75 %)
- Zéro régression sur la suite existante (`ruff check .` propre)

### Sécurité
- Fail closed : sans `PHOTOBOOTH_ADMIN_PASS`, toutes les routes répondent 503.
- `hmac.compare_digest` pour la comparaison mdp.
- Upload PNG uniquement + `Image.verify()` pour rejeter les fichiers malformés.
- Path-traversal bloqué via `os.path.realpath` avec garde de racine.

---

## `WIP` — Perf court terme : décompte + spinner + profiling Pi

### Added
- `Photobooth_start.py::_get_masque_decompte(bande_w, alpha)` + cache module
  `_masque_decompte_cache` : la bande noire latérale du DECOMPTE (mode strips)
  est allouée une seule fois par (largeur, alpha) au lieu d'une `pygame.Surface`
  par frame
- `config.py::SPINNER_FPS=30` : framerate dédié au rafraîchissement du spinner
  (`executer_avec_spinner`, `ecran_attente_impression`), distinct de `FPS`
- `bench_spinner.py` : microbench autonome du `LoaderAnimation` (FPS moyen,
  ms/frame p50/p95/p99), override `--points` pour comparer avant/après optim,
  fallback SDL dummy si pas de display
- `docs/PROFILING.md` : protocole de profiling sur Pi (cProfile, tracemalloc,
  microbench spinner, checklist post-optim, baselines attendues)

### Changed
- `ui/helpers.py::LoaderAnimation` pré-rend `ANIM_NB_POINTS` sprites au boot
  (couleur + alpha figés par index) : la boucle de rendu ne fait plus qu'un
  `blit` par point au lieu de `fill` + `draw.circle` + `blit` → allocations
  par frame divisées par `ANIM_NB_POINTS`
- `config.py::ANIM_NB_POINTS` : 300 → **120** par défaut (suffisant visuellement,
  ~2,5× moins de blits/frame)
- `docs/CONFIG.md` : nouvelles entrées `ANIM_NB_POINTS` et `SPINNER_FPS` dans
  le tableau animation
- `docs/DEVELOPMENT.md` : pointeur vers `docs/PROFILING.md` + `bench_spinner.py`
  dans l'arbo

---

## `WIP` — Priorités stabilité exploitation

### Added
- `Photobooth_start.py::main()` : le module est importable sans lancer pygame,
  caméra ni Arduino ; le runtime n'est initialisé qu'en exécution directe
- Arrêt propre via Échap, SIGTERM et SIGINT, avec fermeture caméra/Arduino/Pygame
  dans un `finally`
- `core/camera.py::CameraManager.close()` pour libérer explicitement la session Canon
- Tests `test_camera.py` : 9 tests CameraManager avec mocks gphoto2/cv2/numpy/pygame
- Tests d'intégration : import `Photobooth_start.py` sans runtime + caméra sans dépendances

### Changed
- `ACTIVER_IMPRESSION=False` devient un vrai mode sans papier : montage archivé
  dans `data/print/`, aucun job CUPS envoyé, metadata `issue=print_disabled`
- Échec CUPS/imprimante : metadata `issue=print_failed` au lieu de `printed`
- `stats.py` affiche et exporte `print_failed` / `print_disabled`
- `core/camera.py` tolère l'absence de `gphoto2`, `cv2`, `numpy` ou `pygame`

### Stats
- Tests : 136 → **147** (+11)
- Coverage : 79,9 % → **92,8 %** ; `core/camera.py` : 0 % → **90 %**

---

## `WIP` — Grain de pellicule sur montages finaux

### Added
- `core/montage.py::MontageBase._appliquer_grain()` : bruit gaussien superposé
  via `Image.effect_noise` + `Image.blend`, niveaux de gris projetés sur les
  3 canaux (pas de dérive de teinte)
- `config.py` : `GRAIN_ENABLED=False`, `GRAIN_INTENSITE=8` (% mélange),
  `GRAIN_SIGMA=30.0`, avec validation assert au chargement
- Tests : 5 nouveaux tests `TestGrain` (disabled no-op, enabled altère canvas,
  intensité 0 ≡ disabled, strip accepte grain, preview jamais altérée)
- `docs/CONFIG.md` : section « Grain de pellicule » à côté du watermark

### Changed
- `MontageGenerator10x15.final()` et `MontageGeneratorStrip.final()` appellent
  `_appliquer_grain()` après le watermark (le grain couvre aussi le texte)

### Pourquoi
- Effet argentique discret demandé dans [IDEAS.md](IDEAS.md#effets-image--expérimentaux),
  activable selon l'ambiance de l'événement (mariage rétro, etc.)
- Isolé au rendu final : pas d'impact CPU sur les previews pendant la session,
  pas de régression visible quand désactivé

### Stats
- Tests : 131 → **136** (+5)
- Coverage : 80.6 % → **80.9 %** ; `core/montage.py` : 88 % → **93 %**

---

## `WIP` — Watchdog systemd + mode kiosque

### Added
- `deploy/photobooth.service` : unit systemd templatisé (`@USER@`, `@HOME@`)
  avec watchdog (`Restart=on-failure`, `StartLimitBurst=5/60s`, `MemoryMax=1G`,
  `TimeoutStopSec=30`)
- `deploy/kiosk.sh` : wrapper de démarrage (xset off, unclutter, export
  `PHOTOBOOTH_KIOSK=1`, venv, exec python)
- `deploy/install.sh` : installeur idempotent (apt install unclutter, sed
  substitution placeholders, systemctl enable)
- `deploy/uninstall.sh` : retrait propre du service
- `deploy/README.md` : guide complet d'installation + dépannage

### Changed
- `Photobooth_start.py` : `pygame.display.set_mode()` prend `FULLSCREEN | NOFRAME`
  si `config.KIOSK_FULLSCREEN=True`, curseur caché en kiosque
- `config.py` : `KIOSK_FULLSCREEN = os.environ.get("PHOTOBOOTH_KIOSK") == "1"`
  — auto-activation depuis l'env posé par `kiosk.sh`
- `docs/DEPLOYMENT.md` : sections 8 (systemd) et 9 (kiosque) remplacées par
  des pointeurs vers `deploy/`, plus de heredoc inline
- `docs/RUNBOOK.md` : commande de rearm watchdog (`systemctl reset-failed`)

### Pourquoi
- Fichiers d'infra versionnés (testables, reviewables) plutôt que heredocs
  enfouis dans la doc
- Watchdog complet avec limite anti-boucle + memory cap + stop gracieux
- Mode kiosque activable via env sans modification de config.py (dev/prod
  même base)

---

## `e60ec6c` — Monitoring température CPU (Raspberry Pi)

### Added
- `core/monitoring.py::TempMonitor` — même pattern que DiskMonitor,
  lit `/sys/class/thermal/thermal_zone0/temp`, inerte silencieux hors Pi
- `config.py` : `SEUIL_TEMP_CRITIQUE_C=75.0`, `INTERVALLE_CHECK_TEMP_S=30.0`,
  `TEMP_PATH`
- `status.py::check_temperature()` — diagnostic pré-événement non-bloquant
- `Photobooth_start.py` : bandeau orange en ACCUEIL si CPU ≥ 75 °C
- Tests : 7 nouveaux tests TempMonitor + 3 tests check_temperature

### Stats
- Tests : 121 → **131** (+10)
- Coverage : 80.1 % → **80.6 %**

---

## `fb704ab` — Split Photobooth_start.py : core/session + core/monitoring

### Added
- `core/session.py` : `Etat` enum, `SessionState` dataclass, `ecrire_metadata_session()`,
  `terminer_session_et_revenir_accueil()` — module pur, testable isolément
- `core/monitoring.py` : `DiskMonitor` (classe rate-limitée, remplace 3 globals
  module-level), `lister_images_slideshow(dossiers, nb_max)` (pure)
- `test_session.py` (11 tests) + `test_monitoring.py` (14 tests)

### Changed
- `Photobooth_start.py` : imports depuis `core.session` et `core.monitoring`,
  suppression de 190 lignes déplacées. 1183 → 1071 L.
- `docs/ARCHITECTURE.md` : modules session + monitoring ajoutés au graphe
- `docs/DEVELOPMENT.md` : arborescence mise à jour
- `docs/TESTING.md` : nouveaux tests inventoriés, couverture actualisée

### Stats
- Coverage : 78 % → **80 %** (seuil via `core/session` 100 % et `core/monitoring` 95 %)
- Tests totaux : 96 → **121** (+25)

---

## `19973c3` (PR #1) — Boîtier Arduino : 3 boutons-poussoirs à LED intégrée

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
