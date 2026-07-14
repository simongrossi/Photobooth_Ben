# Tests — Photobooth Ben

Guide pour lancer, comprendre et étendre la suite de tests. Le projet utilise
**pytest** + **pytest-cov**, avec un découpage entre tests **unitaires** (modules
isolés) et **intégration** (orchestration de plusieurs modules).

Voir aussi : [DEVELOPMENT.md](DEVELOPMENT.md) pour le setup local, pre-commit et CI.

---

## Lancer les tests

```bash
# Toute la suite
pytest

# Un fichier précis
pytest tests/test_montage.py -v

# Un seul test
pytest tests/test_montage.py::test_nom_du_test -v

# Avec couverture (voir [pyproject.toml](../pyproject.toml))
pytest --cov --cov-report=term

# Rapport HTML détaillé (ligne par ligne)
pytest --cov --cov-report=html
open htmlcov/index.html
```

Le seuil de couverture minimum est fixé à **75 %** dans `pyproject.toml`
(`fail_under`). Mesure actuelle : **87,6 %** globale ; les nouveaux modules
purs de performance restent entre **89 % et 97 %**.

---

## Inventaire des fichiers de tests

| Fichier | Tests | Couvre | Stratégie |
|---|---|---|---|
| [test_camera.py](../tests/test_camera.py) | 9 | `core/camera.py` (imports optionnels, preview, capture, close) | mocks gphoto2/cv2/numpy/pygame + subprocess |
| [test_montage.py](../tests/test_montage.py) | 31 | `core/montage.py` (PIL, 10×15/strip, calques, watermark, grain, cache assets) | monkeypatch des `PATH_*` + fixtures PIL synthétiques |
| [test_mise_en_page.py](../tests/test_mise_en_page.py) | 7 | validation, lecture et écriture atomique de la zone photo 10×15 | JSON isolé dans `tmp_path` |
| [test_arduino.py](../tests/test_arduino.py) | 19 | `core/arduino.py` (ArduinoController, LEDs, tick, read loop) | FakeSerial + FakePygame mocks |
| [test_printer.py](../tests/test_printer.py) | 18 | `core/printer.py` (PrinterManager, lpstat/lp) | mock `subprocess.run`/`Popen` |
| [test_logger.py](../tests/test_logger.py) | 4 | `core/logger.py` (log_error wrapper legacy) | `caplog` pytest |
| [test_session.py](../tests/test_session.py) | 11 | `core/session.py` (Etat, SessionState, metadata JSONL) | monkeypatch `PATH_DATA` |
| [test_evenements.py](../tests/test_evenements.py) | 4 | partage actif + instantané de session | `tmp_path`, JSON synthétique |
| [test_monitoring.py](../tests/test_monitoring.py) | 36 | `core/monitoring.py` (monitoring, slideshow et exclusion des sorties techniques) | fixtures `tmp_path` |
| [test_status.py](../tests/test_status.py) | 18 | `status.py` (diagnostic hardware/assets) | fixtures assets factices dans `tmp_path` |
| [test_stats.py](../tests/test_stats.py) | 25 | `stats.py` (parsing `sessions.jsonl`, histogramme horaire, CLI JSON) | fixtures JSONL synthétiques + subprocess |
| [test_integration.py](../tests/test_integration.py) | 8 | chaîne `CameraManager` → `MontageGenerator` → `PrinterManager`, import sans runtime | mocks gphoto2/CUPS/pygame, réels PIL |
| [test_web_evenements.py](../tests/test_web_evenements.py) | 6 | CRUD, activation, filtres et export ZIP | Flask test client + SQLite/filesystem isolés |
| [test_web_gallery.py](../tests/test_web_gallery.py) | 15 | galerie, miniatures cachées, corbeille et exclusion des sorties techniques | Flask test client + filesystem isolé |
| [test_web_templates.py](../tests/test_web_templates.py) | 28 | bibliothèque deux couches + éditeur 10×15 + migrations | Flask test client + SQLite/filesystem isolés |
| [test_nettoyer_sorties_tests.py](../tests/test_nettoyer_sorties_tests.py) | 3 | inventaire et déplacement réversible des sorties techniques | arborescences `tmp_path` |
| [test_profiling_tools.py](../tests/test_profiling_tools.py) | 2 | import `cProfile` et lancement explicite du kiosque profilé | faux module `Photobooth_start` |

**Non couvert en CI** (nécessite pygame/gphoto2/caméra réelle) :
- `Photobooth_start.py` — boucle principale, render functions, event handlers
- `ui/helpers.py` — dépend de pygame.Surface
- `core/printer.py` — dépend de CUPS
- `core/arduino.py` — dépend de pyserial + Nano physique

Le module [Photobooth_start.py](../Photobooth_start.py) est maintenant
**importable sans lancer le kiosque** : le runtime pygame/caméra/Arduino ne
démarre que dans `main()`. Les tests peuvent donc vérifier le contrat d'import
sans ouvrir de fenêtre ni toucher au matériel.

---

## Pourquoi certains modules ne sont pas testés

La CI tourne sur **Ubuntu GitHub Actions** sans caméra, imprimante ni Arduino.
On n'installe volontairement que les **modules purs Python** (Pillow, pytest) —
voir [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

Pour tester les modules hardware-dépendants, il faut :

1. Un **Raspberry Pi de dev** avec toutes les dépendances (voir
   [DEPLOYMENT.md](DEPLOYMENT.md) sections 3-4)
2. Un Canon EOS, une imprimante DNP, ou un Arduino flashé
3. Lancer `pytest` sur le Pi (pas en CI)

Les chemins hardware critiques sont couverts par mocks quand c'est raisonnable
(`core/camera.py`, CUPS, pyserial). Les essais avec vrai matériel restent à faire
sur Raspberry avant événement.

---

## Écrire un nouveau test

### Convention de nommage

- Fichier : `tests/test_<module>.py` dans le dossier `tests/`.
- Fonction : `test_<ce_que_le_test_vérifie>()` — verbe à l'impératif OK.
- Les fixtures partagées vont en **haut du fichier** (pas encore de `conftest.py`
  — à créer si fixture partagée entre fichiers).

### Isolement du système de fichiers

Tout test qui écrit sur disque doit utiliser la fixture pytest `tmp_path` et
monkeypatcher les chemins de `config` au besoin :

```python
def test_genere_montage(tmp_path, monkeypatch):
    monkeypatch.setattr("core.montage.PATH_TEMP", str(tmp_path))
    # ...
```

Un montage strip écrit aussi son fichier `*_CLEAN.jpg` et son dossier
`READY_TO_PRINT` dans `PATH_PRINT_STRIP` : ce chemin doit donc être redirigé
vers `tmp_path` en plus de `PATH_TEMP`.

Voir [test_montage.py](../tests/test_montage.py) pour les fixtures types (`photo_factice`,
`trois_photos`) et l'isolement disque propre.

### Mocker gphoto2 / CUPS / pyserial

Pattern utilisé dans [test_integration.py](../tests/test_integration.py) :

```python
def test_pipeline_complete(monkeypatch):
    monkeypatch.setattr("core.camera.gp", FakeGphoto2())
    # le reste du test voit l'instance factice
```

Pour pygame, `config.py` a un import **tolérant** (`try/except ImportError`)
qui permet de charger la config sans pygame — utile pour les tests.

---

## Couverture actuelle (estimée)

Modules mesurés (voir `[tool.coverage.run] source` dans `pyproject.toml`) :

| Module | Couverture | Commentaire |
|---|---|---|
| `core/montage.py` | 93 % | 27 tests dédiés |
| `core/camera.py` | 90 % | mocks gphoto2/cv2/numpy/pygame + subprocess |
| `core/printer.py` | 100 % | mocks subprocess |
| `core/logger.py` | 94 % | log_error + usage transitif |
| `core/arduino.py` | 87 % | FakeSerial + FakePygame |
| `core/session.py` | 100 % | dataclass + metadata JSONL |
| `core/monitoring.py` | 96 % | DiskMonitor + TempMonitor + slideshow listing |
| `stats.py` | 100 % | tests in-process + CLI |
| `status.py` | 91 % | fixtures + main() en process |

Pour voir le détail réel :

```bash
pytest --cov --cov-report=term-missing
```

---

## Dépannage

**`ModuleNotFoundError: No module named 'pygame'`**
→ Normal, les tests ne nécessitent pas pygame. Si ça bloque, vérifier que tu
ne fais pas `import pygame` directement dans un module testé. Utiliser le
pattern `try/except ImportError` (voir `config.py:3-6`).

**Tests `pass` mais coverage 0 %**
→ Tu testes probablement du code dans un `if __name__ == '__main__'` (exclu par
`[tool.coverage.report] exclude_lines`). Extrais la logique dans une fonction
testable.

**Ruff signale des warnings dans les tests**
→ `pyproject.toml` applique les mêmes règles partout. Ajoute `# noqa: <code>`
si vraiment nécessaire, sinon corrige.
