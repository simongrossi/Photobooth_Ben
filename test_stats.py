"""test_stats.py — tests unitaires de stats.py.

Couvre le parsing JSONL, le filtrage par date, le calcul d'agrégats et
l'affichage JSON. Isolation via tmp_path pour les fichiers factices.
"""
import json
import os
import subprocess
import sys

import pytest

import stats


# --- Fixtures ---

@pytest.fixture
def jsonl_factice(tmp_path):
    """Crée un fichier sessions.jsonl factice avec 8 sessions variées."""
    chemin = tmp_path / "sessions.jsonl"
    entries = [
        {"session_id": "s1", "mode": "10x15", "issue": "printed",
         "nb_photos": 1, "duree_s": 45.2, "ts": "2026-04-20 14:30:45"},
        {"session_id": "s2", "mode": "strips", "issue": "printed",
         "nb_photos": 3, "duree_s": 78.5, "ts": "2026-04-20 14:35:52"},
        {"session_id": "s3", "mode": "strips", "issue": "abandoned",
         "nb_photos": 1, "duree_s": 25.0, "ts": "2026-04-20 14:40:35"},
        {"session_id": "s4", "mode": "10x15", "issue": "capture_failed",
         "nb_photos": 0, "duree_s": 12.3, "ts": "2026-04-20 15:02:45"},
        {"session_id": "s5", "mode": "10x15", "issue": "printed",
         "nb_photos": 1, "duree_s": 50.0, "ts": "2026-04-20 15:15:58"},
        {"session_id": "s6", "mode": "strips", "issue": "printed",
         "nb_photos": 3, "duree_s": 95.0, "ts": "2026-04-21 22:10:41"},
        {"session_id": "s7", "mode": "strips", "issue": "print_failed",
         "nb_photos": 3, "duree_s": 82.0, "ts": "2026-04-20 16:20:10"},
        {"session_id": "s8", "mode": "10x15", "issue": "print_disabled",
         "nb_photos": 1, "duree_s": 44.0, "ts": "2026-04-20 16:25:10"},
    ]
    with chemin.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return str(chemin)


# --- Tests load_sessions ---

class TestLoadSessions:
    def test_fichier_absent_retourne_none(self, tmp_path):
        assert stats.load_sessions(str(tmp_path / "absent.jsonl")) is None

    def test_charge_toutes_les_lignes(self, jsonl_factice):
        sessions = stats.load_sessions(jsonl_factice)
        assert len(sessions) == 8

    def test_tolere_lignes_corrompues(self, tmp_path):
        chemin = tmp_path / "corrompu.jsonl"
        chemin.write_text(
            '{"mode": "10x15"}\n'
            'pas du json\n'
            '\n'  # ligne vide tolérée
            '{"mode": "strips"}\n',
            encoding="utf-8",
        )
        sessions = stats.load_sessions(str(chemin))
        assert len(sessions) == 2


# --- Tests filtrer_par_date ---

class TestFiltrerParDate:
    def test_filtre_exact(self, jsonl_factice):
        sessions = stats.load_sessions(jsonl_factice)
        filtrees = stats.filtrer_par_date(sessions, "2026-04-20")
        assert len(filtrees) == 7

    def test_date_sans_sessions(self, jsonl_factice):
        sessions = stats.load_sessions(jsonl_factice)
        assert stats.filtrer_par_date(sessions, "2030-01-01") == []


# --- Tests calculer_stats ---

class TestCalculerStats:
    def test_vide(self):
        s = stats.calculer_stats([])
        assert s == {"total": 0}

    def test_agregation_complete(self, jsonl_factice):
        sessions = stats.load_sessions(jsonl_factice)
        s = stats.calculer_stats(sessions)

        assert s["total"] == 8
        assert s["printed"] == 4
        assert s["abandoned"] == 1
        assert s["capture_failed"] == 1
        assert s["print_failed"] == 1
        assert s["print_disabled"] == 1
        assert s["modes"] == {"10x15": 4, "strips": 4}
        assert s["nb_photos_total"] == 13
        # Durée moyenne des 8 sessions ≈ 54.0
        assert 53.0 < s["duree_moyenne_s"] < 55.0
        assert s["duree_max_s"] == 95.0

    def test_heure_de_pointe(self, jsonl_factice):
        sessions = stats.load_sessions(jsonl_factice)
        s = stats.calculer_stats(sessions)
        # 14h : 3 sessions, 15h : 2 sessions, 16h : 2 sessions, 22h : 1 session
        assert s["heure_pointe"] == (14, 3)


# --- Tests in-process (pour la couverture) ---

class TestCalculerStatsTsMalforme:
    def test_ts_malforme_ignore(self):
        """Ts invalide (pas de date ou pas d'heure) doit être skippé sans crash."""
        sessions = [
            {"mode": "10x15", "issue": "printed", "nb_photos": 1,
             "duree_s": 40.0, "ts": ""},  # ts vide
            {"mode": "10x15", "issue": "printed", "nb_photos": 1,
             "duree_s": 40.0, "ts": "pas_une_date"},  # ts sans espace
            {"mode": "10x15", "issue": "printed", "nb_photos": 1,
             "duree_s": 40.0, "ts": "2026-04-20 xx:yy:zz"},  # heure non-num
        ]
        s = stats.calculer_stats(sessions)
        assert s["total"] == 3
        assert s["heures"] == {}
        assert s["heure_pointe"] is None


class TestAfficherTexte:
    def test_vide_ne_crashe_pas(self, capsys):
        stats.afficher_texte({"total": 0, "printed": 0, "abandoned": 0,
                              "capture_failed": 0, "print_failed": 0,
                              "print_disabled": 0, "modes": {},
                              "duree_moyenne_s": 0, "duree_max_s": 0,
                              "heures": {}, "heure_pointe": None,
                              "nb_photos_total": 0})
        captured = capsys.readouterr()
        assert "Aucune session" in captured.out

    def test_complet_imprime_tout(self, capsys, jsonl_factice):
        sessions = stats.load_sessions(jsonl_factice)
        s = stats.calculer_stats(sessions)
        stats.afficher_texte(s, date_filter="2026-04-20")
        out = capsys.readouterr().out
        assert "RAPPORT PHOTOBOOTH" in out
        assert "2026-04-20" in out
        assert "Heure de pointe" in out
        assert "Répartition horaire" in out
        assert "Impression KO" in out
        assert "Sans papier" in out


class TestMainInProcess:
    def test_main_fichier_absent(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv",
                            ["stats.py", "--file", str(tmp_path / "absent.jsonl")])
        assert stats.main() == 1

    def test_main_json_ok(self, jsonl_factice, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv",
                            ["stats.py", "--json", "--file", jsonl_factice])
        assert stats.main() == 0
        data = json.loads(capsys.readouterr().out)
        assert data["total"] == 8

    def test_main_texte_ok(self, jsonl_factice, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv",
                            ["stats.py", "--date", "2026-04-20", "--file", jsonl_factice])
        assert stats.main() == 0
        assert "RAPPORT PHOTOBOOTH" in capsys.readouterr().out


# --- Tests d'intégration du CLI ---

class TestCLI:
    def test_exit_1_si_fichier_absent(self, tmp_path):
        result = subprocess.run(
            [sys.executable, "stats.py", "--file", str(tmp_path / "absent.jsonl")],
            capture_output=True, text=True, cwd=os.getcwd(),
        )
        assert result.returncode == 1

    def test_mode_json_produit_json_parsable(self, jsonl_factice):
        result = subprocess.run(
            [sys.executable, "stats.py", "--json", "--file", jsonl_factice],
            capture_output=True, text=True, cwd=os.getcwd(),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["total"] == 8
        assert data["printed"] == 4
        assert data["print_failed"] == 1
        assert data["print_disabled"] == 1
        # heure_pointe sérialisé en dict en mode --json
        assert data["heure_pointe"]["heure"] == 14

    def test_filtre_date_via_cli(self, jsonl_factice):
        result = subprocess.run(
            [sys.executable, "stats.py", "--date", "2026-04-21",
             "--file", jsonl_factice],
            capture_output=True, text=True, cwd=os.getcwd(),
        )
        assert result.returncode == 0
        # Seulement 1 session le 21 avril
        assert "total : 1" in result.stdout
