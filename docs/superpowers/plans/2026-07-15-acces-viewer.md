# Accès viewer sans mot de passe — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deux niveaux d'accès — admin (Basic Auth, inchangé) et viewer anonyme en consultation seule (dashboard + galerie), avec interrupteur `PHOTOBOOTH_ACCES_LIBRE`.

**Architecture:** `web/auth.py` gagne `role_courant()` + `require_lecture` (admin OU anonyme si accès libre). Les GET de consultation passent sous `require_lecture` (dashboard `/`, `/heure`, galerie `/`, `image`, `thumb`) ; tout le reste reste `require_auth`. Un context processor injecte `role` dans les gabarits pour masquer nav/actions ; route `/connexion` sous `require_auth` pour déclencher le challenge navigateur.

**Tech Stack:** Flask, Basic Auth, pytest.

**Spec :** `docs/superpowers/specs/2026-07-15-acces-viewer-design.md` · **Branche :** `acces-viewer`

---

### Task 1 : `web/auth.py` — rôles + `require_lecture`

**Files:** Modify `web/auth.py` ; Create `tests/test_web_auth_viewer.py`.

- [ ] Tests (`tests/test_web_auth_viewer.py`) :

```python
"""test_web_auth_viewer.py — mode consultation anonyme (viewer) vs admin."""
from __future__ import annotations

import base64
import os

import pytest
from PIL import Image

from web.app import create_app

HEADERS_OK = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}
HEADERS_KO = {"Authorization": "Basic " + base64.b64encode(b"admin:faux").decode()}


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    d10 = data / "print" / "print_10x15"
    dstrip = data / "print" / "print_strip"
    d10.mkdir(parents=True)
    dstrip.mkdir(parents=True)
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    monkeypatch.setattr(config, "PATH_PRINT", str(data / "print"))
    monkeypatch.setattr(config, "PATH_PRINT_10X15", str(d10))
    monkeypatch.setattr(config, "PATH_PRINT_STRIP", str(dstrip))
    import web.db
    import web.routes.gallery as g
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(g, "_RACINES_AUTORISEES", {"10x15": str(d10), "strip": str(dstrip)})
    monkeypatch.setattr(g, "PATH_CORBEILLE", str(data / "corbeille"))
    Image.new("RGB", (40, 40), (200, 30, 30)).save(str(d10 / "m1.jpg"), format="JPEG")

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


class TestViewerConsultation:
    def test_dashboard_accessible_sans_auth(self, client):
        r = client.get("/dashboard/")
        assert r.status_code == 200

    def test_heure_accessible_sans_auth(self, client):
        assert client.get("/dashboard/heure").status_code == 200

    def test_galerie_et_images_accessibles_sans_auth(self, client):
        assert client.get("/galerie/").status_code == 200
        assert client.get("/galerie/image/10x15/m1.jpg").status_code == 200
        assert client.get("/galerie/thumb/10x15/m1.jpg").status_code == 200

    def test_html_viewer_sans_actions_ni_chemins(self, client):
        dash = client.get("/dashboard/").get_data(as_text=True)
        assert "Réglages" not in dash
        assert "Journal :" not in dash
        assert "debloquer" not in dash
        galerie = client.get("/galerie/").get_data(as_text=True)
        assert "Retirer" not in galerie
        assert "Corbeille" not in galerie
        assert "Connexion admin" in dash


class TestViewerBloque:
    def test_post_retirer_401(self, client):
        assert client.post("/galerie/retirer/10x15/m1.jpg").status_code == 401

    def test_pages_gestion_401(self, client):
        for url in ("/templates/", "/kiosque/", "/settings/", "/evenements/"):
            assert client.get(url).status_code == 401, url

    def test_debloquer_quota_401(self, client):
        assert client.post("/dashboard/quota/debloquer").status_code == 401

    def test_mauvais_mdp_401(self, client):
        assert client.get("/dashboard/", headers=HEADERS_KO).status_code == 401


class TestInterrupteurEtFailClosed:
    def test_acces_libre_coupe_401(self, client, monkeypatch):
        monkeypatch.setenv("PHOTOBOOTH_ACCES_LIBRE", "0")
        assert client.get("/dashboard/").status_code == 401
        assert client.get("/dashboard/", headers=HEADERS_OK).status_code == 200

    def test_sans_mdp_admin_503_partout(self, client, monkeypatch):
        monkeypatch.delenv("PHOTOBOOTH_ADMIN_PASS", raising=False)
        assert client.get("/dashboard/").status_code == 503


class TestAdmin:
    def test_admin_voit_tout(self, client):
        dash = client.get("/dashboard/", headers=HEADERS_OK).get_data(as_text=True)
        assert "Réglages" in dash
        galerie = client.get("/galerie/", headers=HEADERS_OK).get_data(as_text=True)
        assert "Retirer" in galerie

    def test_connexion_declenche_challenge_puis_redirige(self, client):
        assert client.get("/connexion").status_code == 401
        r = client.get("/connexion", headers=HEADERS_OK)
        assert r.status_code == 302
```

- [ ] Échec attendu (routes viewer → 401 aujourd'hui), puis implémenter dans `web/auth.py`
  (après `_mot_de_passe_attendu`) :

```python
ENV_ACCES_LIBRE = "PHOTOBOOTH_ACCES_LIBRE"


def _acces_libre_actif() -> bool:
    """Mode consultation anonyme activé (défaut oui ; '0' pour le couper)."""
    return os.environ.get(ENV_ACCES_LIBRE, "1") != "0"


def role_courant() -> str | None:
    """'admin' si Basic Auth valide, 'viewer' si anonyme autorisé, None sinon.

    None couvre : pas de mot de passe admin configuré (fail closed), créds
    invalides, ou anonyme alors que l'accès libre est coupé.
    """
    attendu = _mot_de_passe_attendu()
    if not attendu:
        return None
    auth = request.authorization
    if auth is not None:
        if auth.username == ADMIN_USER and hmac.compare_digest(auth.password or "", attendu):
            return "admin"
        return None
    return "viewer" if _acces_libre_actif() else None


def require_lecture(f):
    """Décorateur consultation : admin OU viewer anonyme (si accès libre)."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _mot_de_passe_attendu():
            return Response(
                "Admin désactivé : variable d'environnement "
                f"{ENV_VAR} non configurée.",
                status=503,
            )
        if role_courant() is None:
            return _unauthorized()
        return f(*args, **kwargs)

    return wrapper
```

  et mettre à jour le docstring de module (deux niveaux, interrupteur).
- [ ] Task 2 requise pour que les tests passent — pas de run isolé ici, commit groupé en Task 2.

### Task 2 : Routes + context processor + `/connexion`

**Files:** Modify `web/routes/dashboard.py` (routes `/` et `/heure`), `web/routes/gallery.py`
(routes `/`, `image`, `thumb`), `web/app.py`.

- [ ] `dashboard.py` : importer `require_lecture` ; `@require_auth` → `@require_lecture` sur
  `heure_serveur` et `index` uniquement (`debloquer_quota` reste `require_auth`).
- [ ] `gallery.py` : idem sur `index`, `image`, `thumb` (retirer/restaurer restent admin).
- [ ] `web/app.py` dans `create_app`, après les blueprints :

```python
    from flask import redirect as _redirect, url_for as _url_for

    from web.auth import require_auth, role_courant

    @app.context_processor
    def _injecter_role():
        return {"role": role_courant()}

    @app.route("/connexion")
    @require_auth
    def connexion():
        # Sous require_auth : un anonyme reçoit le challenge Basic du navigateur,
        # puis atterrit sur le dashboard en admin.
        return _redirect(_url_for("dashboard.index"))
```

  (adapter les imports si `redirect`/`url_for` sont déjà importés en tête — ils le sont : utiliser
  directement `redirect(url_for(...))`.)
- [ ] Run: `pytest tests/test_web_auth_viewer.py -q` → seuls les tests de masquage HTML
  (`test_html_viewer_sans_actions_ni_chemins`) échouent encore. Les autres PASS.

### Task 3 : Masquage dans les gabarits

**Files:** Modify `web/templates/base.html`, `web/templates/dashboard.html`, `web/templates/gallery.html`.

- [ ] `base.html` — nav conditionnelle :

```html
    <nav class="nav">
      <a href="{{ url_for('dashboard.index') }}">Dashboard</a>
      <a href="{{ url_for('gallery.index') }}">Galerie</a>
      {% if role == 'admin' %}
        <a href="{{ url_for('evenements.index') }}">Événements</a>
        <a href="{{ url_for('templates.index') }}">Templates</a>
        <a href="{{ url_for('kiosque.index') }}">Kiosque</a>
        <a href="{{ url_for('settings.index') }}">Réglages</a>
      {% else %}
        <a href="{{ url_for('connexion') }}">Connexion admin</a>
      {% endif %}
    </nav>
```

- [ ] `dashboard.html` : entourer le formulaire `dashboard.debloquer_quota` (~l.122) et le
  paragraphe `Journal : …` (~l.163) de `{% if role == 'admin' %} … {% endif %}` (lire le
  contexte exact avant d'éditer — le fichier a bougé récemment).
- [ ] `gallery.html` : entourer le formulaire « Retirer » et la section « Corbeille » de
  `{% if role == 'admin' %} … {% endif %}`.
- [ ] Run: `pytest tests/test_web_auth_viewer.py -q` PASS, puis suite complète + ruff.
- [ ] Commit : `feat(admin): accès consultation sans mot de passe (viewer) + rôle admin`

### Task 4 : Env, docs, vérification finale

**Files:** Modify `deploy/install-admin.sh`, `docs/ADMIN.md`.

- [ ] `install-admin.sh` — dans le heredoc du fichier env généré, ajouter :

```bash
# Mode consultation anonyme (dashboard + galerie en lecture seule pour le LAN).
# Mettre 0 pour exiger le mot de passe partout (événement privé).
PHOTOBOOTH_ACCES_LIBRE=1
```

- [ ] `docs/ADMIN.md` : section « Accès » — deux niveaux, interrupteur, mise en garde
  vie privée (galerie visible de tout le wifi quand l'accès libre est actif), limite
  de déconnexion Basic Auth (fermer le navigateur).
- [ ] `pytest -q` + `ruff check .` + smoke navigateur : page dashboard SANS auth
  (nav réduite + « Connexion admin »), puis AVEC auth (nav complète).
- [ ] Commit : `docs+deploy: accès viewer (interrupteur PHOTOBOOTH_ACCES_LIBRE)`

## Auto-revue

- Spec couverte : rôles/décorateur (T1), routes+context processor+connexion (T2), masquage
  nav/actions/chemins (T3), interrupteur+docs+install (T4), fail-closed (T1 test 503),
  mauvais mdp → 401 (T1). ✔ Types cohérents (`role_courant()` → 'admin'|'viewer'|None partout). ✔
- Pas de placeholder : le seul « lire le contexte exact avant d'éditer » est une consigne de
  sécurité d'édition, le contenu à insérer est spécifié. ✔
