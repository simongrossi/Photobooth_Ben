"""db.py — SQLite léger pour l'interface admin web.

Stocke les métadonnées admin (registre de templates, journal d'audit). La
source de vérité des overrides config reste `data/config_overrides.json`
(lisible par config.py sans dépendance au DB). Les sessions restent dans
`data/sessions.jsonl` (écrit par le kiosque).

Une seule table aujourd'hui :
- `template`  (id, nom, type, fichier, actif, uploaded_at, taille_octets)

Les types sont "10x15" ou "strip". La colonne `actif` marque le template
actuellement utilisé pour ce mode (un seul actif par type). Les fichiers
eux-mêmes restent sur disque dans `assets/overlays/` — la DB ne stocke
que la liste + flag actif.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from config import PATH_DATA

DB_PATH = os.path.join(PATH_DATA, "admin.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('10x15', 'strip')),
    fichier TEXT NOT NULL UNIQUE,
    actif INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    taille_octets INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_template_type_actif ON template (type, actif);
"""


def _ouvrir(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str = DB_PATH) -> None:
    """Crée la DB si absente, applique le schéma (idempotent)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _ouvrir(path) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


@contextmanager
def connexion(path: str = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Context manager ouvrant une connexion commit-on-success."""
    conn = _ouvrir(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
