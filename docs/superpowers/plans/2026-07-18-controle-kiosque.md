# Contrôle du kiosque (volet 3) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Panneau admin « Contrôle du kiosque » (redémarrer / arrêter le kiosque, redémarrer la machine) + pastille d'état du service, sur la base systemd déjà présente dans `deploy/`.

**Architecture:** Nouveau module `web/systeme.py` = liste blanche fermée de 3 actions (`sudo -n systemctl …`) + `etat_kiosque()` (`systemctl is-active`, sans sudo). `settings_route._redemarrer_kiosque()` (déjà existant) est refactoré pour déléguer à ce module (une seule implémentation). `install-admin.sh` étend le sudoers existant (restart seul → restart/stop/start/reboot). Dashboard : pastille santé + panneau 3 boutons admin-only, routes POST sous `require_auth`.

**Tech Stack:** Flask, subprocess (mocké en test), sudoers/visudo, pytest.

**Spec :** `docs/superpowers/specs/2026-07-18-controle-kiosque-design.md` · **Branche :** `controle-kiosque`

**État déjà en place (ne pas recréer) :** `deploy/photobooth.service` (watchdog), `deploy/kiosk.sh`, `install-admin.sh` §4 sudoers (restart seul), `settings_route.py` : `KIOSQUE_SERVICE`, `SUDO_PATH`, `SYSTEMCTL_PATH`, `_redemarrer_kiosque()`.

---

### Task 1 : `web/systeme.py` — liste blanche + état

**Files:** Create `web/systeme.py` ; Create `tests/test_web_systeme.py`.

- [ ] Tests (`tests/test_web_systeme.py`) :

```python
"""test_web_systeme.py — contrôle du kiosque : liste blanche, exécution, état."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from web import systeme


def _fake_run(returncode=0, stdout="", stderr=""):
    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return run


class TestListeBlanche:
    def test_action_inconnue_leve(self):
        with pytest.raises(ValueError):
            systeme.executer_action("rm-rf")

    def test_les_trois_actions_existent(self):
        assert set(systeme.ACTIONS) == {
            "redemarrer-kiosque", "arreter-kiosque", "redemarrer-machine",
        }

    def test_commandes_utilisent_sudo_n(self):
        for cmd in systeme.ACTIONS.values():
            assert cmd[1] == "-n"          # sudo non-interactif
            assert "systemctl" in cmd[2]


class TestExecution:
    def test_succes(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0))
        ok, msg = systeme.executer_action("redemarrer-kiosque")
        assert ok is True

    def test_echec_sudo(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run",
                            _fake_run(1, stderr="sudo: a password is required"))
        ok, msg = systeme.executer_action("arreter-kiosque")
        assert ok is False
        assert "password" in msg

    def test_timeout(self, monkeypatch):
        def run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 10)
        monkeypatch.setattr(systeme.subprocess, "run", run)
        ok, msg = systeme.executer_action("redemarrer-kiosque")
        assert ok is False

    def test_commande_absente(self, monkeypatch):
        def run(cmd, **kwargs):
            raise OSError("no such file")
        monkeypatch.setattr(systeme.subprocess, "run", run)
        ok, msg = systeme.executer_action("redemarrer-machine")
        assert ok is False


class TestEtatKiosque:
    def test_actif(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0, stdout="active\n"))
        assert systeme.etat_kiosque() == "active"

    def test_arrete(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(3, stdout="inactive\n"))
        assert systeme.etat_kiosque() == "inactive"

    def test_en_panne(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(3, stdout="failed\n"))
        assert systeme.etat_kiosque() == "failed"

    def test_indisponible(self, monkeypatch):
        def run(cmd, **kwargs):
            raise OSError("systemctl introuvable")
        monkeypatch.setattr(systeme.subprocess, "run", run)
        assert systeme.etat_kiosque() == "indisponible"
```

- [ ] Vérifier l'échec (`pytest tests/test_web_systeme.py -q` → ModuleNotFoundError),
  puis créer `web/systeme.py` :

```python
"""systeme.py — contrôle du service kiosque depuis l'admin web (liste blanche).

Trois actions fermées, exécutées via `sudo -n systemctl …` grâce à la règle
`/etc/sudoers.d/photobooth-admin` posée par deploy/install-admin.sh. L'action
est une CLÉ de dictionnaire — jamais un fragment de commande : impossible
d'injecter quoi que ce soit depuis la requête HTTP.

`etat_kiosque()` lit l'état du service sans sudo (`systemctl is-active`).
Sur une machine sans systemd (dev macOS), tout dégrade proprement :
état 'indisponible', actions en échec avec message clair.
"""
from __future__ import annotations

import shutil
import subprocess

SUDO_PATH = shutil.which("sudo") or "/usr/bin/sudo"
SYSTEMCTL_PATH = shutil.which("systemctl") or "/usr/bin/systemctl"
SERVICE_KIOSQUE = "photobooth.service"
TIMEOUT_S = 20

ACTIONS = {
    "redemarrer-kiosque": [SUDO_PATH, "-n", SYSTEMCTL_PATH, "restart", SERVICE_KIOSQUE],
    "arreter-kiosque":    [SUDO_PATH, "-n", SYSTEMCTL_PATH, "stop", SERVICE_KIOSQUE],
    "redemarrer-machine": [SUDO_PATH, "-n", SYSTEMCTL_PATH, "reboot"],
}

LIBELLES = {
    "redemarrer-kiosque": "Redémarrage du kiosque lancé (~10 s).",
    "arreter-kiosque": "Kiosque arrêté — relançable via « Redémarrer le kiosque ».",
    "redemarrer-machine": "Redémarrage de la machine lancé — de retour dans ~1 minute.",
}


def executer_action(action: str) -> tuple[bool, str]:
    """Exécute une action de la liste blanche. Retourne (ok, message utilisateur).

    Lève ValueError si l'action n'est pas dans la liste blanche (la route en
    fait un 404).
    """
    commande = ACTIONS.get(action)
    if commande is None:
        raise ValueError(f"Action système inconnue : {action!r}")
    try:
        resultat = subprocess.run(
            commande, capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"L'action a dépassé {TIMEOUT_S} secondes."
    except OSError as e:
        return False, f"Commande indisponible sur cette machine : {e}"
    if resultat.returncode == 0:
        return True, LIBELLES[action]
    detail = (resultat.stderr or resultat.stdout).strip()
    suffixe = f" ({detail[:200]})" if detail else ""
    return False, f"Échec de l'action{suffixe}. Vérifie la règle sudoers (install-admin.sh)."


def etat_kiosque() -> str:
    """'active' | 'inactive' | 'failed' | 'indisponible' (sans sudo)."""
    try:
        resultat = subprocess.run(
            [SYSTEMCTL_PATH, "is-active", SERVICE_KIOSQUE],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "indisponible"
    etat = (resultat.stdout or "").strip()
    return etat if etat in ("active", "inactive", "failed") else (etat or "indisponible")
```

- [ ] `pytest tests/test_web_systeme.py -q` PASS →
  commit `feat(admin): module systeme (liste blanche de contrôle du kiosque)`.

### Task 2 : Refactor `settings_route` → délégation

**Files:** Modify `web/routes/settings_route.py`.

- [ ] Remplacer le corps de `_redemarrer_kiosque()` par une délégation (le message
  « Réglages appliqués » est conservé) :

```python
def _redemarrer_kiosque() -> tuple[bool, str]:
    """Redémarre seulement le kiosque via la règle sudoers installée."""
    ok, message = systeme.executer_action("redemarrer-kiosque")
    if ok:
        return True, "Réglages appliqués : le service kiosque a été redémarré."
    return False, message
```

  avec `from web import systeme` dans les imports ; supprimer `SUDO_PATH`,
  `SYSTEMCTL_PATH`, `KIOSQUE_SERVICE` et l'import `shutil`/`subprocess` de ce
  fichier **s'ils n'ont plus d'autre usage** (vérifier par grep avant).
- [ ] `pytest tests/test_web_settings.py -q` PASS (adapter le monkeypatch des tests
  existants s'ils patchaient `settings_route.subprocess` → patcher `systeme.subprocess`).
- [ ] Commit `refactor(admin): settings délègue le restart kiosque à web.systeme`.

### Task 3 : Routes dashboard + pastille état + panneau

**Files:** Modify `web/routes/dashboard.py`, `web/templates/dashboard.html` ;
Test `tests/test_web_systeme.py` (classe routes).

- [ ] Tests (fin de `tests/test_web_systeme.py`) — fixture minimale comme
  `tests/test_web_auth_viewer.py` (PATH_DATA/DB_PATH monkeypatchés, mot de passe
  `test`), puis :

```python
class TestRoutesSysteme:
    def test_action_valide_redirige(self, client, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0))
        r = client.post("/dashboard/systeme/redemarrer-kiosque",
                        headers=HEADERS_OK, follow_redirects=True)
        assert r.status_code == 200

    def test_action_inconnue_404(self, client):
        assert client.post("/dashboard/systeme/pwn",
                           headers=HEADERS_OK).status_code == 404

    def test_sans_auth_401(self, client):
        assert client.post("/dashboard/systeme/redemarrer-kiosque").status_code == 401

    def test_viewer_ne_voit_pas_le_panneau(self, client, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0, stdout="active\n"))
        html = client.get("/dashboard/").get_data(as_text=True)
        assert "Contrôle du kiosque" not in html

    def test_admin_voit_le_panneau(self, client, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", _fake_run(0, stdout="active\n"))
        html = client.get("/dashboard/", headers=HEADERS_OK).get_data(as_text=True)
        assert "Contrôle du kiosque" in html
        assert "/dashboard/systeme/redemarrer-machine" in html
```

- [ ] `dashboard.py` : `from web import systeme` ; dans `_construire_sante`, ajouter
  en tête de liste :

```python
    etat_k = systeme.etat_kiosque()
    mapping = {"active": ("ok", "actif"), "inactive": ("warn", "arrêté"),
               "failed": ("err", "en panne"), "indisponible": ("na", "N/A")}
    etat, detail = mapping.get(etat_k, ("na", etat_k))
    sante.insert(0, {"libelle": "Kiosque", "etat": etat, "detail": detail})
```

  et la route :

```python
@bp.route("/systeme/<action>", methods=["POST"])
@require_auth
def action_systeme(action: str):
    """Contrôle du kiosque (liste blanche web/systeme.py). Admin uniquement."""
    try:
        ok, message = systeme.executer_action(action)
    except ValueError:
        abort(404)
    flash(message, "success" if ok else "error")
    return redirect(url_for("dashboard.index"))
```

  (ajouter `abort` à l'import flask du fichier si absent.)
- [ ] `dashboard.html` : après la section pastilles, panneau admin :

```html
{% if role == 'admin' %}
<section class="panel">
  <h2>Contrôle du kiosque</h2>
  <div class="actions">
    <form method="post" class="inline" action="{{ url_for('dashboard.action_systeme', action='redemarrer-kiosque') }}"
          onsubmit="return confirm('Redémarrer le kiosque ? (~10 s, coupe une éventuelle session en cours)');">
      <button type="submit" class="btn btn--primary">Redémarrer le kiosque</button>
    </form>
    <form method="post" class="inline" action="{{ url_for('dashboard.action_systeme', action='arreter-kiosque') }}"
          onsubmit="return confirm('Arrêter le kiosque ? (relançable via Redémarrer)');">
      <button type="submit" class="btn">Arrêter le kiosque</button>
    </form>
    <form method="post" class="inline" action="{{ url_for('dashboard.action_systeme', action='redemarrer-machine') }}"
          onsubmit="return confirm('Redémarrer TOUTE la machine ?') && confirm('Vraiment ? ~1 minute d\'indisponibilité totale.');">
      <button type="submit" class="btn btn--danger">Redémarrer la machine</button>
    </form>
  </div>
  <p class="muted">Nécessite le kiosque en service systemd (deploy/install.sh) et la règle sudoers (install-admin.sh).</p>
</section>
{% endif %}
```

- [ ] `pytest tests/test_web_systeme.py -q` PASS + suite complète + ruff →
  commit `feat(admin): panneau Contrôle du kiosque (restart/stop/reboot) + pastille état`.

### Task 4 : Sudoers étendu + docs

**Files:** Modify `deploy/install-admin.sh` (§4), `docs/ADMIN.md`.

- [ ] `install-admin.sh` — remplacer le printf du §4 par :

```bash
printf '%s ALL=(root) NOPASSWD: %s restart photobooth.service, %s stop photobooth.service, %s start photobooth.service, %s reboot\n' \
    "${TARGET_USER}" "${SYSTEMCTL_BIN}" "${SYSTEMCTL_BIN}" "${SYSTEMCTL_BIN}" "${SYSTEMCTL_BIN}" > "${SUDOERS_TMP}"
```

  (la validation `visudo -cf` + `install -m 440` existent déjà — inchangées).
- [ ] `bash -n deploy/install-admin.sh` (syntaxe OK).
- [ ] `docs/ADMIN.md` : section « Contrôle du kiosque » (3 boutons, prérequis
  service systemd + sudoers, pastille état, admin uniquement) + la procédure de
  migration autostart XFCE → systemd (les 4 étapes de la spec).
- [ ] Suite complète + ruff → commit `deploy+docs: sudoers étendu (stop/start/reboot) + migration systemd`.

## Auto-revue

- Spec couverte : module liste blanche (T1), mutualisation settings (T2 — la spec
  n'en parlait pas explicitement mais évite deux implémentations du même subprocess),
  routes+pastille+panneau+confirmations (T3), sudoers+visudo+docs+migration (T4).
  Fix @PROJET_DIR@ : **déjà présent sur main**, rien à faire. ✔
- Cohérence : `systeme.executer_action`/`etat_kiosque`/`ACTIONS` mêmes noms partout ;
  actions kebab-case identiques routes/UI/tests. ✔ Pas de placeholder. ✔
