# Assets kiosque (volet 2) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Page admin « Kiosque » (fond d'accueil, police, slides perso) + corbeille galerie, avec mécanique « actif + fallback » sans écraser les fichiers versionnés.

**Architecture:** Nouvelle table `asset_kiosque` + Blueprint `/kiosque` (pattern templates_route). `config.py` gagne `resoudre_actif()` + chemins actifs/bibliothèques ; le kiosque consomme `BG_ACCUEIL_EFFECTIF`/`POLICE_EFFECTIVE` et un dossier slideshow de plus. La galerie déplace vers `data/corbeille/<mode>/` (restaurable), jamais de suppression définitive.

**Tech Stack:** Flask + Jinja2, SQLite, PIL (validation .ttf + miniature police), pytest.

**Spec :** `docs/superpowers/specs/2026-07-14-assets-kiosque-design.md` · **Branche :** `assets-kiosque`

---

### Task 1 : Config — chemins + `resoudre_actif()` (+ docs/CONFIG.md)

**Files:** Modify `config.py` (après POLICE_FICHIER, ~l.151) ; Create `test_config_assets.py` ; Modify `docs/CONFIG.md`.

- [ ] Test (`test_config_assets.py`) :

```python
"""test_config_assets.py — résolution actif/défaut des assets kiosque (volet 2)."""
import config


class TestResoudreActif:
    def test_prefere_actif_si_present(self, tmp_path):
        actif = tmp_path / "actif.jpg"
        actif.write_bytes(b"x")
        assert config.resoudre_actif(str(actif), "/defaut.jpg") == str(actif)

    def test_fallback_si_actif_absent(self, tmp_path):
        absent = str(tmp_path / "absent.jpg")
        assert config.resoudre_actif(absent, "/defaut.jpg") == "/defaut.jpg"


class TestConstantesVolet2:
    def test_constantes_presentes(self):
        for nom in ("FILE_BG_ACCUEIL_ACTIF", "POLICE_FICHIER_ACTIF", "PATH_SLIDESHOW_PERSO",
                    "PATH_CORBEILLE", "PATH_ACCUEIL_BIBLIO", "PATH_FONTS_BIBLIO",
                    "BG_ACCUEIL_EFFECTIF", "POLICE_EFFECTIVE"):
            assert hasattr(config, nom), nom
```

- [ ] Vérifier l'échec (`pytest test_config_assets.py -q` → AttributeError), puis implémenter dans `config.py` après `POLICE_FICHIER` :

```python
# --- Volet 2 : assets kiosque gérés par l'admin web (fond accueil, police, slides) ---
def resoudre_actif(chemin_actif, chemin_defaut):
    """Préfère le fichier activé par l'admin web s'il existe, sinon le défaut.
    Évalué à l'import : le kiosque charge ses assets au boot."""
    return chemin_actif if os.path.exists(chemin_actif) else chemin_defaut


FILE_BG_ACCUEIL_ACTIF = os.path.join(PATH_INTERFACE, "accueil_actif.jpg")
POLICE_FICHIER_ACTIF  = os.path.join(BASE_DIR, "assets/fonts/police_active.ttf")
PATH_ACCUEIL_BIBLIO   = os.path.join(PATH_INTERFACE, "accueil")
PATH_FONTS_BIBLIO     = os.path.join(BASE_DIR, "assets/fonts/bibliotheque")
PATH_SLIDESHOW_PERSO  = os.path.join(PATH_ASSETS, "slideshow")
PATH_CORBEILLE        = os.path.join(PATH_DATA, "corbeille")

BG_ACCUEIL_EFFECTIF = resoudre_actif(FILE_BG_ACCUEIL_ACTIF, FILE_BG_ACCUEIL)
POLICE_EFFECTIVE    = resoudre_actif(POLICE_FICHIER_ACTIF, POLICE_FICHIER)
```

- [ ] `docs/CONFIG.md` : documenter les 8 noms (section « Assets kiosque (admin web) »).
- [ ] `pytest test_config_assets.py -q` PASS → commit `feat(config): chemins assets kiosque + resoudre_actif (volet 2)`.

### Task 2 : DB — table `asset_kiosque`

**Files:** Modify `web/db.py` ; Create `test_web_kiosque.py`.

- [ ] Test initial (`test_web_kiosque.py`) :

```python
"""test_web_kiosque.py — page Kiosque (fond accueil, police, slides)."""
from __future__ import annotations

import base64
import io
import os

import pytest
from PIL import Image

from web.app import create_app

HEADERS = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}


class TestTableAssetKiosque:
    def test_table_creee(self, tmp_path):
        import sqlite3
        from web.db import init_db
        db = str(tmp_path / "admin.db")
        init_db(path=db)
        conn = sqlite3.connect(db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "asset_kiosque" in tables
```

- [ ] Échec attendu, puis ajouter à `_SCHEMA` (web/db.py) :

```sql
CREATE TABLE IF NOT EXISTS asset_kiosque (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    categorie TEXT NOT NULL,
    fichier TEXT NOT NULL UNIQUE,
    actif INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    taille_octets INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_asset_kiosque_cat_actif ON asset_kiosque (categorie, actif);
```

(+ docstring : catégories 'accueil'|'police'|'slide', un actif max par catégorie, actif sans objet pour slide.)
- [ ] PASS → commit `feat(admin): table asset_kiosque`.

### Task 3 : Blueprint `/kiosque` + page + nav

**Files:** Create `web/routes/kiosque_route.py`, `web/templates/kiosque.html` ; Modify `web/app.py`, `web/templates/base.html` ; Test `test_web_kiosque.py`.

- [ ] Fixture + tests (ajout à `test_web_kiosque.py`) :

```python
def _png_bytes(taille=(60, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", taille, (10, 120, 220)).save(buf, format="PNG")
    return buf.getvalue()


def _ttf_bytes() -> bytes:
    # La police par défaut du repo sert de .ttf valide pour les tests.
    with open("assets/fonts/WesternBangBang-Regular.ttf", "rb") as f:
        return f.read()


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    accueil_bib = tmp_path / "accueil"
    fonts_bib = tmp_path / "fonts"
    slides = tmp_path / "slides"
    for d in (accueil_bib, fonts_bib, slides):
        d.mkdir()
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    import web.db
    import web.routes.kiosque_route as kr
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(kr, "_RACINE_PAR_CATEGORIE", {
        "accueil": str(accueil_bib), "police": str(fonts_bib), "slide": str(slides),
    })
    monkeypatch.setattr(kr, "_CIBLE_ACTIVE", {
        "accueil": str(tmp_path / "accueil_actif.jpg"),
        "police": str(tmp_path / "police_active.ttf"),
    })

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), str(tmp_path)


def _uploader(c, nom, categorie, contenu, nom_fichier):
    c.post("/kiosque/upload", data={
        "nom": nom, "categorie": categorie,
        "fichier": (io.BytesIO(contenu), nom_fichier),
    }, headers=HEADERS, content_type="multipart/form-data", follow_redirects=True)
    import sqlite3
    import web.db
    conn = sqlite3.connect(web.db.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM asset_kiosque WHERE nom = ?", (nom,)).fetchone()
    conn.close()
    return row["id"] if row else None


class TestUploadKiosque:
    def test_upload_fond_accueil(self, client):
        c, base = client
        tid = _uploader(c, "Plage", "accueil", _png_bytes(), "plage.png")
        assert tid is not None

    def test_upload_police_valide(self, client):
        c, base = client
        tid = _uploader(c, "Western", "police", _ttf_bytes(), "western.ttf")
        assert tid is not None

    def test_upload_police_corrompue_refusee(self, client):
        c, base = client
        tid = _uploader(c, "Fausse", "police", b"pas une fonte", "fake.ttf")
        assert tid is None

    def test_upload_slide(self, client):
        c, base = client
        tid = _uploader(c, "Annonce", "slide", _png_bytes(), "annonce.png")
        assert tid is not None

    def test_categorie_inconnue_refusee(self, client):
        c, base = client
        assert _uploader(c, "X", "autre", _png_bytes(), "x.png") is None


class TestActivationKiosque:
    def test_activer_accueil_copie_cible(self, client):
        c, base = client
        tid = _uploader(c, "Plage", "accueil", _png_bytes(), "plage.png")
        r = c.post(f"/kiosque/activer/{tid}", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert os.path.isfile(os.path.join(base, "accueil_actif.jpg"))

    def test_activer_police_copie_cible(self, client):
        c, base = client
        tid = _uploader(c, "Western", "police", _ttf_bytes(), "w.ttf")
        c.post(f"/kiosque/activer/{tid}", headers=HEADERS, follow_redirects=True)
        assert os.path.isfile(os.path.join(base, "police_active.ttf"))

    def test_activer_slide_400(self, client):
        c, base = client
        tid = _uploader(c, "Annonce", "slide", _png_bytes(), "a.png")
        r = c.post(f"/kiosque/activer/{tid}", headers=HEADERS)
        assert r.status_code == 400


class TestDefautKiosque:
    def test_defaut_supprime_cible(self, client):
        c, base = client
        tid = _uploader(c, "Plage", "accueil", _png_bytes(), "plage.png")
        c.post(f"/kiosque/activer/{tid}", headers=HEADERS, follow_redirects=True)
        r = c.post("/kiosque/defaut/accueil", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert not os.path.exists(os.path.join(base, "accueil_actif.jpg"))

    def test_defaut_idempotent(self, client):
        c, base = client
        r = c.post("/kiosque/defaut/police", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200

    def test_defaut_slide_404(self, client):
        c, base = client
        assert c.post("/kiosque/defaut/slide", headers=HEADERS).status_code == 404


class TestPageEtThumb:
    def test_page_trois_sections(self, client):
        c, base = client
        r = c.get("/kiosque/", headers=HEADERS)
        html = r.get_data(as_text=True)
        for txt in ("Fond d'accueil", "Police", "Slides"):
            assert txt in html

    def test_thumb_police_rendue(self, client):
        c, base = client
        tid = _uploader(c, "Western", "police", _ttf_bytes(), "w.ttf")
        r = c.get(f"/kiosque/thumb/{tid}", headers=HEADERS)
        assert r.status_code == 200
        assert r.mimetype == "image/png"

    def test_supprimer_actif_refuse(self, client):
        c, base = client
        tid = _uploader(c, "Plage", "accueil", _png_bytes(), "p.png")
        c.post(f"/kiosque/activer/{tid}", headers=HEADERS, follow_redirects=True)
        c.post(f"/kiosque/supprimer/{tid}", headers=HEADERS, follow_redirects=True)
        import sqlite3
        import web.db
        conn = sqlite3.connect(web.db.DB_PATH)
        n = conn.execute("SELECT COUNT(*) FROM asset_kiosque").fetchone()[0]
        conn.close()
        assert n == 1  # toujours là
```

- [ ] Échec attendu, puis créer `web/routes/kiosque_route.py` (calqué sur templates_route) :
  constantes `CATEGORIES = ("accueil", "police", "slide")`,
  `EXTENSIONS_PAR_CATEGORIE = {"accueil": (".png",".jpg",".jpeg"), "police": (".ttf",".otf"), "slide": (".png",".jpg",".jpeg")}`,
  `_CIBLE_ACTIVE = {"accueil": FILE_BG_ACCUEIL_ACTIF, "police": POLICE_FICHIER_ACTIF}`,
  `_RACINE_PAR_CATEGORIE = {"accueil": PATH_ACCUEIL_BIBLIO, "police": PATH_FONTS_BIBLIO, "slide": PATH_SLIDESHOW_PERSO}`.
  Validation upload : images → `Image.verify()` ; police → `ImageFont.truetype(io.BytesIO(contenu), 24)`.
  Préfixe fichier : `f"{categorie}__{nom_sain}"`. Routes : index, upload, activer (400 si slide),
  defaut/<categorie> (404 si inconnue ou slide), supprimer (refus si actif), thumb (image →
  thumbnail ; police → rendu PIL « Aa Bb 123 » 240×80 RGBA).
- [ ] `web/app.py` : `from web.routes import ... kiosque_route` + `app.register_blueprint(kiosque_route.bp)`.
  `base.html` : lien nav `<a href="{{ url_for('kiosque.index') }}">Kiosque</a>` avant Réglages.
  `kiosque.html` : 3 sections (état Actif/Défaut + bouton « Défaut » pour accueil/police ;
  liste avec Activer/Supprimer ; note slides « pris en compte ≤ 30 s, sans redémarrage »).
- [ ] PASS + suite complète → commit `feat(admin): page Kiosque (fond accueil, police, slides perso)`.

### Task 4 : Galerie — retirer / corbeille / restaurer

**Files:** Modify `web/routes/gallery.py`, `web/templates/gallery.html` ; Test `test_web_gallery.py`.

- [ ] Tests (fin de `test_web_gallery.py`, réutiliser sa fixture existante — vérifier son nom
  et adapter : elle doit monkeypatcher aussi `gallery.PATH_CORBEILLE` vers tmp) :

```python
class TestCorbeille:
    def test_retirer_deplace_en_corbeille(self, client_avec_images):
        c, dossiers = client_avec_images  # adapter au retour réel de la fixture
        # image existante listée par la fixture, ex. "m1.jpg" en mode 10x15
        r = c.post("/galerie/retirer/10x15/m1.jpg", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert not os.path.exists(os.path.join(dossiers["10x15"], "m1.jpg"))
        assert os.path.exists(os.path.join(dossiers["corbeille"], "10x15", "m1.jpg"))

    def test_restaurer_ramene_le_fichier(self, client_avec_images):
        c, dossiers = client_avec_images
        c.post("/galerie/retirer/10x15/m1.jpg", headers=HEADERS, follow_redirects=True)
        r = c.post("/galerie/restaurer/10x15/m1.jpg", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert os.path.exists(os.path.join(dossiers["10x15"], "m1.jpg"))

    def test_retirer_fichier_inexistant_404(self, client_avec_images):
        c, dossiers = client_avec_images
        assert c.post("/galerie/retirer/10x15/absent.jpg", headers=HEADERS).status_code == 404

    def test_retirer_traversee_bloquee(self, client_avec_images):
        c, dossiers = client_avec_images
        r = c.post("/galerie/retirer/10x15/..%2F..%2Fetc%2Fpasswd", headers=HEADERS)
        assert r.status_code == 404
```

- [ ] Échec attendu, puis dans `gallery.py` : import `PATH_CORBEILLE`, helpers
  `_chemin_corbeille(mode, nom)` (même garde realpath, racine `PATH_CORBEILLE/<mode>`),
  routes POST `retirer/<mode>/<nom>` (`os.makedirs` + `os.replace` → corbeille, flash) et
  `restaurer/<mode>/<nom>` (inverse), `_lister_corbeille()` ; `index()` passe `corbeille=...`.
  `gallery.html` : bouton « Retirer » (confirm) par item + section « Corbeille » avec « Restaurer ».
- [ ] PASS + suite → commit `feat(admin): corbeille galerie (retirer/restaurer, jamais de suppression)`.

### Task 5 : Branchement kiosque

**Files:** Modify `Photobooth_start.py`, `ui/helpers.py`.

- [ ] `Photobooth_start.py` : dans l'import config, ajouter `BG_ACCUEIL_EFFECTIF`,
  `PATH_SLIDESHOW_PERSO`, `POLICE_EFFECTIVE` ; remplacer l'usage de `FILE_BG_ACCUEIL`
  (AccueilAssets.charger) par `BG_ACCUEIL_EFFECTIF` ; `_charger_polices()` utilise
  `POLICE_EFFECTIVE` (les 6 `pygame.font.Font`) ; l'appel `lister_images_slideshow`
  reçoit `[PATH_PRINT_10X15, PATH_PRINT_STRIP, PATH_SLIDESHOW_PERSO]`.
- [ ] `ui/helpers.py` : `config.POLICE_FICHIER` → `config.POLICE_EFFECTIVE` (2 fonts impression).
  (`core/montage.py` garde POLICE_FICHIER pour le watermark imprimé — hors périmètre.)
- [ ] `python3 -m py_compile Photobooth_start.py ui/helpers.py` + suite complète + ruff
  → commit `feat(kiosque): consomme les assets actifs (fond accueil, police, slides perso)`.

### Task 6 : Docs + vérification finale

- [ ] `docs/ADMIN.md` : puce « Kiosque » + corbeille galerie + tableau source de vérité
  (fond actif, police active, slides, corbeille).
- [ ] `pytest -q` + `ruff check .` + couverture ≥ 75 % + smoke serveur réel
  (page /kiosque/ dans le navigateur, clair + sombre) → commit `docs: ADMIN.md — page Kiosque + corbeille`.

## Auto-revue

- Spec couverte : config (T1), DB (T2), routes+UI (T3), galerie (T4), kiosque (T5), docs (T6),
  erreurs (fonte corrompue T3, idempotence défaut T3, 404 corbeille T4, traversées T3/T4). ✔
- Cohérence : `_CIBLE_ACTIVE`/`_RACINE_PAR_CATEGORIE` mêmes noms fixture/module ; retour fixture
  kiosque = `(client, base_tmp)`. Galerie : adapter les tests au nom réel de la fixture existante. ✔
