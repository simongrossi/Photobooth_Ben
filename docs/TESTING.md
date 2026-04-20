# Tests — Photobooth Ben

Guide pour lancer, comprendre et étendre la suite de tests. Le projet utilise
**pytest** + **pytest-cov**, avec un découpage entre tests **unitaires** (modules
isolés) et **intégration** (orchestration de plusieurs modules).

Voir aussi : [DEVELOPMENT.md](DEVELOPMENT.md) pour le setup local, pre-commit et CI.

---

## Lancer les tests

```bash
# Tous les tests (48 tests, ~2 s)
pytest

# Un fichier précis
pytest test_montage.py -v

# Un seul test
pytest test_montage.py::test_nom_du_test -v

# Avec couverture (voir [pyproject.toml](../pyproject.toml))
pytest --cov --cov-report=term

# Rapport HTML détaillé (ligne par ligne)
pytest --cov --cov-report=html
open htmlcov/index.html
```

Le seuil de couverture minimum est fixé à **30 %** dans `pyproject.toml`
(`fail_under`). Cible court terme : **60 %**. Cible moyen terme : **80 %**.

---

## Inventaire des fichiers de tests

| Fichier | Tests | Couvre | Stratégie |
|---|---|---|---|
| [test_montage.py](../test_montage.py) | 18 | `core/montage.py` (PIL, MontageGenerator10x15/Strip) | monkeypatch des `PATH_*` + fixtures PIL synthétiques |
| [test_status.py](../test_status.py) | 13 | `status.py` (diagnostic hardware/assets) | fixtures assets factices dans `tmp_path` |
| [test_stats.py](../test_stats.py) | 11 | `stats.py` (parsing `sessions.jsonl`, histogramme horaire) | fixtures JSONL synthétiques |
| [test_integration.py](../test_integration.py) | 6 | chaîne `CameraManager` → `MontageGenerator` → `PrinterManager` | mocks gphoto2/CUPS, réels PIL |

**Non couvert en CI** (nécessite pygame/gphoto2/caméra réelle) :
- `Photobooth_start.py` — boucle principale, render functions, event handlers
- `ui/helpers.py` — dépend de pygame.Surface
- `core/camera.py` — dépend du hardware gphoto2
- `core/printer.py` — dépend de CUPS
- `core/arduino.py` — dépend de pyserial + Nano physique

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

Alternative envisageable : tests d'intégration avec mocks gphoto2/CUPS plus
poussés — cf. [ROADMAP.md](ROADMAP.md) section Tests & qualité.

---

## Écrire un nouveau test

### Convention de nommage

- Fichier : `test_<module>.py` à la racine (pas dans un dossier `tests/`,
  convention historique du projet).
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

Voir [test_montage.py](../test_montage.py) pour les fixtures types (`photo_factice`,
`trois_photos`) et l'isolement disque propre.

### Mocker gphoto2 / CUPS / pyserial

Pattern utilisé dans [test_integration.py](../test_integration.py) :

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

| Module | Couverture estimée | Commentaire |
|---|---|---|
| `core/montage.py` | ~85 % | 18 tests dédiés |
| `core/camera.py` | ~20 % | mocks partiels via `test_integration` |
| `core/printer.py` | ~15 % | idem |
| `core/logger.py` | ~40 % | utilisé transitivement par autres tests |
| `core/arduino.py` | ~0 % | non testé (pyserial non mocké) |
| `stats.py` | ~90 % | 11 tests dédiés |
| `status.py` | ~80 % | 13 tests dédiés |

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
