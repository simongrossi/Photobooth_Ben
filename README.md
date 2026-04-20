# Photobooth Ben

Application photobooth événementiel en **Pygame + gphoto2 + PIL**, conçue pour un Raspberry Pi connecté à un Canon EOS et une imprimante DNP en mode CUPS. Deux modes de rendu : **10×15 grand format** (1 photo) ou **bandelettes** (3 photos). Lancement/interaction au clavier (3 touches : gauche, milieu, droite).

---

## Démarrage rapide

```bash
# 1. Diagnostic du matériel et des assets (avant chaque événement)
python3 status.py

# 2. Si tout est vert, lancer le photobooth
python3 Photobooth_start.py

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

| Fichier | Rôle |
|---------|------|
| [Photobooth_start.py](Photobooth_start.py) | Entrée + boucle principale + UI pygame |
| [config.py](config.py) | Constantes centralisées + validation au chargement |
| [camera.py](camera.py) | `CameraManager` — gphoto2 avec `threading.Lock` + retry |
| [montage.py](montage.py) | `MontageGenerator10x15` / `MontageGeneratorStrip` — génération PIL |
| [printer.py](printer.py) | `PrinterManager` — CUPS `lpstat` + `lp` |
| [logger.py](logger.py) | Logging rotatif + `log_info` / `log_warning` / `log_critical` |
| [status.py](status.py) | Diagnostic autonome pré-événement |
| [stats.py](stats.py) | Rapport fin de soirée à partir de `sessions.jsonl` |
| [test_montage.py](test_montage.py) | 18 tests pytest (isolation via `monkeypatch`) |

### Modules purs (testables isolément, sans pygame)

- `montage.py` — pur PIL + `config`
- `printer.py` — pur subprocess + `logger`
- `logger.py` — logging standard

### Modules avec dépendances pygame

- `camera.py` — utilise `pygame.surfarray.make_surface` pour convertir les frames gphoto2
- `Photobooth_start.py` — boucle principale, fontes, UI helpers, machine d'état

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

`issue` vaut `printed` / `abandoned` / `capture_failed` — consommé par `stats.py`.

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
```

Système (Raspberry OS / Debian) :
```bash
sudo apt install gphoto2 cups-client
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

## Roadmap & idées

- [docs/ROADMAP.md](docs/ROADMAP.md) — items actionnables priorisés (court / moyen / long terme)
- [docs/IDEAS.md](docs/IDEAS.md) — pool d'idées en vrac + références open-source (PIBOOTH, photobooth-app, RaspAP, nodogsplash)

---

## Historique des sprints

Le projet a été refactoré par sprints incrémentaux (voir commit history) :
- **Sprint 1** — stabilité (fuites, retry, except)
- **Sprint 2** — UX événementiel (flash, sons, écrans d'erreur, confirmation abandon)
- **Sprint 3** — performance (threading, cache, loader GC)
- **Sprint 4** — architecture modulaire (extraction CameraManager, MontageGenerator, PrinterManager, logger)
- **Sprint 5** — observabilité (logging rotatif, metadata sessions, monitoring disque, status.py, stats.py)
- **Sprint 6** — features événementiel (slideshow idle, compteur photo strip)

Chaque item est documenté dans [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Licence

Projet personnel. Open à contribution via pull request.
