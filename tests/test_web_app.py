"""test_web_app.py — tests de l'app Flask d'admin (auth, routing, dashboard)."""
from __future__ import annotations

import base64
import json

import pytest

from web.app import create_app


HEADERS_OK = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}
HEADERS_KO = {"Authorization": "Basic " + base64.b64encode(b"admin:wrong").decode()}


@pytest.fixture
def app(tmp_path, monkeypatch):
    """App Flask avec data/ isolé dans tmp_path + mot de passe 'test'."""
    data_path = tmp_path / "data"
    data_path.mkdir()
    (data_path / "print").mkdir()
    (data_path / "print" / "print_10x15").mkdir()
    (data_path / "print" / "print_strip").mkdir()
    overlays = tmp_path / "overlays"
    overlays.mkdir()

    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")
    # Redirige les chemins config vers tmp_path (sans casser les autres tests).
    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data_path))
    monkeypatch.setattr(config, "PATH_PRINT", str(data_path / "print"))
    monkeypatch.setattr(config, "PATH_PRINT_10X15", str(data_path / "print" / "print_10x15"))
    monkeypatch.setattr(config, "PATH_PRINT_STRIP", str(data_path / "print" / "print_strip"))
    monkeypatch.setattr(config, "PATH_OVERLAYS", str(overlays))
    monkeypatch.setattr(config, "OVERLAY_10X15", str(overlays / "10x15_overlay.png"))
    monkeypatch.setattr(config, "OVERLAY_STRIPS", str(overlays / "strips_overlay.png"))
    monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(data_path / "config_overrides.json"))
    # Modules déjà importés qui captent les chemins par `from config import`.
    import web.db
    import web.routes.gallery
    import web.routes.settings_route
    import web.routes.templates_route
    monkeypatch.setattr(web.db, "DB_PATH", str(data_path / "admin.db"))
    monkeypatch.setattr(web.routes.gallery, "_RACINES_AUTORISEES", {
        "10x15": str(data_path / "print" / "print_10x15"),
        "strip": str(data_path / "print" / "print_strip"),
    })
    monkeypatch.setattr(web.routes.templates_route, "_CIBLE_ACTIVE", {
        "10x15": str(overlays / "10x15_overlay.png"),
        "strip": str(overlays / "strips_overlay.png"),
    })
    monkeypatch.setattr(
        web.routes.settings_route,
        "CONFIG_OVERRIDES_PATH",
        str(data_path / "config_overrides.json"),
    )

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestAuth:
    def test_sans_env_var_retourne_503(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PHOTOBOOTH_ADMIN_PASS", raising=False)
        # Isole la DB : create_app() appelle init_db(), qui ne doit jamais
        # toucher la vraie data/admin.db depuis un test.
        import web.db
        monkeypatch.setattr(web.db, "DB_PATH", str(tmp_path / "admin.db"))
        app = create_app()
        c = app.test_client()
        r = c.get("/dashboard/")
        assert r.status_code == 503

    def test_sans_auth_retourne_401(self, client):
        # /dashboard/ est désormais consultable en anonyme (mode viewer) —
        # les pages de gestion, elles, exigent toujours l'admin.
        r = client.get("/settings/")
        assert r.status_code == 401
        assert "WWW-Authenticate" in r.headers

    def test_mauvais_mdp_retourne_401(self, client):
        r = client.get("/dashboard/", headers=HEADERS_KO)
        assert r.status_code == 401

    def test_bon_mdp_retourne_200(self, client):
        r = client.get("/dashboard/", headers=HEADERS_OK)
        assert r.status_code == 200


class TestIndex:
    def test_redirige_vers_dashboard(self, client):
        r = client.get("/")
        assert r.status_code == 302
        assert "/dashboard" in r.headers["Location"]


class TestDashboard:
    def test_sans_sessions_affiche_zero(self, client):
        r = client.get("/dashboard/", headers=HEADERS_OK)
        assert r.status_code == 200
        assert b"Sessions" in r.data

    def test_horloge_utilise_et_resynchronise_heure_serveur(self, client, monkeypatch):
        from datetime import datetime, timedelta, timezone
        import web.routes.dashboard as dash
        fixe = datetime(2026, 7, 14, 21, 42, 5, tzinfo=timezone(timedelta(hours=2)))
        monkeypatch.setattr(dash, "_maintenant_serveur", lambda: fixe)

        page = client.get("/dashboard/", headers=HEADERS_OK).get_data(as_text=True)
        assert 'id="server-clock"' in page
        assert "14/07/2026 21:42:05" in page
        assert "/dashboard/heure" in page

        heure = client.get("/dashboard/heure", headers=HEADERS_OK)
        assert heure.status_code == 200
        assert heure.json["serveur_offset_minutes"] == 120
        assert heure.json["serveur_heure_texte"] == "14/07/2026 21:42:05"

    def test_avec_sessions(self, client, app, tmp_path):
        import config
        jsonl = tmp_path / "data" / "sessions.jsonl"
        from datetime import date
        jsonl.write_text(json.dumps({
            "session_id": "s1", "mode": "10x15", "issue": "printed",
            "nb_photos": 1, "duree_s": 30.0, "ts": f"{date.today().strftime('%Y-%m-%d')} 14:00:00",
        }) + "\n", encoding="utf-8")
        assert config.PATH_DATA == str(tmp_path / "data")
        r = client.get("/dashboard/", headers=HEADERS_OK)
        assert r.status_code == 200
        # La card "Imprimées" doit contenir 1.
        assert b"Imprim" in r.data
        assert b"R\xc3\xa9partition horaire" in r.data


class TestDashboardV2:
    def test_quatre_etages_presents(self, client, monkeypatch):
        import web.routes.dashboard as dash
        monkeypatch.setattr(dash.printer_mgr, "is_ready", lambda mode: True)
        r = client.get("/dashboard/", headers=HEADERS_OK)
        html = r.get_data(as_text=True)
        assert "Aujourd'hui" in html
        assert "Historique par journée" in html
        assert "pastille--ok" in html          # imprimantes mockées prêtes
        assert "Imprimante 10×15" in html

    def test_imprimante_en_erreur_pastille_rouge(self, client, monkeypatch):
        import web.routes.dashboard as dash
        monkeypatch.setattr(dash.printer_mgr, "is_ready",
                            lambda mode: "FILE D'ATTENTE PLEINE")
        r = client.get("/dashboard/", headers=HEADERS_OK)
        html = r.get_data(as_text=True)
        assert "pastille--err" in html
        assert "FILE D&#39;ATTENTE PLEINE" in html or "FILE D'ATTENTE PLEINE" in html

    def test_zero_session_ne_crashe_pas(self, client, monkeypatch):
        import web.routes.dashboard as dash
        monkeypatch.setattr(dash.printer_mgr, "is_ready", lambda mode: True)
        r = client.get("/dashboard/", headers=HEADERS_OK)
        assert r.status_code == 200

    def test_dashboard_filtre_periode(self, client, app, tmp_path):
        import config
        from datetime import date, timedelta
        import json
        jsonl = tmp_path / "data" / "sessions.jsonl"
        
        # Une session récente (aujourd'hui)
        s_recent = {
            "session_id": "recent", "mode": "10x15", "issue": "printed",
            "nb_photos": 1, "duree_s": 30.0, "ts": f"{date.today().strftime('%Y-%m-%d')} 14:00:00",
        }
        # Une session ancienne (15 jours)
        s_ancienne = {
            "session_id": "ancienne", "mode": "strips", "issue": "printed",
            "nb_photos": 3, "duree_s": 45.0, "ts": f"{(date.today() - timedelta(days=15)).strftime('%Y-%m-%d')} 15:00:00",
        }
        
        jsonl.write_text(json.dumps(s_recent) + "\n" + json.dumps(s_ancienne) + "\n", encoding="utf-8")
        assert config.PATH_DATA == str(tmp_path / "data")
        
        # Par défaut (récent) : seulement la session récente
        r1 = client.get("/dashboard/", headers=HEADERS_OK)
        html1 = r1.get_data(as_text=True)
        # La période par défaut est explicitement de 7 jours.
        assert "Sessions — 7 derniers jours</div>" in html1
        assert "1" in html1
        
        # Avec filtre toutes : les deux sessions
        r2 = client.get("/dashboard/?periode=toutes", headers=HEADERS_OK)
        html2 = r2.get_data(as_text=True)
        assert "Sessions — Tout depuis le début</div>" in html2
        assert "2" in html2

    def test_filtres_en_jours_calendaires(self):
        from datetime import date, timedelta

        from web.routes.dashboard import _filtrer_sessions_par_periode

        aujourd_hui = date(2026, 7, 14)
        sessions = [
            {"ts": f"{(aujourd_hui - timedelta(days=delta)).isoformat()} 12:00:00"}
            for delta in (0, 1, 2, 6, 7, 30)
        ]

        assert len(_filtrer_sessions_par_periode(sessions, "aujourdhui", aujourd_hui)[0]) == 1
        assert len(_filtrer_sessions_par_periode(sessions, "2jours", aujourd_hui)[0]) == 2
        assert len(_filtrer_sessions_par_periode(sessions, "7jours", aujourd_hui)[0]) == 4
        assert len(_filtrer_sessions_par_periode(sessions, "toutes", aujourd_hui)[0]) == 6

    def test_ancien_filtre_recent_reste_compatible(self):
        from datetime import date

        from web.routes.dashboard import _filtrer_sessions_par_periode

        sessions, periode = _filtrer_sessions_par_periode([], "recent", date(2026, 7, 14))
        assert sessions == []
        assert periode == "7jours"
