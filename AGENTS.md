# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project

Event photobooth app (Pygame + gphoto2 + PIL) targeting a Raspberry Pi with a Canon EOS camera and a DNP printer over CUPS. Two render modes: **10×15** (single photo) and **strips** (3 photos). Input is 3 keys or an Arduino Nano 3-button box. Code, commits, and docs are primarily in **French**; match that language when editing existing files.

## Common commands

```bash
# Tests (48 tests, ~2 s) — pure-Python modules only
pytest                                   # full suite
pytest test_montage.py -v                # single file
pytest test_montage.py::test_name -v     # single test
pytest --cov --cov-report=term-missing   # coverage (threshold: fail_under=75)

# Lint / format (config in pyproject.toml)
ruff check .
ruff check --fix .
ruff format .                            # not in pre-commit

# Pre-commit (runs ruff --fix + pytest test_montage.py)
pre-commit install

# Run the app (requires pygame + hardware, typically on the Pi)
python3 Photobooth_start.py

# Pre-event hardware/assets diagnostic
python3 status.py

# Post-event session report (reads data/sessions.jsonl)
python3 stats.py
python3 stats.py --date 2026-04-20
python3 stats.py --json

# Profiling (see docs/PROFILING.md for the full Pi protocol)
python3 profile.py        # cProfile → profile.stats (open with snakeviz)
python3 profile_mem.py    # tracemalloc
python3 bench_spinner.py  # LoaderAnimation microbench (--points N to override)
```

CI (`.github/workflows/ci.yml`) installs only `Pillow pytest pytest-cov ruff` — `pygame`/`gphoto2`/`cv2`/`pyserial` are **never** installed in CI.

## Architecture

### Layering (strict import rules)

```
Photobooth_start.py  ──► imports everything
        │
        ├──► ui/*           (pygame surfaces, fonts, loaders, sounds)
        │      │
        │      └──► core/*  (ui may import core; core may NOT import ui)
        │
        └──► core/*         (pure business logic; no ui/, no Photobooth_start)
               │
               └──► config  (shared constants; validated at import time)
```

- `core/*` must never import `ui.*` or `Photobooth_start`.
- `ui/helpers.py` may import `core.*` but not `Photobooth_start`.
- `config.py` imports nothing from the project; it wraps `import pygame` in try/except so `status.py` can load it on machines without pygame.
- `core/montage.py` is **lazy-imported** inside `ui.get_pygame_surf` to avoid loading PIL at startup.
- Standalone scripts (`status.py`, `stats.py`) import only `config`.

### Pure vs hardware-bound modules

Tested in CI (pure Python + PIL): `core/montage.py`, `core/printer.py` (subprocess-mocked), `core/logger.py`, `core/session.py`, `core/monitoring.py`, `core/arduino.py` (FakeSerial/FakePygame), `stats.py`, `status.py`.

**Not testable in CI** (require real hardware or pygame): `Photobooth_start.py`, `ui/helpers.py`, `core/camera.py`. The `[tool.coverage.run] source` in `pyproject.toml` deliberately excludes `Photobooth_start.py`/`ui/` since they need a runtime.

### State machine (driven by `core/session.py`)

`ACCUEIL → DECOMPTE → VALIDATION → FIN → (print) → ACCUEIL`

- `Etat` (enum) + `SessionState` (dataclass) live in `core/session.py`.
- The main loop in `Photobooth_start.py` dispatches render + event handlers by `session.etat`.
- A slideshow overlay triggers on `ACCUEIL` when `time.time() - session.last_activity_ts > DUREE_IDLE_SLIDESHOW`; first key press only wakes it.
- End of each session appends a JSON line to `data/sessions.jsonl` (`issue` = `printed`/`abandoned`/`capture_failed`) — consumed by `stats.py`.

See `docs/ARCHITECTURE.md` for the full flow, artifacts table (raw, temp, print, skipped, logs, sessions.jsonl), and class diagram.

### Singletons & threading

Module-level singletons (`camera_mgr`, `printer_mgr`, `session`, `UIContext`) rather than DI — tests use `monkeypatch`. Only one worker thread: `executer_avec_spinner()` runs `MontageGenerator*.final()` in a daemon thread while the main thread animates a spinner. All pygame surface access stays on the main thread. `CameraManager` holds a `threading.Lock` (reserved for future async capture).

### Hardware-optional pattern

The app degrades gracefully when `gphoto2`, `cups`, or `pyserial` is missing — follow the `try/except ImportError` pattern seen in `config.py:3-6` when adding a new optional dependency. `assets/sounds/*.wav` are also optional (silent if absent).

## Conventions

- **Test file location**: `test_*.py` at the **repo root** (not under `tests/`). This is the project convention, enforced by `pyproject.toml` `testpaths = ["."]`.
- **Test isolation**: use `tmp_path` + `monkeypatch.setattr("core.montage.PATH_TEMP", str(tmp_path))` to isolate filesystem writes; never write into the real `data/` tree from tests. See `test_montage.py` for `photo_factice` / `trois_photos` fixtures.
- **Config-driven**: all tunables (resolutions, timings, CUPS queue names, montage geometry) live in `config.py` with assertion-based validation at import. When adding/changing a tunable, also update `docs/CONFIG.md`.
- **Ruff**: defaults (E, F, W) only; `E501` is ignored, `line-length = 110`. Keep it clean — CI fails on any ruff issue.
- **Coverage**: `fail_under = 75`; actual ~80 %. `core/camera.py` is 0 % by design (hardware), which drags the average — new pure code should stay above 87 %.
- **Commits/branches**: French, free-form but `<domain>: <short description>` is the observed pattern (`docs:`, `tests:`, sprint/feature name). Keep history **bisectable** — each commit should pass tests. PRs target `main`; squash-merge for noisy branches.
- **Never use `--no-verify`** on `main`; if a pre-commit hook fails, fix the root cause.

## What to update when you change something

- Touch `config.py` → update `docs/CONFIG.md`.
- Touch the module graph or state machine → update `docs/ARCHITECTURE.md`.
- Ship a sprint → update `docs/CHANGELOG.md` and `docs/ROADMAP.md`.
- New deployment step → update `docs/DEPLOYMENT.md` and/or `deploy/install.sh`.

## Reference docs

`docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/TESTING.md`, `docs/CONFIG.md`, `docs/DEPLOYMENT.md`, `docs/ARDUINO.md`, `docs/RUNBOOK.md`, `docs/PROFILING.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`, `docs/IDEAS.md`.
