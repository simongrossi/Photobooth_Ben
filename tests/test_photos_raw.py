"""test_photos_raw.py — regroupement des photos brutes par session.

Module partagé par la galerie et l'aperçu du rendu final.
"""
from __future__ import annotations

import pytest
from PIL import Image

from web import photos_raw


@pytest.fixture
def raw(tmp_path, monkeypatch):
    dossier = tmp_path / "raw"
    dossier.mkdir()
    monkeypatch.setattr(photos_raw, "PATH_RAW", str(dossier))
    return dossier


def _photo(dossier, nom):
    Image.new("RGB", (40, 30), (10, 20, 30)).save(dossier / nom, "JPEG")


class TestExtraireSessionId:
    def test_reconnait_le_format_du_kiosque(self):
        assert photos_raw.extraire_session_id(
            "photo_2026-08-20_14h32_07_1.jpg"
        ) == "2026-08-20_14h32_07"

    def test_retourne_none_hors_format(self):
        assert photos_raw.extraire_session_id("capture.jpg") is None


class TestListerSessions:
    def test_dossier_vide(self, raw):
        assert photos_raw.lister_sessions() == []

    def test_dossier_absent(self, monkeypatch, tmp_path):
        monkeypatch.setattr(photos_raw, "PATH_RAW", str(tmp_path / "nexiste_pas"))
        assert photos_raw.lister_sessions() == []

    def test_regroupe_les_photos_d_une_session(self, raw):
        for i in (1, 2, 3):
            _photo(raw, f"photo_2026-08-20_14h32_07_{i}.jpg")
        sessions = photos_raw.lister_sessions()
        assert len(sessions) == 1
        assert sessions[0].id_session == "2026-08-20_14h32_07"
        assert len(sessions[0].photos) == 3

    def test_photos_triees_par_index(self, raw):
        for i in (3, 1, 2):
            _photo(raw, f"photo_2026-08-20_14h32_07_{i}.jpg")
        photos = photos_raw.lister_sessions()[0].photos
        assert [p.rsplit("_", 1)[1] for p in photos] == ["1.jpg", "2.jpg", "3.jpg"]

    def test_la_plus_recente_d_abord(self, raw):
        _photo(raw, "photo_2026-08-20_09h00_00_1.jpg")
        _photo(raw, "photo_2026-08-20_21h15_42_1.jpg")
        ids = [s.id_session for s in photos_raw.lister_sessions()]
        assert ids == ["2026-08-20_21h15_42", "2026-08-20_09h00_00"]

    def test_ignore_les_fichiers_hors_format(self, raw):
        _photo(raw, "photo_2026-08-20_14h32_07_1.jpg")
        (raw / "notes.txt").write_text("bruit")
        _photo(raw, "capture_manuelle.jpg")
        assert len(photos_raw.lister_sessions()) == 1

    def test_filtre_par_nombre_de_photos(self, raw):
        _photo(raw, "photo_2026-08-20_09h00_00_1.jpg")
        for i in (1, 2, 3):
            _photo(raw, f"photo_2026-08-20_21h15_42_{i}.jpg")
        triplets = photos_raw.lister_sessions(minimum_photos=3)
        assert [s.id_session for s in triplets] == ["2026-08-20_21h15_42"]


class TestSessionParId:
    def test_retrouve_une_session(self, raw):
        _photo(raw, "photo_2026-08-20_14h32_07_1.jpg")
        session = photos_raw.session_par_id("2026-08-20_14h32_07")
        assert session is not None
        assert len(session.photos) == 1

    def test_none_si_absente(self, raw):
        assert photos_raw.session_par_id("2026-01-01_00h00_00") is None

    def test_none_si_trop_courte_pour_un_strip(self, raw):
        _photo(raw, "photo_2026-08-20_14h32_07_1.jpg")
        assert photos_raw.session_par_id(
            "2026-08-20_14h32_07", minimum_photos=3
        ) is None


class TestImageSubstitution:
    def test_dimensions_et_mode(self):
        image = photos_raw.image_substitution()
        assert image.mode == "RGB"
        assert image.size == (1200, 800)

    def test_chemin_temporaire_utilisable_puis_nettoye(self):
        with photos_raw.photo_substitution() as chemin:
            assert photos_raw.os.path.isfile(chemin)
            ouverte = Image.open(chemin)
            assert ouverte.size == (1200, 800)
            ouverte.close()
        assert not photos_raw.os.path.isfile(chemin)
