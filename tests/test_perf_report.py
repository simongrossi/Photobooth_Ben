"""Tests du rapport performance sur événements synthétiques."""
import json

from perf_report import analyser_evenements, charger_evenements


def _capture(index: int, mode: str = "10x15") -> dict:
    return {
        "event": "capture",
        "mode": mode,
        "preview_fps": 10.0,
        "capture_total_ms": 6000.0,
        "rss_mb": 100.0 + index * 6,
        "temperature_c": 76.0,
        "camera_preview": {
            "first_frame_ms": 700.0,
            "acquisition_ms": {"p95": 40.0},
            "decode_ms": {"p95": 12.0},
        },
        "countdown_render_ms": {"p95": 30.0},
    }


def test_analyse_detecte_alertes_et_croissance_rss():
    evenements = [_capture(i) for i in range(5)]
    evenements.extend([
        {"event": "preview_validation", "duration_ms": 700.0, "mode": "10x15"},
        {"event": "montage_final", "duration_ms": 3500.0, "mode": "10x15"},
        {"event": "session_end", "mode": "10x15"},
    ])

    rapport = analyser_evenements(evenements)

    assert rapport["captures"] == 5
    assert rapport["sessions"] == 1
    assert rapport["rss_growth_mb"] == 24.0
    assert len(rapport["alerts"]) >= 6
    assert rapport["by_mode"]["10x15"]["captures"] == 5


def test_chargement_ignore_ligne_invalide_et_lit_rotations(tmp_path):
    chemin = tmp_path / "performance.jsonl"
    (tmp_path / "performance.jsonl.1").write_text(
        json.dumps({"event": "capture", "capture_total_ms": 1}) + "\n",
        encoding="utf-8",
    )
    chemin.write_text("invalide\n" + json.dumps({"event": "session_end"}) + "\n", encoding="utf-8")

    evenements = charger_evenements(str(chemin))

    assert [e["event"] for e in evenements] == ["capture", "session_end"]


def test_analyse_vide():
    rapport = analyser_evenements([])
    assert rapport["captures"] == 0
    assert rapport["alerts"] == []
