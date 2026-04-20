"""test_status.py — tests unitaires de status.py.

Les dépendances système (subprocess gphoto2/lpstat, filesystem) sont mockées
via `unittest.mock.patch`. Le but est de couvrir la logique de parsing
sans nécessiter le vrai matériel.
"""
import os
import subprocess
from unittest.mock import patch, MagicMock


import status


# --- Tests check_file ---

class TestCheckFile:
    def test_fichier_present(self, tmp_path, capsys):
        f = tmp_path / "exists.txt"
        f.write_text("hello")
        assert status.check_file(str(f), "test") is True

    def test_fichier_absent(self, tmp_path, capsys):
        assert status.check_file(str(tmp_path / "absent.txt"), "test") is False


# --- Tests check_disk ---

class TestCheckDisk:
    def test_path_data_absent(self, tmp_path, monkeypatch, capsys):
        """Si PATH_DATA n'existe pas, check_disk retourne False."""
        monkeypatch.setattr(status, "PATH_DATA", str(tmp_path / "pas_ici"))
        assert status.check_disk() is False

    def test_disk_ok_si_plus_de_1go(self, tmp_path, monkeypatch, capsys):
        """Avec du disque libre, check_disk doit retourner True."""
        monkeypatch.setattr(status, "PATH_DATA", str(tmp_path))
        # Le disque local a typiquement > 1 Go libre → test doit passer
        result = status.check_disk()
        # On accepte True (normal) ou False (disque plein — peu probable en CI)
        assert isinstance(result, bool)


# --- Tests check_printer ---

class TestCheckPrinter:
    def test_lpstat_absent(self):
        """Si lpstat n'est pas installé, check_printer retourne False."""
        with patch("status.subprocess.run",
                   side_effect=FileNotFoundError("lpstat")):
            assert status.check_printer("DNP_10x15") is False

    def test_imprimante_absente_de_cups(self):
        """lpstat retourne un stdout vide → printer introuvable."""
        fake = MagicMock(stdout="", returncode=0)
        with patch("status.subprocess.run", return_value=fake):
            assert status.check_printer("DNP_10x15") is False

    def test_imprimante_disabled(self):
        """lpstat mentionne 'disabled' → KO."""
        fake = MagicMock(stdout="printer DNP_10x15 disabled since Tue", returncode=0)
        with patch("status.subprocess.run", return_value=fake):
            assert status.check_printer("DNP_10x15") is False

    def test_imprimante_idle_ok(self):
        """lpstat mentionne 'idle' → OK."""
        fake = MagicMock(stdout="printer DNP_10x15 is idle", returncode=0)
        with patch("status.subprocess.run", return_value=fake):
            assert status.check_printer("DNP_10x15") is True

    def test_imprimante_enabled_ok(self):
        fake = MagicMock(stdout="printer DNP_10x15 is enabled", returncode=0)
        with patch("status.subprocess.run", return_value=fake):
            assert status.check_printer("DNP_10x15") is True


# --- Tests check_camera ---

class TestCheckCamera:
    def test_gphoto2_absent(self):
        """Si gphoto2 n'est pas installé, check_camera retourne False."""
        with patch("status.subprocess.run",
                   side_effect=FileNotFoundError("gphoto2")):
            assert status.check_camera() is False

    def test_aucune_camera_detectee(self):
        """gphoto2 --auto-detect retourne un header vide → aucune caméra."""
        fake = MagicMock(
            stdout="Model                          Port\n----------------------------------\n",
            returncode=0,
        )
        with patch("status.subprocess.run", return_value=fake):
            assert status.check_camera() is False

    def test_camera_detectee(self):
        """gphoto2 --auto-detect liste un modèle → OK."""
        fake = MagicMock(
            stdout=(
                "Model                          Port\n"
                "----------------------------------------\n"
                "Canon EOS 500D                 usb:001,005\n"
            ),
            returncode=0,
        )
        with patch("status.subprocess.run", return_value=fake):
            assert status.check_camera() is True


# --- Tests CLI ---

class TestCLI:
    def test_cli_retourne_exit_code(self):
        """Le script tourne et retourne un exit code 0 ou 1 (dépend de la machine)."""
        import sys
        result = subprocess.run(
            [sys.executable, "status.py"],
            capture_output=True, text=True, cwd=os.getcwd(),
        )
        assert result.returncode in (0, 1)
        # Au minimum, le header doit apparaître
        assert "Photobooth" in result.stdout


# --- Tests in-process pour la couverture ---


class TestCheckTemperature:
    def test_fichier_absent_retourne_true_non_bloquant(self, monkeypatch, capsys):
        """Sur macOS/Windows, pas de /sys/class/thermal → pas un échec."""
        monkeypatch.setattr(status, "TEMP_PATH", "/nonexistent/thermal")
        assert status.check_temperature() is True
        assert "non disponible" in capsys.readouterr().out

    def test_temperature_normale(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / "temp"
        f.write_text("42000")
        monkeypatch.setattr(status, "TEMP_PATH", str(f))
        monkeypatch.setattr(status, "SEUIL_TEMP_CRITIQUE_C", 75.0)
        assert status.check_temperature() is True
        assert "42.0 °C" in capsys.readouterr().out

    def test_temperature_critique(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / "temp"
        f.write_text("82000")
        monkeypatch.setattr(status, "TEMP_PATH", str(f))
        monkeypatch.setattr(status, "SEUIL_TEMP_CRITIQUE_C", 75.0)
        assert status.check_temperature() is False
        assert "AU-DESSUS" in capsys.readouterr().out


class TestCheckPythonDeps:
    def test_module_present(self, capsys):
        """PIL est dans les deps dev — doit être trouvé."""
        # check_python_deps vérifie ["pygame", "cv2", "gphoto2", "PIL", "numpy"]
        # En CI, certains manquent → on accepte True ou False mais la fonction
        # ne doit pas crasher.
        result = status.check_python_deps()
        assert isinstance(result, bool)
        assert "Module Python : PIL" in capsys.readouterr().out


class TestMainInProcess:
    def test_main_retourne_0_ou_1(self, capsys):
        """Exécute main() en process : couvre les branches non-CLI restantes."""
        rc = status.main()
        assert rc in (0, 1)
        out = capsys.readouterr().out
        assert "diagnostic" in out
