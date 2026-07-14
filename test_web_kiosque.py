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
