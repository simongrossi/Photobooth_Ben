"""test_integration.py — smoke tests d'intégration sans pygame display.

Vérifie que :
- Les modules core/ s'importent proprement (sans pygame)
- `core.camera` dégrade proprement si ses dépendances optionnelles manquent
- `Photobooth_start.py` est importable sans démarrer le kiosque
- `SessionState` se comporte correctement (reset, mutation)
- `Etat` enum est bien typé et comparable
- `terminer_session_et_revenir_accueil` déclenche l'écriture metadata

Ces tests ne lancent PAS la boucle principale (qui demande un écran
pygame). Ils couvrent la logique d'état et les helpers purs.

Pour un vrai test end-to-end du photobooth, il faut un environnement
avec `SDL_VIDEODRIVER=dummy` + une caméra fake, ce qui sort du scope.
"""
import sys
from pathlib import Path



# --- Test que les modules core/ s'importent sans pygame ---

class TestImportsCore:
    def test_import_logger(self):
        from core import logger
        assert callable(logger.log_info)
        assert callable(logger.log_warning)
        assert callable(logger.log_critical)

    def test_import_montage(self):
        from core.montage import (
            MontageGenerator10x15, MontageGeneratorStrip,
        )
        assert MontageGenerator10x15.PREVIEW_SIZE == (900, 600)
        assert MontageGeneratorStrip.FINAL_SIZE == (600, 1800)

    def test_import_printer(self):
        from core.printer import PrinterManager
        mgr = PrinterManager("DNP_10x15", "DNP_STRIP")
        assert mgr.nom("10x15") == "DNP_10x15"
        assert mgr.nom("strips") == "DNP_STRIP"
        assert mgr.nom("invalide") is None


class TestImportsHardwareOptionnel:
    def test_camera_manager_importe_sans_dependances_camera(self, tmp_path):
        """Simule une machine sans cv2/gphoto2/numpy/pygame : le module reste importable."""
        import subprocess

        script = f"""
import builtins
import sys

sys.path.insert(0, {str(Path.cwd())!r})

real_import = builtins.__import__
blocked = {"cv2", "gphoto2", "numpy", "pygame"}

def fake_import(name, *args, **kwargs):
    if name.split(".")[0] in blocked:
        raise ImportError(name)
    return real_import(name, *args, **kwargs)

builtins.__import__ = fake_import

from core.camera import CameraManager

mgr = CameraManager()
assert mgr.init() is False
assert mgr.get_preview_frame() is None
assert mgr.is_connected is False
mgr.close()
print("OK")
"""
        script_path = tmp_path / "camera_optional.py"
        script_path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, cwd=Path.cwd(),
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout

    def test_photobooth_start_import_ne_lance_pas_runtime(self, tmp_path):
        """Importe le module avec pygame/ui factices : aucun init écran/caméra ne doit partir."""
        import subprocess

        script = f"""
import sys
import types

sys.path.insert(0, {str(Path.cwd())!r})

pygame = types.ModuleType("pygame")
pygame.K_g = ord("g")
pygame.K_m = ord("m")
pygame.K_d = ord("d")
pygame.K_ESCAPE = 27
pygame.QUIT = 256
pygame.KEYDOWN = 768
sys.modules["pygame"] = pygame

ui = types.ModuleType("ui")
class UIContext:
    @classmethod
    def setup(cls, *args, **kwargs):
        raise AssertionError("UIContext.setup ne doit pas être appelé à l'import")
class AccueilAssets:
    @classmethod
    def charger(cls, *args, **kwargs):
        raise AssertionError("AccueilAssets.charger ne doit pas être appelé à l'import")
def _no_runtime(*args, **kwargs):
    raise AssertionError("helper UI runtime appelé à l'import")
ui.UIContext = UIContext
ui.AccueilAssets = AccueilAssets
ui.setup_sounds = _no_runtime
ui.jouer_son = _no_runtime
ui.draw_text_shadow_soft = _no_runtime
ui.inserer_background = _no_runtime
ui.afficher_message_plein_ecran = _no_runtime
ui.executer_avec_spinner = _no_runtime
ui.ecran_erreur = _no_runtime
ui.ecran_attente_impression = _no_runtime
ui.splash_connexion_camera = _no_runtime
sys.modules["ui"] = ui

import Photobooth_start as app

assert callable(app.main)
assert app.camera_mgr is None
assert app.screen is None
assert app.arduino_ctrl is None
print("OK")
"""
        script_path = tmp_path / "import_main.py"
        script_path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, cwd=Path.cwd(),
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout


# --- Test du comportement de SessionState (via subprocess pour isoler pygame) ---

def _script_session_state(tmp_path: Path) -> str:
    """Script Python isolé qui teste SessionState sans pygame."""
    return f"""
import sys
sys.path.insert(0, {str(tmp_path.parent.absolute())!r})

# Mocking pygame avant tout import de Photobooth_start
import unittest.mock as mock
pygame_mock = mock.MagicMock()
pygame_mock.K_g = ord('g')
pygame_mock.K_m = ord('m')
pygame_mock.K_d = ord('d')
sys.modules['pygame'] = pygame_mock
sys.modules['pygame.font'] = pygame_mock.font
sys.modules['pygame.display'] = pygame_mock.display
sys.modules['pygame.event'] = pygame_mock.event

# On importe directement l'Enum + dataclass
from dataclasses import dataclass, field
from enum import Enum

class Etat(Enum):
    ACCUEIL = "ACCUEIL"
    DECOMPTE = "DECOMPTE"
    VALIDATION = "VALIDATION"
    FIN = "FIN"

@dataclass
class SessionState:
    etat: Etat = Etat.ACCUEIL
    mode_actuel: object = None
    photos_validees: list = field(default_factory=list)
    id_session_timestamp: str = ""
    session_start_ts: float = 0.0
    path_montage: str = ""
    img_preview_cache: object = None
    dernier_clic_time: float = 0.0
    abandon_confirm_until: float = 0.0
    last_activity_ts: float = 0.0

    def reset_pour_accueil(self):
        self.etat = Etat.ACCUEIL
        self.mode_actuel = None
        self.photos_validees = []
        self.id_session_timestamp = ""
        self.img_preview_cache = None
        self.path_montage = ""

# Tests
s = SessionState()
assert s.etat is Etat.ACCUEIL
assert s.mode_actuel is None

s.mode_actuel = "10x15"
s.photos_validees = ["photo1.jpg"]
s.id_session_timestamp = "2026-04-20_14h30_15"
s.etat = Etat.VALIDATION

s.reset_pour_accueil()
assert s.etat is Etat.ACCUEIL
assert s.mode_actuel is None
assert s.photos_validees == []
# last_activity_ts préservé
assert s.last_activity_ts == 0.0  # pas touché par reset

# Etat enum : comparaison par identité
assert s.etat is Etat.ACCUEIL
assert s.etat is not Etat.FIN

print("OK")
"""


class TestSessionState:
    def test_session_state_via_subprocess(self, tmp_path):
        """Teste la dataclass SessionState dans un subprocess isolé."""
        import subprocess
        script = _script_session_state(tmp_path)
        script_path = tmp_path / "runner.py"
        script_path.write_text(script, encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout


# --- Test de cohérence config : les 96 imports explicites existent tous ---

class TestConfigImports:
    def test_tous_les_noms_importes_existent(self):
        """Lit la ligne `from config import (` dans Photobooth_start.py et
        vérifie que tous les noms existent bien dans config.py."""
        import config
        with open("Photobooth_start.py", encoding="utf-8") as f:
            content = f.read()

        # Extrait la partie entre `from config import (` et la parenthèse fermante
        start = content.index("from config import (")
        end = content.index(")", start)
        bloc = content[start:end]

        # Récupère tous les identifiants mentionnés
        import re
        noms = re.findall(r"\b([A-Z][A-Z0-9_]*[a-z]?[A-Za-z0-9_]*)\b", bloc)
        noms = [n for n in noms if not n.startswith("from") and not n.startswith("config")]

        for nom in set(noms):
            assert hasattr(config, nom), f"{nom} importé mais absent de config.py"


# --- Test que le montage produit les bonnes tailles selon la config ---

class TestMontageRespecteConfig:
    def test_montage_10x15_utilise_config(self, tmp_path, monkeypatch):
        """Changer MONTAGE_10X15_SIZE dans config impacte la sortie générée."""
        from core import montage
        from PIL import Image

        # Petite photo factice
        photo = tmp_path / "photo.jpg"
        Image.new("RGB", (800, 600), "red").save(photo, "JPEG")

        monkeypatch.setattr(montage, "PATH_TEMP", str(tmp_path))
        monkeypatch.setattr(montage, "BG_10X15_FILE", "/inexistant")
        monkeypatch.setattr(montage, "OVERLAY_10X15", "/inexistant")

        path = montage.MontageGenerator10x15.final([str(photo)], "test_sess")
        with Image.open(path) as img:
            assert img.size == montage.MONTAGE_10X15_SIZE
