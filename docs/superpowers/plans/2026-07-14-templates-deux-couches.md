# Bibliothèque templates deux couches — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La page Templates de l'admin web gère les deux couches (overlay + fond) par format, avec bibliothèque d'upload et état « Aucun » par couche×format.

**Architecture:** Généralisation du système existant : la table `template` gagne une colonne `couche` (migration idempotente), les routes résolvent la cible active par couple (couche, type) parmi les 4 fichiers fixes lus par le kiosque, et une nouvelle route `desactiver` supprime le fichier actif (le moteur de montage gère nativement l'absence : fond → blanc, overlay → sauté). Aucun changement côté kiosque.

**Tech Stack:** Flask + Jinja2, SQLite (`data/admin.db`), PIL, pytest (tests dans `tests/`, convention projet).

**Spec :** `docs/superpowers/specs/2026-07-14-sans-template-design.md`
**Branche :** `templates-deux-couches`

---

## Structure des fichiers

| Fichier | Rôle dans ce plan |
|---|---|
| `web/db.py` | Colonne `couche` dans `_SCHEMA` + fonction `_migrer()` + index (couche, type, actif) |
| `web/routes/templates_route.py` | Constantes deux couches, résolution chemin par couche, upload/activer/desactiver/supprimer/thumb couche-aware |
| `web/templates/templates.html` | Deux sections (Overlays / Fonds), formulaire avec choix de couche, boutons « Aucun » avec état |
| `tests/test_web_templates.py` | Fixture couche-aware + nouveaux tests (migration, fond, désactivation) |
| `docs/ADMIN.md` | Page Templates deux couches + tableau source de vérité |

Rappels projet : tests dans **`tests/`** (`testpaths = ["tests"]`), ruff propre obligatoire (CI), commits en français `<domaine>: <description>`, chaque commit doit passer les tests.

---

### Task 1 : Migration DB — colonne `couche`

**Files:**
- Modify: `web/db.py`
- Test: `test_web_templates.py` (nouvelle classe en fin de fichier)

- [ ] **Step 1 : Écrire le test de migration (échec attendu)**

Ajouter en fin de `test_web_templates.py` :

```python
class TestMigrationCouche:
    """La colonne `couche` doit être ajoutée aux bases créées avant son introduction."""

    def _creer_ancienne_base(self, chemin: str) -> None:
        import sqlite3
        conn = sqlite3.connect(chemin)
        conn.execute("""CREATE TABLE template (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('10x15', 'strip')),
            fichier TEXT NOT NULL UNIQUE,
            actif INTEGER NOT NULL DEFAULT 0,
            uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
            taille_octets INTEGER NOT NULL DEFAULT 0
        )""")
        conn.execute(
            "INSERT INTO template (nom, type, fichier) VALUES ('Mariage', '10x15', 'm.png')"
        )
        conn.commit()
        conn.close()

    def test_ancienne_base_migree_en_overlay(self, tmp_path):
        import sqlite3
        db = str(tmp_path / "admin.db")
        self._creer_ancienne_base(db)

        from web.db import init_db
        init_db(path=db)  # ne doit pas lever, et ajouter la colonne

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT couche FROM template WHERE nom = 'Mariage'").fetchone()
        conn.close()
        assert row["couche"] == "overlay"

    def test_init_db_idempotent_sur_base_migree(self, tmp_path):
        db = str(tmp_path / "admin.db")
        self._creer_ancienne_base(db)
        from web.db import init_db
        init_db(path=db)
        init_db(path=db)  # 2e passage : ne doit pas lever

    def test_base_neuve_a_la_colonne(self, tmp_path):
        import sqlite3
        db = str(tmp_path / "neuve.db")
        from web.db import init_db
        init_db(path=db)
        conn = sqlite3.connect(db)
        colonnes = {r[1] for r in conn.execute("PRAGMA table_info(template)")}
        conn.close()
        assert "couche" in colonnes
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `pytest tests/test_web_templates.py::TestMigrationCouche -v`
Expected: FAIL (`no such column: couche` sur le premier test ; le 3e échoue aussi).

- [ ] **Step 3 : Implémenter dans `web/db.py`**

Remplacer le bloc `_SCHEMA` et `init_db` :

```python
_SCHEMA = """
CREATE TABLE IF NOT EXISTS template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('10x15', 'strip')),
    couche TEXT NOT NULL DEFAULT 'overlay',
    fichier TEXT NOT NULL UNIQUE,
    actif INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    taille_octets INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_template_type_actif ON template (type, actif);
"""
```

```python
def _migrer(conn: sqlite3.Connection) -> None:
    """Migrations idempotentes du schéma (bases créées avant l'ajout de colonnes).

    L'index sur `couche` est créé dans init_db APRÈS cette fonction : sur une
    base ancienne, la colonne doit exister avant l'index.
    """
    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(template)")}
    if "couche" not in colonnes:
        conn.execute(
            "ALTER TABLE template ADD COLUMN couche TEXT NOT NULL DEFAULT 'overlay'"
        )


def init_db(path: str = DB_PATH) -> None:
    """Crée la DB si absente, applique le schéma + migrations (idempotent)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _ouvrir(path) as conn:
        conn.executescript(_SCHEMA)
        _migrer(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_template_couche_type_actif "
            "ON template (couche, type, actif)"
        )
        conn.commit()
```

Mettre à jour le docstring de module (« Une seule table aujourd'hui ») pour mentionner la colonne `couche` (`'overlay'` | `'fond'`, un seul actif par couple couche×type).

- [ ] **Step 4 : Vérifier le succès**

Run: `pytest tests/test_web_templates.py -v`
Expected: PASS (les 3 nouveaux + tous les anciens — la colonne a un DEFAULT, rien ne casse).

- [ ] **Step 5 : Commit**

```bash
git add web/db.py tests/test_web_templates.py
git commit -m "feat(admin): colonne couche sur la table template + migration idempotente"
```

---

### Task 2 : Structures couche-aware dans la route (compat overlay par défaut)

**Files:**
- Modify: `web/routes/templates_route.py`
- Modify: `test_web_templates.py` (fixture `client`)

- [ ] **Step 1 : Adapter la fixture aux nouvelles structures**

Dans `test_web_templates.py`, remplacer la fixture `client` par :

```python
@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    fonds = tmp_path / "fonds"
    fonds.mkdir()
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    monkeypatch.setattr(config, "PATH_OVERLAYS", str(overlays))
    monkeypatch.setattr(config, "PATH_FONDS", str(fonds))
    monkeypatch.setattr(config, "OVERLAY_10X15", str(overlays / "10x15_overlay.png"))
    monkeypatch.setattr(config, "OVERLAY_STRIPS", str(overlays / "strips_overlay.png"))
    monkeypatch.setattr(config, "BG_10X15_FILE", str(fonds / "10x15_background.jpg"))
    monkeypatch.setattr(config, "BG_STRIPS_FILE", str(fonds / "strips_background.jpg"))
    import web.db
    import web.routes.templates_route as tr
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(tr, "_CIBLE_ACTIVE", {
        ("overlay", "10x15"): str(overlays / "10x15_overlay.png"),
        ("overlay", "strip"): str(overlays / "strips_overlay.png"),
        ("fond", "10x15"): str(fonds / "10x15_background.jpg"),
        ("fond", "strip"): str(fonds / "strips_background.jpg"),
    })
    monkeypatch.setattr(tr, "_RACINE_PAR_COUCHE", {
        "overlay": str(overlays),
        "fond": str(fonds),
    })
    monkeypatch.setattr(tr, "PATH_OVERLAYS", str(overlays))

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), str(overlays), str(fonds)
```

⚠️ La fixture retourne maintenant un triplet : mettre à jour **tous** les dépaquetages
existants `c, _ = client` → `c, _, _ = client` et `c, overlays = client` →
`c, overlays, _ = client` dans le fichier.

- [ ] **Step 2 : Vérifier l'échec**

Run: `pytest tests/test_web_templates.py -v`
Expected: FAIL — `AttributeError` sur `tr._RACINE_PAR_COUCHE` (n'existe pas encore).

- [ ] **Step 3 : Refactorer `web/routes/templates_route.py`**

Import config : remplacer la ligne existante par :

```python
from config import (
    BG_10X15_FILE,
    BG_STRIPS_FILE,
    OVERLAY_10X15,
    OVERLAY_STRIPS,
    PATH_FONDS,
    PATH_OVERLAYS,
)
```

Remplacer le bloc constantes (`TYPES_AUTORISES` → `_CIBLE_ACTIVE`) par :

```python
TYPES_AUTORISES = ("10x15", "strip")
COUCHES_AUTORISEES = ("overlay", "fond")
# L'overlay exige la transparence (PNG) ; le fond est une image pleine.
EXTENSIONS_PAR_COUCHE = {
    "overlay": (".png",),
    "fond": (".png", ".jpg", ".jpeg"),
}
THUMB_MAX = (240, 240)

# Cibles fixes lues par le kiosque à chaque montage, par (couche, type).
_CIBLE_ACTIVE = {
    ("overlay", "10x15"): OVERLAY_10X15,
    ("overlay", "strip"): OVERLAY_STRIPS,
    ("fond", "10x15"): BG_10X15_FILE,
    ("fond", "strip"): BG_STRIPS_FILE,
}

# Dossier bibliothèque par couche.
_RACINE_PAR_COUCHE = {
    "overlay": PATH_OVERLAYS,
    "fond": PATH_FONDS,
}
```

`TemplateRow` : ajouter le champ `couche: str` (après `type`).

`_chemin_fichier` : signature et racine par couche :

```python
def _chemin_fichier(fichier: str, couche: str) -> str:
    racine_couche = _RACINE_PAR_COUCHE.get(couche)
    if racine_couche is None:
        abort(404)
    chemin = os.path.realpath(os.path.join(racine_couche, fichier))
    racine = os.path.realpath(racine_couche)
    if not chemin.startswith(racine + os.sep):
        abort(404)
    return chemin
```

`_lister` : sélectionner et propager `couche` :

```python
def _lister() -> list[TemplateRow]:
    with connexion() as conn:
        rows = conn.execute(
            "SELECT id, nom, type, couche, fichier, actif, uploaded_at, taille_octets "
            "FROM template ORDER BY couche, type, uploaded_at DESC"
        ).fetchall()
    return [
        TemplateRow(
            id=r["id"], nom=r["nom"], type=r["type"], couche=r["couche"],
            fichier=r["fichier"], actif=bool(r["actif"]),
            uploaded_at=r["uploaded_at"], taille_ko=r["taille_octets"] // 1024,
        )
        for r in rows
    ]
```

`upload()` : lire la couche (défaut `overlay` = compat), extensions et dossier par couche,
préfixe `couche__type__` (évite la collision UNIQUE entre couches) :

```python
    couche = (request.form.get("couche") or "overlay").strip()
    if couche not in COUCHES_AUTORISEES:
        flash("Couche invalide.", "error")
        return redirect(url_for("templates.index"))
```

(placer ce bloc juste avant la vérification du type), puis remplacer la vérification
d'extension et la construction du chemin :

```python
    extensions = EXTENSIONS_PAR_COUCHE[couche]
    if not f.filename.lower().endswith(extensions):
        flash(f"Extension non autorisée : {', '.join(extensions)} uniquement.", "error")
        return redirect(url_for("templates.index"))

    racine = _RACINE_PAR_COUCHE[couche]
    os.makedirs(racine, exist_ok=True)
    nom_fichier = _safe_filename(f.filename)
    if not nom_fichier:
        flash("Nom de fichier invalide.", "error")
        return redirect(url_for("templates.index"))
    # Préfixe couche + type : évite les collisions entre modes ET entre couches
    # (la colonne `fichier` est UNIQUE globalement).
    nom_fichier = f"{couche}__{type_template}__{nom_fichier}"
    cible = os.path.join(racine, nom_fichier)
```

et l'INSERT :

```python
        conn.execute(
            "INSERT OR REPLACE INTO template (nom, type, couche, fichier, actif, taille_octets) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (nom_affiche or nom_fichier, type_template, couche, nom_fichier, taille),
        )
```

Le message flash d'erreur PIL devient : `"Fichier image non reconnu ou corrompu."`
(il couvre maintenant PNG et JPEG).

`activer()` : sélectionner `couche`, résoudre la cible par couple, reset limité au couple :

```python
        row = conn.execute(
            "SELECT type, couche, fichier, nom FROM template WHERE id = ?", (template_id,),
        ).fetchone()
        if row is None:
            abort(404)
        type_t = row["type"]
        couche = row["couche"]
        fichier = row["fichier"]
        source = _chemin_fichier(fichier, couche)
        if not os.path.isfile(source):
            flash("Fichier source introuvable sur disque.", "error")
            return redirect(url_for("templates.index"))

        cible_active = _CIBLE_ACTIVE.get((couche, type_t))
        if cible_active is None:
            abort(400)
        os.makedirs(os.path.dirname(cible_active), exist_ok=True)
        shutil.copyfile(source, cible_active)

        conn.execute(
            "UPDATE template SET actif = 0 WHERE couche = ? AND type = ?", (couche, type_t),
        )
        conn.execute("UPDATE template SET actif = 1 WHERE id = ?", (template_id,))
    flash(f"Template « {row['nom']} » activé ({couche} {type_t}).", "success")
```

`supprimer()` et `thumb()` : ajouter `couche` au SELECT et passer
`_chemin_fichier(row["fichier"], row["couche"])`.

`index()` : exposer l'état actif par couple + les listes pour le gabarit :

```python
@bp.route("/", methods=["GET"])
@require_auth
def index():
    templates = _lister()
    actifs = {(t.couche, t.type): t.nom for t in templates if t.actif}
    return render_template(
        "templates.html",
        templates=templates,
        actifs=actifs,
        couches=COUCHES_AUTORISEES,
        types=TYPES_AUTORISES,
        path_overlays=PATH_OVERLAYS,
        path_fonds=PATH_FONDS,
    )
```

Docstring de module : mentionner les deux couches et les 4 cibles.

- [ ] **Step 4 : Vérifier le succès**

Run: `pytest tests/test_web_templates.py tests/test_web_app.py -v`
Expected: PASS — les anciens tests passent (couche défaut `overlay`), la fixture triplet fonctionne.
Note : le gabarit HTML référence encore l'ancienne variable ? Non — `path_overlays` est
toujours passé ; la mise à jour du gabarit vient en Task 5. Si un test de rendu échoue sur
`actifs`/`couches` manquants, c'est que `index()` n'a pas été mis à jour.

- [ ] **Step 5 : Commit**

```bash
git add web/routes/templates_route.py tests/test_web_templates.py
git commit -m "refactor(admin): résolution des templates par couple (couche, type), défaut overlay"
```

---

### Task 3 : Upload de fonds

**Files:**
- Modify: `test_web_templates.py`
- (l'implémentation est déjà en place depuis Task 2 — cette tâche la prouve)

- [ ] **Step 1 : Écrire les tests fond (échec = garde-fou)**

Ajouter en fin de `test_web_templates.py` un helper JPEG près de `_png_bytes` :

```python
def _jpg_bytes(taille=(100, 100), couleur=(0, 128, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", taille, couleur).save(buf, format="JPEG")
    return buf.getvalue()
```

puis la classe :

```python
class TestUploadFond:
    def test_upload_fond_jpg_dans_dossier_fonds(self, client):
        c, _, fonds = client
        data = {
            "nom": "Fond mariage",
            "type": "10x15",
            "couche": "fond",
            "fichier": (io.BytesIO(_jpg_bytes()), "fond.jpg"),
        }
        r = c.post("/templates/upload", data=data,
                   headers=HEADERS, content_type="multipart/form-data",
                   follow_redirects=True)
        assert r.status_code == 200
        assert os.path.isfile(os.path.join(fonds, "fond__10x15__fond.jpg"))

    def test_upload_fond_png_accepte(self, client):
        c, _, fonds = client
        data = {
            "nom": "Fond png",
            "type": "strip",
            "couche": "fond",
            "fichier": (io.BytesIO(_png_bytes()), "fond.png"),
        }
        r = c.post("/templates/upload", data=data,
                   headers=HEADERS, content_type="multipart/form-data",
                   follow_redirects=True)
        assert r.status_code == 200
        assert os.path.isfile(os.path.join(fonds, "fond__strip__fond.png"))

    def test_upload_overlay_jpg_refuse(self, client):
        c, overlays, _ = client
        data = {
            "nom": "Mauvais overlay",
            "type": "10x15",
            "couche": "overlay",
            "fichier": (io.BytesIO(_jpg_bytes()), "cadre.jpg"),
        }
        c.post("/templates/upload", data=data,
               headers=HEADERS, content_type="multipart/form-data",
               follow_redirects=True)
        assert not os.path.isfile(os.path.join(overlays, "overlay__10x15__cadre.jpg"))

    def test_upload_couche_inconnue_refuse(self, client):
        c, overlays, fonds = client
        data = {
            "nom": "X",
            "type": "10x15",
            "couche": "cadre",
            "fichier": (io.BytesIO(_png_bytes()), "x.png"),
        }
        c.post("/templates/upload", data=data,
               headers=HEADERS, content_type="multipart/form-data",
               follow_redirects=True)
        assert os.listdir(overlays) == [] and os.listdir(fonds) == []
```

- [ ] **Step 2 : Lancer les tests**

Run: `pytest tests/test_web_templates.py::TestUploadFond -v`
Expected: PASS directement (l'implémentation date de Task 2). Si un test échoue,
corriger `upload()` — ne pas modifier le test.

- [ ] **Step 3 : Commit**

```bash
git add tests/test_web_templates.py
git commit -m "tests(admin): upload de fonds (jpg/png), rejets extension et couche inconnue"
```

---

### Task 4 : Activation de fonds + route de désactivation « Aucun »

**Files:**
- Modify: `web/routes/templates_route.py` (nouvelle route `desactiver`)
- Modify: `test_web_templates.py`

- [ ] **Step 1 : Écrire les tests (échec attendu sur la désactivation)**

Ajouter en fin de `test_web_templates.py` :

```python
def _uploader(c, nom, type_t, couche, contenu, nom_fichier):
    """Helper : upload + retourne l'id du template créé."""
    c.post("/templates/upload", data={
        "nom": nom, "type": type_t, "couche": couche,
        "fichier": (io.BytesIO(contenu), nom_fichier),
    }, headers=HEADERS, content_type="multipart/form-data", follow_redirects=True)
    import sqlite3
    import web.db
    conn = sqlite3.connect(web.db.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM template WHERE nom = ?", (nom,)).fetchone()
    conn.close()
    return row["id"]


class TestActivationFond:
    def test_activer_fond_copie_vers_cible_bg(self, client):
        c, _, fonds = client
        tid = _uploader(c, "FondM", "10x15", "fond", _jpg_bytes(), "f.jpg")
        r = c.post(f"/templates/activer/{tid}", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert os.path.isfile(os.path.join(fonds, "10x15_background.jpg"))

    def test_activation_independante_entre_couches(self, client):
        """Activer un fond 10x15 ne doit PAS désactiver l'overlay 10x15."""
        c, overlays, _ = client
        tid_ov = _uploader(c, "Cadre", "10x15", "overlay", _png_bytes(), "c.png")
        tid_fd = _uploader(c, "Fond", "10x15", "fond", _jpg_bytes(), "f.jpg")
        c.post(f"/templates/activer/{tid_ov}", headers=HEADERS, follow_redirects=True)
        c.post(f"/templates/activer/{tid_fd}", headers=HEADERS, follow_redirects=True)

        import sqlite3
        import web.db
        conn = sqlite3.connect(web.db.DB_PATH)
        actifs = conn.execute("SELECT COUNT(*) FROM template WHERE actif = 1").fetchone()[0]
        conn.close()
        assert actifs == 2  # un par couche


class TestDesactivation:
    def test_desactiver_supprime_cible_et_actif(self, client):
        c, overlays, _ = client
        tid = _uploader(c, "Cadre", "10x15", "overlay", _png_bytes(), "c.png")
        c.post(f"/templates/activer/{tid}", headers=HEADERS, follow_redirects=True)
        cible = os.path.join(overlays, "10x15_overlay.png")
        assert os.path.isfile(cible)

        r = c.post("/templates/desactiver/overlay/10x15",
                   headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert not os.path.exists(cible)

        import sqlite3
        import web.db
        conn = sqlite3.connect(web.db.DB_PATH)
        actifs = conn.execute("SELECT COUNT(*) FROM template WHERE actif = 1").fetchone()[0]
        conn.close()
        assert actifs == 0

    def test_desactiver_idempotent_si_deja_aucun(self, client):
        c, _, _ = client
        r = c.post("/templates/desactiver/fond/strip",
                   headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200  # no-op poli, pas d'erreur

    def test_desactiver_couche_inconnue_404(self, client):
        c, _, _ = client
        r = c.post("/templates/desactiver/cadre/10x15", headers=HEADERS)
        assert r.status_code == 404

    def test_desactiver_type_inconnu_404(self, client):
        c, _, _ = client
        r = c.post("/templates/desactiver/overlay/13x18", headers=HEADERS)
        assert r.status_code == 404
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `pytest tests/test_web_templates.py::TestDesactivation -v`
Expected: FAIL — 404 partout (la route n'existe pas) : les tests `couche_inconnue`
passent « par accident », `test_desactiver_supprime...` échoue. C'est l'échec attendu.

- [ ] **Step 3 : Implémenter la route dans `web/routes/templates_route.py`**

Insérer après la route `activer` :

```python
@bp.route("/desactiver/<couche>/<type_t>", methods=["POST"])
@require_auth
def desactiver(couche: str, type_t: str):
    """État « Aucun » : supprime le fichier actif de la couche pour ce mode.

    Le kiosque gère nativement l'absence (fond → toile blanche, overlay → photo
    nue), effet à la photo suivante. Idempotent si déjà aucun template actif.
    """
    if couche not in COUCHES_AUTORISEES or type_t not in TYPES_AUTORISES:
        abort(404)
    cible_active = _CIBLE_ACTIVE[(couche, type_t)]
    try:
        os.remove(cible_active)
    except FileNotFoundError:
        pass
    with connexion() as conn:
        conn.execute(
            "UPDATE template SET actif = 0 WHERE couche = ? AND type = ?",
            (couche, type_t),
        )
    flash(f"Aucun template {couche} pour le mode {type_t} (désactivé).", "success")
    return redirect(url_for("templates.index"))
```

- [ ] **Step 4 : Vérifier le succès**

Run: `pytest tests/test_web_templates.py -v`
Expected: PASS (toutes classes).

- [ ] **Step 5 : Commit**

```bash
git add web/routes/templates_route.py tests/test_web_templates.py
git commit -m "feat(admin): désactivation « Aucun » par couche×format + tests activation fonds"
```

---

### Task 5 : Interface — deux sections + boutons « Aucun »

**Files:**
- Modify: `web/templates/templates.html` (remplacement complet)
- Test: `test_web_templates.py`

- [ ] **Step 1 : Écrire le test de rendu (échec attendu)**

```python
class TestPageDeuxCouches:
    def test_page_contient_sections_et_desactivation(self, client):
        c, _, _ = client
        r = c.get("/templates/", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "Overlays" in html
        assert "Fonds" in html
        assert "/templates/desactiver/overlay/10x15" in html
        assert "/templates/desactiver/fond/strip" in html

    def test_etat_aucun_affiche_par_defaut(self, client):
        c, _, _ = client
        r = c.get("/templates/", headers=HEADERS)
        assert "Aucun" in r.get_data(as_text=True)
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `pytest tests/test_web_templates.py::TestPageDeuxCouches -v`
Expected: FAIL (« Fonds » absent du HTML actuel).

- [ ] **Step 3 : Remplacer `web/templates/templates.html`**

Contenu complet :

```html
{% extends "base.html" %}
{% block titre %}Templates · Photobooth{% endblock %}
{% block contenu %}
<h1>Templates</h1>

{% set libelles_couche = {"overlay": "Overlays (cadres PNG)", "fond": "Fonds (sous les photos)"} %}
{% set libelles_type = {"10x15": "10×15 (grand format)", "strip": "Bandelette (strip)"} %}

<section class="panel">
  <h2>Uploader un nouveau template</h2>
  <form class="form" method="post" action="{{ url_for('templates.upload') }}" enctype="multipart/form-data">
    <label>
      Nom affiché
      <input type="text" name="nom" maxlength="80" placeholder="ex : Mariage Camille &amp; Paul">
    </label>
    <label>
      Couche
      <select name="couche" required>
        <option value="overlay">Overlay (cadre PNG par-dessus)</option>
        <option value="fond">Fond (image sous les photos)</option>
      </select>
    </label>
    <label>
      Type
      <select name="type" required>
        <option value="10x15">10×15 (grand format)</option>
        <option value="strip">Bandelette (strip)</option>
      </select>
    </label>
    <label>
      Fichier (PNG pour overlay ; JPG ou PNG pour fond)
      <input type="file" name="fichier" accept="image/png,image/jpeg" required>
    </label>
    <button type="submit">Uploader</button>
  </form>
  <p class="muted">
    Overlays stockés dans <code>{{ path_overlays }}</code>, fonds dans <code>{{ path_fonds }}</code>.
    Dimensions du montage : 1800×1200 pour 10×15, 600×1800 pour strip.
    L'overlay doit être un PNG avec transparence.
  </p>
</section>

{% for couche in couches %}
<section class="panel">
  <h2>{{ libelles_couche[couche] }}</h2>

  <ul class="etats">
    {% for type_t in types %}
      <li>
        <strong>{{ libelles_type[type_t] }}</strong> —
        {% set nom_actif = actifs.get((couche, type_t)) %}
        {% if nom_actif %}
          <span class="badge badge--actif">Actif : {{ nom_actif }}</span>
          <form method="post" class="inline"
                action="{{ url_for('templates.desactiver', couche=couche, type_t=type_t) }}"
                onsubmit="return confirm('Passer en « aucun template » pour ce mode ?');">
            <button type="submit" class="btn btn--danger">Aucun (désactiver)</button>
          </form>
        {% else %}
          <span class="badge">Aucun</span>
          <form method="post" class="inline"
                action="{{ url_for('templates.desactiver', couche=couche, type_t=type_t) }}">
            <button type="submit" class="btn" title="Supprime aussi un fichier actif posé à la main">Forcer « aucun »</button>
          </form>
        {% endif %}
      </li>
    {% endfor %}
  </ul>

  {% set liste = templates | selectattr("couche", "equalto", couche) | list %}
  {% if liste %}
    <ul class="templates">
      {% for t in liste %}
        <li class="templates__item {% if t.actif %}templates__item--actif{% endif %}">
          <img src="{{ url_for('templates.thumb', template_id=t.id) }}" alt="{{ t.nom }}">
          <div class="templates__info">
            <h3>{{ t.nom }}</h3>
            <p>
              <span class="badge badge--{{ t.type }}">{{ t.type }}</span>
              {% if t.actif %}<span class="badge badge--actif">Actif</span>{% endif %}
              <span class="muted">{{ t.taille_ko }} Ko — {{ t.uploaded_at }}</span>
            </p>
            <div class="actions">
              {% if not t.actif %}
                <form method="post" action="{{ url_for('templates.activer', template_id=t.id) }}">
                  <button type="submit" class="btn btn--primary">Activer</button>
                </form>
                <form method="post" action="{{ url_for('templates.supprimer', template_id=t.id) }}" onsubmit="return confirm('Supprimer ce template ?');">
                  <button type="submit" class="btn btn--danger">Supprimer</button>
                </form>
              {% else %}
                <span class="muted">Utilisé par le kiosque actuellement.</span>
              {% endif %}
            </div>
          </div>
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p class="muted">Aucun template {{ couche }} enregistré. Uploade un fichier ci-dessus.</p>
  {% endif %}
</section>
{% endfor %}
{% endblock %}
```

Note : l'indicateur « Aucun » se base sur la DB (`actifs`). Un fichier actif posé à la
main (hors admin) n'est pas connu de la DB — d'où le bouton « Forcer aucun » qui
supprime la cible même sans template actif en base.

- [ ] **Step 4 : Vérifier le succès**

Run: `pytest tests/test_web_templates.py -v`
Expected: PASS.

- [ ] **Step 5 : Ajouter le style minimal (si classes manquantes)**

Vérifier dans `web/static/admin.css` que `.inline` et `.etats` existent ; sinon ajouter :

```css
.etats { list-style: none; padding: 0; }
.etats li { margin: .4rem 0; display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }
form.inline { display: inline; margin: 0; }
```

- [ ] **Step 6 : Commit**

```bash
git add web/templates/templates.html web/static/admin.css tests/test_web_templates.py
git commit -m "feat(admin): page Templates deux sections (overlays/fonds) + boutons « Aucun »"
```

---

### Task 6 : Documentation + vérification finale

**Files:**
- Modify: `docs/ADMIN.md`

- [ ] **Step 1 : Mettre à jour `docs/ADMIN.md`**

Remplacer la puce descriptive :

```markdown
- **Templates** : bibliothèque des deux couches d'habillage — **overlays** (PNG
  par-dessus la photo) et **fonds** (image sous les photos) — upload, activation
  par format (10×15 / strip), et état « Aucun » par couche×format (photo nue /
  fond blanc, effet à la photo suivante, sans redémarrage du kiosque).
```

Dans le tableau « Source de vérité », remplacer les lignes overlays par :

```markdown
| Overlays PNG (bibliothèque) | `assets/overlays/*.png` | admin | kiosque (montage) |
| Fonds JPG/PNG (bibliothèque) | `assets/backgrounds/*` | admin | kiosque (montage) |
| Couches actives | `assets/overlays/{10x15,strips}_overlay.png` et `assets/backgrounds/{10x15,strips}_background.jpg` (copies du template activé ; fichier absent = « aucun ») | admin | kiosque |
```

- [ ] **Step 2 : Suite complète + lint + couverture**

Run: `pytest -q && ruff check . && pytest -q --cov --cov-report=term | tail -5`
Expected: tous les tests passent, ruff propre, couverture totale ≥ 75 % (cible ~89 %).

- [ ] **Step 3 : Commit**

```bash
git add docs/ADMIN.md
git commit -m "docs: ADMIN.md — page Templates deux couches (overlays + fonds, état « Aucun »)"
```

---

## Auto-revue (faite à l'écriture du plan)

- **Couverture spec** : modèle de données (T1), stockage/upload (T2-T3), activation +
  désactivation (T4), UI (T5), erreurs (T4 idempotence/404, T2 validations), docs (T6). ✔
- **Point spec « thumb/supprimer résolus par couche »** : couvert en T2 Step 3. ✔
- **Types cohérents** : `couche` partout en `str` (`"overlay"`/`"fond"`), `_CIBLE_ACTIVE`
  keyé par tuple dans le code ET la fixture, fixture retourne un triplet partout. ✔
- **Pas de placeholder** : chaque étape contient le code/commande exacts. ✔
