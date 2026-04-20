"""test_monitoring.py — tests unitaires de core/monitoring.py.

Couvre DiskMonitor (rate-limit, transition OK→critique, exception silencieuse)
et lister_images_slideshow (tri mtime, filtres extension, dossiers absents).
"""
from __future__ import annotations

import os
import time

import pytest

from core import monitoring
from core.monitoring import DiskMonitor, TempMonitor, lister_images_slideshow


# --- DiskMonitor ---


class TestDiskMonitorRateLimit:
    def test_premier_tick_declenche_check(self, tmp_path):
        dm = DiskMonitor(path=str(tmp_path), seuil_mb=0, intervalle_s=30)
        dm.tick(maintenant=100.0)
        assert dm.libre_mb is not None
        assert dm._dernier_check_ts == 100.0

    def test_tick_dans_intervalle_skip(self, tmp_path):
        dm = DiskMonitor(path=str(tmp_path), seuil_mb=0, intervalle_s=30)
        dm.tick(maintenant=100.0)
        premier = dm._dernier_check_ts
        dm.tick(maintenant=110.0)  # 10 s après → skippé
        assert dm._dernier_check_ts == premier

    def test_tick_hors_intervalle_rejoue(self, tmp_path):
        dm = DiskMonitor(path=str(tmp_path), seuil_mb=0, intervalle_s=30)
        dm.tick(maintenant=100.0)
        dm.tick(maintenant=140.0)  # 40 s après → rejoué
        assert dm._dernier_check_ts == 140.0


class TestDiskMonitorCritique:
    def test_pas_critique_si_seuil_bas(self, tmp_path):
        dm = DiskMonitor(path=str(tmp_path), seuil_mb=1, intervalle_s=30)
        dm.tick(maintenant=100.0)
        assert dm.critique is False

    def test_critique_si_seuil_tres_haut(self, tmp_path):
        """Seuil à 10 exaoctets → toujours critique."""
        dm = DiskMonitor(path=str(tmp_path), seuil_mb=10 ** 15, intervalle_s=30)
        dm.tick(maintenant=100.0)
        assert dm.critique is True

    def test_transition_ok_vers_critique_loggue_une_fois(self, tmp_path, caplog):
        dm = DiskMonitor(path=str(tmp_path), seuil_mb=10 ** 15, intervalle_s=1)
        with caplog.at_level("WARNING", logger="photobooth"):
            dm.tick(maintenant=100.0)
            # 2e check : déjà critique → pas de nouveau warn
            dm.tick(maintenant=200.0)
        warnings = [r for r in caplog.records if "disque critique" in r.message.lower()]
        assert len(warnings) == 1


class TestDiskMonitorErreur:
    def test_disk_usage_raise_capture_silencieuse(self, tmp_path, monkeypatch):
        """shutil.disk_usage qui raise ne doit pas crasher le tick."""
        def failing(*a, **kw):
            raise OSError("disque perdu")
        monkeypatch.setattr(monitoring.shutil, "disk_usage", failing)
        dm = DiskMonitor(path=str(tmp_path), seuil_mb=0, intervalle_s=1)
        dm.tick(maintenant=100.0)  # ne doit pas lever
        assert dm.libre_mb is None

    def test_maintenant_defaut_time_time(self, tmp_path):
        """Sans arg `maintenant`, doit utiliser time.time()."""
        dm = DiskMonitor(path=str(tmp_path), seuil_mb=0, intervalle_s=30)
        avant = time.time()
        dm.tick()
        apres = time.time()
        assert avant <= dm._dernier_check_ts <= apres


# --- TempMonitor ---


@pytest.fixture
def temp_file_factory(tmp_path):
    """Retourne un factory qui crée un faux /sys/.../temp avec une valeur donnée."""
    def _make(millideg: int) -> str:
        path = tmp_path / f"temp_{millideg}"
        path.write_text(str(millideg))
        return str(path)
    return _make


class TestTempMonitorLecture:
    def test_lecture_ok_convertit_millideg_en_celsius(self, temp_file_factory):
        path = temp_file_factory(55000)
        tm = TempMonitor(path=path, seuil_c=75.0, intervalle_s=0)
        tm.tick(maintenant=100.0)
        assert tm.temp_c == 55.0
        assert tm.critique is False

    def test_temperature_au_dessus_seuil_critique(self, temp_file_factory):
        path = temp_file_factory(80000)
        tm = TempMonitor(path=path, seuil_c=75.0, intervalle_s=0)
        tm.tick(maintenant=100.0)
        assert tm.temp_c == 80.0
        assert tm.critique is True

    def test_pile_au_seuil_est_critique(self, temp_file_factory):
        path = temp_file_factory(75000)
        tm = TempMonitor(path=path, seuil_c=75.0, intervalle_s=0)
        tm.tick(maintenant=100.0)
        assert tm.critique is True


class TestTempMonitorFallback:
    def test_fichier_absent_inerte_silencieux(self, tmp_path):
        tm = TempMonitor(path=str(tmp_path / "pas_ici"), seuil_c=75.0, intervalle_s=0)
        tm.tick(maintenant=100.0)
        assert tm.temp_c is None
        assert tm.critique is False

    def test_contenu_invalide_warn_pas_crash(self, tmp_path, caplog):
        path = tmp_path / "t"
        path.write_text("pas-un-nombre")
        tm = TempMonitor(path=str(path), seuil_c=75.0, intervalle_s=0)
        with caplog.at_level("WARNING", logger="photobooth"):
            tm.tick(maintenant=100.0)
        assert any("Check température" in r.message for r in caplog.records)


class TestTempMonitorRateLimit:
    def test_tick_dans_intervalle_skip(self, temp_file_factory):
        path = temp_file_factory(50000)
        tm = TempMonitor(path=path, seuil_c=75.0, intervalle_s=30)
        tm.tick(maintenant=100.0)
        premier = tm._dernier_check_ts
        tm.tick(maintenant=110.0)
        assert tm._dernier_check_ts == premier

    def test_transition_ok_vers_critique_loggue_une_fois(self, temp_file_factory, caplog):
        # 1er check à 50 °C, puis le fichier change à 80 °C
        path = temp_file_factory(50000)
        tm = TempMonitor(path=path, seuil_c=75.0, intervalle_s=1)
        tm.tick(maintenant=100.0)
        assert tm.critique is False

        # Simule une montée en température
        import os as _os
        _os.remove(path)
        open(path, "w").write("82000")

        with caplog.at_level("WARNING", logger="photobooth"):
            tm.tick(maintenant=200.0)
            tm.tick(maintenant=300.0)  # déjà critique → pas de 2e warn
        warnings = [r for r in caplog.records if "Température CPU critique" in r.message]
        assert len(warnings) == 1


# --- lister_images_slideshow ---


@pytest.fixture
def dossier_avec_images(tmp_path):
    """Crée 5 fichiers : 3 images + 1 non-image + 1 subdirectory. Retourne le path."""
    d = tmp_path / "prints"
    d.mkdir()
    (d / "photo1.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (d / "photo2.png").write_bytes(b"\x89PNG")
    (d / "photo3.JPEG").write_bytes(b"\xff\xd8\xff\xd9")
    (d / "notes.txt").write_text("pas une image")
    (d / "subdir").mkdir()
    return str(d)


class TestListerImages:
    def test_retourne_seulement_images(self, dossier_avec_images):
        fichiers = lister_images_slideshow([dossier_avec_images], nb_max=10)
        noms = [os.path.basename(f) for f in fichiers]
        assert all(n.lower().endswith((".jpg", ".jpeg", ".png")) for n in noms)
        assert "notes.txt" not in noms

    def test_respecte_nb_max(self, dossier_avec_images):
        fichiers = lister_images_slideshow([dossier_avec_images], nb_max=2)
        assert len(fichiers) == 2

    def test_tri_mtime_desc(self, tmp_path):
        d = tmp_path / "p"
        d.mkdir()
        # Crée 3 fichiers avec mtime manuels
        f1 = d / "old.jpg"
        f1.write_bytes(b"x")
        os.utime(f1, (100.0, 100.0))
        f2 = d / "mid.jpg"
        f2.write_bytes(b"x")
        os.utime(f2, (200.0, 200.0))
        f3 = d / "recent.jpg"
        f3.write_bytes(b"x")
        os.utime(f3, (300.0, 300.0))

        fichiers = lister_images_slideshow([str(d)], nb_max=10)
        noms = [os.path.basename(f) for f in fichiers]
        assert noms == ["recent.jpg", "mid.jpg", "old.jpg"]

    def test_dossier_absent_ignore_silencieusement(self, tmp_path):
        absent = str(tmp_path / "pas_ici")
        present = str(tmp_path)
        (tmp_path / "p.jpg").write_bytes(b"x")
        # Le dossier absent ne doit pas lever
        fichiers = lister_images_slideshow([absent, present], nb_max=10)
        assert len(fichiers) == 1

    def test_liste_vide_si_tout_absent(self, tmp_path):
        fichiers = lister_images_slideshow(
            [str(tmp_path / "a"), str(tmp_path / "b")], nb_max=10,
        )
        assert fichiers == []

    def test_multi_dossiers_merge(self, tmp_path):
        d1 = tmp_path / "d1"
        d1.mkdir()
        (d1 / "a.jpg").write_bytes(b"x")
        d2 = tmp_path / "d2"
        d2.mkdir()
        (d2 / "b.jpg").write_bytes(b"x")

        fichiers = lister_images_slideshow([str(d1), str(d2)], nb_max=10)
        assert len(fichiers) == 2
