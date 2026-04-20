# Développement — Photobooth Ben

Guide pour contribuer au code : setup local, conventions, outils qualité, CI.
Pour les tests eux-mêmes voir [TESTING.md](TESTING.md). Pour le déploiement
sur Raspberry voir [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Setup local (macOS / Linux dev)

### 1. Clone + venv

```bash
git clone <repo-url> Photobooth_Ben
cd Photobooth_Ben
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Dépendances

Pour **contribuer au code pur** (montage, stats, status, tests), seul Pillow
+ outils dev suffisent :

```bash
pip install Pillow pytest pytest-cov ruff pre-commit
```

Pour **lancer l'appli complète en local** (besoin d'un mac ou Linux avec
pygame) :

```bash
pip install pygame
# gphoto2/CUPS/pyserial : difficiles à installer hors Pi, l'appli tolère
# leur absence en mode dégradé (voir config.py:3-6 pour le pattern).
```

### 3. Pre-commit hook

Après `pip install pre-commit` :

```bash
pre-commit install
```

À partir de là, chaque `git commit` déclenche automatiquement :
- `ruff --fix` (auto-fix des warnings)
- `pytest test_montage.py -q` (tests les plus rapides)

Voir [`.pre-commit-config.yaml`](../.pre-commit-config.yaml).

> Si tu dois commiter sans hook (cas rare, ex: WIP sur feature branche perso) :
> `git commit --no-verify`. Évite sur `main`.

---

## Structure du repo

```
Photobooth_Ben/
├── Photobooth_start.py   # entrée : bootstrap + renders + event handlers + boucle principale (~1070 L)
├── config.py             # 96 constantes partagées — voir CONFIG.md
├── core/                 # modules métier (testables sans pygame)
│   ├── arduino.py        # pyserial + thread → injecte KEYDOWN, pilote LEDs
│   ├── camera.py         # gphoto2 + lock + retry
│   ├── logger.py         # logging rotatif + sessions.jsonl
│   ├── monitoring.py     # DiskMonitor + lister_images_slideshow
│   ├── montage.py        # PIL : MontageGenerator10x15/Strip
│   ├── printer.py        # CUPS
│   └── session.py        # Etat enum + SessionState + metadata JSONL
├── ui/                   # helpers pygame (surfaces, fontes, caches)
│   └── helpers.py
├── status.py             # diagnostic standalone (matériel, assets)
├── stats.py              # rapport post-événement (sessions.jsonl)
├── profile.py            # profiling CPU (cProfile)
├── profile_mem.py        # profiling mémoire (tracemalloc)
├── test_*.py             # tests pytest
├── arduino/              # firmware Nano (.ino)
├── deploy/               # infra Pi : systemd unit, kiosk.sh, installer
└── docs/                 # toute la doc .md
```

Voir [ARCHITECTURE.md](ARCHITECTURE.md) pour le graphe de dépendances.

### Règles d'importation

- `Photobooth_start.py` peut importer tout.
- `core/*` n'importe pas de `ui/*`.
- `ui/*` peut importer `core/*`.
- Ni `core/` ni `ui/` n'importent `Photobooth_start`.
- Import lazy : `core/montage` chargé à la volée dans `ui.get_pygame_surf`
  pour éviter de charger PIL au démarrage.

---

## Outils qualité

### Ruff (lint + format)

Config : [`pyproject.toml`](../pyproject.toml) section `[tool.ruff]`.

```bash
ruff check .              # lint
ruff check --fix .        # auto-fix
ruff format .             # formate (non obligatoire, pas en pre-commit)
```

Règles actives : défauts (E, F, W). `E501` (ligne trop longue) ignoré —
`line-length = 110`.

### Pytest

Voir [TESTING.md](TESTING.md).

```bash
pytest                    # tous les tests, rapide (~2 s)
pytest --cov              # avec couverture
```

### Profiling

```bash
python3 profile.py        # cProfile → profile.stats (ouvrir avec snakeviz)
python3 profile_mem.py    # tracemalloc top-N allocations
```

Ignorés par `.gitignore` (voir `.coverage`, `htmlcov/`, `profile.stats`).

---

## CI (GitHub Actions)

Config : [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

À chaque push ou PR sur `main` :
1. `ruff check .` — échec bloquant
2. `pytest --cov --cov-report=term`
3. `coverage report` — échec si sous `fail_under = 30 %`

Pas de build pygame/gphoto2 en CI : seuls les modules purs sont testés. Voir
[TESTING.md § Pourquoi certains modules ne sont pas testés](TESTING.md#pourquoi-certains-modules-ne-sont-pas-testés).

---

## Conventions Git

### Branches

- `main` : stable, déployé sur le Pi.
- `<feature>` : branche de travail. Merge via PR, pas de push direct sur main
  pour les grosses features.
- Exemple historique : `Arduino-boutton` → PR #1 → merge via squash/merge.

### Commits

Format libre mais conventions implicites observées dans le log :

```
<domaine>: <description courte>

- détail 1
- détail 2
```

Domaines courants : `docs`, `tests`, `Items N—…`, `Quick wins`, nom de la
feature (`Arduino Nano …`).

Garder un historique **bisectable** : chaque commit doit idéalement compiler et
passer les tests, pour pouvoir `git bisect` en cas de régression entre deux
événements.

### Tags

Pas encore utilisés systématiquement. Proposition : tag `event-YYYY-MM-DD`
avant chaque événement réel, pour rollback rapide.

---

## Workflow type : ajouter une feature

1. Crée une branche : `git checkout -b feature/nom-court`
2. Code + tests dans `test_<module>.py`
3. Lance `pytest` + `ruff check .` en local
4. Commit (pre-commit relance ruff + pytest montage)
5. Push + ouvre la PR
6. La CI valide (ruff + tests + coverage)
7. Merge sur `main` (squash recommandé si nombreux commits WIP)
8. Mets à jour [CHANGELOG.md](CHANGELOG.md) et [ROADMAP.md](ROADMAP.md)
9. Si feature touche la config : mets à jour [CONFIG.md](CONFIG.md)
10. Si feature touche l'archi : mets à jour [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Ce que la CI ne détecte pas

- Régressions visuelles (un layout cassé passe les tests PIL)
- Bugs d'intégration caméra USB (lock, retry, disconnect)
- Bugs d'impression (driver CUPS, file bloquée, papier mal chargé)
- Bugs Arduino (LEDs pas synchro avec Etat)
- Performances sur Raspberry (OK en CI Ubuntu != OK sur Pi 4)

**→ Toujours valider sur matos cible avant un événement**
(voir [RUNBOOK.md](RUNBOOK.md)).
