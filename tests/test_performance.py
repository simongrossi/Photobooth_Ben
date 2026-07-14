"""Tests du journal de performance sans toucher aux vrais logs."""
import json

from core.performance import PerformanceJournal, resumer_durees


def test_resumer_durees_p50_p95_et_frames_lentes():
    resume = resumer_durees([1, 2, 3, 4, 100], seuil_lent_ms=33.3)

    assert resume == {
        "count": 5,
        "avg": 22.0,
        "p50": 3.0,
        "p95": 100.0,
        "max": 100.0,
        "slow_count": 1,
    }


def test_resumer_durees_vide():
    assert resumer_durees([])["count"] == 0
    assert resumer_durees([])["p95"] is None


def test_journal_ecrit_jsonl(tmp_path):
    chemin = tmp_path / "performance.jsonl"
    journal = PerformanceJournal(str(chemin))

    journal.ecrire("capture", session_id="s1", capture_ms=123.4)

    entree = json.loads(chemin.read_text(encoding="utf-8"))
    assert entree["schema"] == 1
    assert entree["event"] == "capture"
    assert entree["session_id"] == "s1"
    assert "ts" in entree


def test_journal_rotation(tmp_path):
    chemin = tmp_path / "performance.jsonl"
    journal = PerformanceJournal(str(chemin), max_bytes=1, backups=2)

    journal.ecrire("premier", valeur="x" * 20)
    journal.ecrire("second")

    assert chemin.exists()
    assert (tmp_path / "performance.jsonl.1").exists()
