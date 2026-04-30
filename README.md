# Photobooth Ben

Application photobooth événementiel en **Pygame + gphoto2 + PIL**, conçue pour un Raspberry Pi connecté à un Canon EOS et une imprimante DNP en mode CUPS. Deux modes de rendu : **10×15 grand format** (1 photo) ou **bandelettes** (3 photos). Interaction au clavier (3 touches : gauche, milieu, droite) **ou** via un boîtier **Arduino Nano à 3 boutons-poussoirs à LED intégrée** — voir [docs/ARDUINO.md](docs/ARDUINO.md).

---

## Démarrage rapide

**Installation complète Raspberry Pi** : voir le guide pas-à-pas détaillé
👉 **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** (apt, CUPS, systemd autostart, kiosk mode, troubleshooting)

Une fois installé, le cycle quotidien :

```bash
cd ~/Photobooth_Ben
source .venv/bin/activate

# 1. Diagnostic du matériel et des assets (avant chaque événement)
python3 status.py

# 2. Si tout est vert, lancer le photobooth manuellement
python3 Photobooth_start.py
# OU si systemd configuré :
sudo systemctl start photobooth.service

# 3. Après l'événement : rapport stats
python3 stats.py
python3 stats.py --date 2026-04-20   # filtrer par date
python3 stats.py --json              # export machine-readable
```

**Avant le premier lancement**, vérifie que les dossiers d'assets sont en place :

```
assets/
├── interface/
│   ├── background.jpg        # fond d'accueil
│   ├── img_10x15.png         # icône mode grand format
│   └── img_strip.png         # icône mode bandelettes
├── backgrounds/
│   ├── 10x15_background.jpg  # fond d'impression 10x15
│   └── strips_background.jpg # fond d'impression strip
├── overlays/
│   ├── 10x15_overlay.png     # overlay RGBA 10x15
│   └── strips_overlay.png    # overlay RGBA strip
├── fonts/
│   └── WesternBangBang-Regular.ttf
└── sounds/                   # optionnel (silencieux si absents)
    ├── beep.wav              # tick décompte
    ├── shutter.wav           # déclenchement photo
    └── success.wav           # impression lancée
```

---

## Architecture

```
Photobooth_Ben/
├── Photobooth_start.py   # entrée : main() + boucle principale + state + renders + event handlers
├── config.py             # constantes + validation au chargement
├── core/                 # logique métier (testable sans pygame display)
│   ├── logger.py         # logging rotatif + log_info/warning/critical
│   ├── camera.py         # CameraManager (gphoto2 + threading.Lock + retry)
│   ├── montage.py        # MontageGenerator10x15/Strip (PIL)
│   ├── printer.py        # PrinterManager (CUPS lpstat/lp)
│   └── arduino.py        # ArduinoController (pyserial + thread : 3 boutons + LEDs)
├── arduino/              # firmware Nano (optionnel)
│   └── photobooth_buttons/photobooth_buttons.ino
├── ui/                   # couche pygame
│   ├── helpers.py        # UIContext + LoaderAnimation + écrans + sons
│   └── __init__.py       # re-exporte pour `from ui import X`
├── status.py             # diagnostic autonome pré-événement
├── stats.py              # rapport fin de soirée (sessions.jsonl)
├── test_*.py             # suite pytest à la racine (147 tests)
├── README.md
├── deploy/                 # infra Pi (systemd + kiosque)
│   ├── photobooth.service  # unit systemd avec watchdog
│   ├── kiosk.sh            # wrapper démarrage (xset, unclutter, venv)
│   ├── install.sh          # installeur idempotent
│   └── README.md           # guide d'installation
├── docs/
│   ├── ROADMAP.md          # items actionnables priorisés
│   ├── IDEAS.md            # idées en vrac
│   ├── CHANGELOG.md        # historique des sprints
│   ├── ARCHITECTURE.md     # graphe de dépendances + machine d'état
│   ├── DEPLOYMENT.md       # install Raspberry Pi pas-à-pas
│   ├── ARDUINO.md          # câblage, flash firmware, protocole
│   ├── DEVELOPMENT.md      # setup dev local, CI, conventions
│   ├── TESTING.md          # lancer et écrire les tests
│   ├── CONFIG.md           # référence des constantes de config.py
│   ├── PROFILING.md        # protocole de profiling Pi + microbench spinner
│   └── RUNBOOK.md          # checklist événementiel J-1 / J / J+1
└── .gitignore
```

### Modules purs (testables isolément, sans pygame)

- [core/montage.py](core/montage.py) — pur PIL + `config`
- [core/printer.py](core/printer.py) — pur subprocess + `logger`
- [core/logger.py](core/logger.py) — logging standard

### Modules avec dépendances pygame

- [core/camera.py](core/camera.py) — imports optionnels `gphoto2`/`cv2`/`numpy`/`pygame`, fallback sans caméra
- [ui/helpers.py](ui/helpers.py) — `UIContext`, rendus, animations, sons
- [Photobooth_start.py](Photobooth_start.py) — `main()` initialise le runtime ; l'import seul ne lance ni pygame ni le matériel

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) pour le graphe de dépendances + machine d'état + flow de données.

---

## Flux d'une session

```
ACCUEIL → (choix mode + validation) → DECOMPTE → VALIDATION → FIN → impression → ACCUEIL
```

Machine d'état explicite via `Etat` Enum (Sprint 4.5).
Chaque fin de session écrit une ligne JSON dans `data/sessions.jsonl` :

```json
{"session_id": "2026-04-20_14h30_15", "mode": "strips",
 "issue": "printed", "nb_photos": 3, "duree_s": 78.5,
 "ts": "2026-04-20 14:30:45"}
```

`issue` vaut `printed` / `abandoned` / `capture_failed` / `print_failed` /
`print_disabled` — consommé par `stats.py`.

---

## Observabilité

- **Logs rotatifs** : `logs/photobooth.log` (2 Mo × 5 fichiers, rotation auto)
- **Monitoring disque** : check continu pendant l'accueil, bandeau rouge visible si < 500 Mo libres
- **Metadata sessions** : `data/sessions.jsonl` append-only
- **Diagnostic matériel** : `status.py` — vérifie caméra, imprimante, disque, assets critiques

---

## Tests

```bash
python3 -m pytest test_montage.py -v
```

Couvre :
- Helpers `charger_et_corriger` et `_canvas_depuis_bg_ou_blanc`
- Les 4 méthodes `preview()` / `final()` des 2 classes `MontageGenerator*`
- Cohérence config ↔ sortie (tailles, nom de fichier session)

Isolation via `monkeypatch` sur `PATH_TEMP` et chemins BG/overlay inexistants.

---

## Dépendances Python

```bash
pip install pygame opencv-python gphoto2 Pillow numpy pytest
pip install pyserial   # optionnel — uniquement si boîtier Arduino utilisé
```

Système (Raspberry OS / Debian) :
```bash
sudo apt install gphoto2 cups-client
sudo apt install python3-serial   # optionnel — boîtier Arduino
```

---

## Configuration

Tout est dans [config.py](config.py) :
- Résolution écran, polices, couleurs
- Timings : décompte, débounce, flash, slideshow idle
- Imprimantes CUPS (noms des files 10x15 et strip)
- Chemins assets et stockage
- Seuils monitoring (espace disque, timeout splash caméra)
- Dimensions des montages (canvas, photos, offsets)

Validation automatique au chargement — un `AssertionError` explicite au démarrage si une valeur est incohérente.

---

## Documentation

- 🚀 **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — **installation Raspberry Pi** (apt, CUPS, systemd, kiosk, troubleshooting)
- 🎛 **[docs/ARDUINO.md](docs/ARDUINO.md)** — boîtier 3 boutons + LEDs (câblage, flash firmware, protocole)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — diagramme des modules + machine d'état + flow de données
- [docs/PROFILING.md](docs/PROFILING.md) — protocole de profiling sur Pi (cProfile, tracemalloc, `bench_spinner.py`)
- [docs/ROADMAP.md](docs/ROADMAP.md) — items dev à faire, priorisés court/moyen/long terme
- [docs/IDEAS.md](docs/IDEAS.md) — pool d'idées + références open-source (PIBOOTH, photobooth-app, RaspAP)
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — historique des commits par sprint

---

## Licence

Projet personnel. Open à contribution via pull request.
