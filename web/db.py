"""db.py — SQLite léger pour l'interface admin web.

Stocke les métadonnées admin (registre de templates, journal d'audit). La
source de vérité des overrides config reste `data/config_overrides.json`
(lisible par config.py sans dépendance au DB). Les sessions restent dans
`data/sessions.jsonl` (écrit par le kiosque).

Tables principales :
- `template`      (fichier/couche/actif + zone photo 10×15 optionnelle)
- `asset_kiosque` (id, nom, categorie, fichier, actif, uploaded_at, taille_octets)
  — catégories 'accueil' | 'police' | 'slide' ; un actif max par catégorie ;
  `actif` sans objet pour 'slide' (tous les slides présents tournent).
- `evenement`, `tag`, `evenement_tag` pour le cycle de vie événementiel.

Les types sont "10x15" ou "strip" ; les couches "overlay" (PNG par-dessus la
photo) ou "fond" (image sous les photos). La colonne `actif` marque le template
actuellement utilisé (un seul actif par couple couche×type). Les fichiers
eux-mêmes restent sur disque dans `assets/overlays/` et `assets/backgrounds/` —
la DB ne stocke que la liste + flag actif.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from config import PATH_DATA

DB_PATH = os.path.join(PATH_DATA, "admin.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('10x15', 'strip')),
    couche TEXT NOT NULL DEFAULT 'overlay',
    fichier TEXT NOT NULL UNIQUE,
    actif INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    taille_octets INTEGER NOT NULL DEFAULT 0,
    photo_x INTEGER,
    photo_y INTEGER,
    photo_largeur INTEGER,
    photo_hauteur INTEGER
);

CREATE INDEX IF NOT EXISTS idx_template_type_actif ON template (type, actif);

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

CREATE TABLE IF NOT EXISTS evenement (
    id TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    debut TEXT NOT NULL,
    fin TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'brouillon'
        CHECK (statut IN ('brouillon', 'actif', 'termine', 'archive')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_evenement_unique_actif
    ON evenement (statut) WHERE statut = 'actif';
CREATE INDEX IF NOT EXISTS idx_evenement_dates ON evenement (debut, fin);

CREATE TABLE IF NOT EXISTS tag (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL UNIQUE COLLATE NOCASE,
    slug TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS evenement_tag (
    evenement_id TEXT NOT NULL REFERENCES evenement(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (evenement_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_evenement_tag_tag ON evenement_tag (tag_id, evenement_id);
"""


def _ouvrir(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
    for colonne in ("photo_x", "photo_y", "photo_largeur", "photo_hauteur"):
        if colonne not in colonnes:
            conn.execute(f"ALTER TABLE template ADD COLUMN {colonne} INTEGER")


def init_db(path: Optional[str] = None) -> None:
    """Crée la DB si absente, applique le schéma + migrations (idempotent).

    `path=None` → `DB_PATH` résolu à l'appel (et non à l'import) : indispensable
    pour que les tests puissent monkeypatcher `web.db.DB_PATH` — sinon ils
    écriraient dans la vraie base `data/admin.db`.
    """
    if path is None:
        path = DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _ouvrir(path) as conn:
        conn.executescript(_SCHEMA)
        _migrer(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_template_couche_type_actif "
            "ON template (couche, type, actif)"
        )
        conn.commit()


@contextmanager
def connexion(path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    """Context manager ouvrant une connexion commit-on-success.

    `path=None` → `DB_PATH` résolu à l'appel (voir init_db)."""
    if path is None:
        path = DB_PATH
    conn = _ouvrir(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
