"""test_montage.py — tests unitaires de montage.py.

Couvre les classes MontageGenerator10x15 et MontageGeneratorStrip + le helper
`charger_et_corriger`. Les dépendances disque (PATH_TEMP, BG_*, OVERLAY_*) sont
monkeypatchées pour isoler les tests du système de fichiers réel.

Usage : pytest test_montage.py -v
Sprint 5.3 — devient possible depuis que montage.py est extrait (Sprint 4.2/4.6).
"""
import os
import pytest
from PIL import Image

import montage
from montage import (
    MontageBase, MontageGenerator10x15, MontageGeneratorStrip,
    charger_et_corriger,
)


# --- Fixtures ---

@pytest.fixture
def tmp_path_str(tmp_path):
    """tmp_path en str (compatible avec os.path.join dans les classes)."""
    return str(tmp_path)


@pytest.fixture
def photo_factice(tmp_path_str):
    """Crée une photo JPEG 800×600 RGB et retourne son chemin."""
    chemin = os.path.join(tmp_path_str, "photo_test.jpg")
    img = Image.new("RGB", (800, 600), color=(128, 200, 255))
    img.save(chemin, "JPEG", quality=85)
    return chemin


@pytest.fixture
def trois_photos(tmp_path_str):
    """Crée 3 photos distinctes (couleurs différentes) pour tester les strips."""
    chemins = []
    couleurs = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    for i, couleur in enumerate(couleurs):
        chemin = os.path.join(tmp_path_str, f"photo_{i}.jpg")
        Image.new("RGB", (800, 600), color=couleur).save(chemin, "JPEG", quality=85)
        chemins.append(chemin)
    return chemins


@pytest.fixture
def isoler_paths(monkeypatch, tmp_path_str):
    """Redirige PATH_TEMP + BG_*/OVERLAY_* vers tmp (évite de toucher le vrai disque)."""
    monkeypatch.setattr(montage, "PATH_TEMP", tmp_path_str)
    # BG / overlay absents → fallback canvas blanc (testé explicitement par ailleurs)
    monkeypatch.setattr(montage, "BG_10X15_FILE", "/inexistant/bg10x15.jpg")
    monkeypatch.setattr(montage, "OVERLAY_10X15", "/inexistant/ov10x15.png")
    monkeypatch.setattr(montage, "BG_STRIPS_FILE", "/inexistant/bg_strip.jpg")
    monkeypatch.setattr(montage, "OVERLAY_STRIPS", "/inexistant/ov_strip.png")
    return tmp_path_str


# --- Tests helper charger_et_corriger ---

class TestChargerEtCorriger:
    def test_retourne_image_rgb(self, photo_factice):
        img = charger_et_corriger(photo_factice)
        assert img.mode == "RGB"

    def test_dimensions_preservees_sans_rotation(self, photo_factice):
        img = charger_et_corriger(photo_factice)
        assert img.size == (800, 600)

    def test_rotation_90_inverse_dimensions(self, photo_factice):
        img = charger_et_corriger(photo_factice, rotation_forcee=90)
        assert img.size == (600, 800)  # expand=True swap w/h

    def test_erreur_sur_fichier_absent(self):
        with pytest.raises(FileNotFoundError):
            charger_et_corriger("/chemin/inexistant.jpg")


# --- Tests MontageBase._canvas_depuis_bg_ou_blanc ---

class TestCanvasDepuisBg:
    def test_bg_absent_retourne_canvas_blanc(self):
        canvas = MontageBase._canvas_depuis_bg_ou_blanc(
            "/inexistant.jpg", (400, 300),
        )
        assert canvas.size == (400, 300)
        assert canvas.mode == "RGB"
        # pixel blanc partout
        assert canvas.getpixel((0, 0)) == (255, 255, 255)

    def test_bg_present_redimensionne(self, tmp_path_str):
        bg_path = os.path.join(tmp_path_str, "bg.jpg")
        Image.new("RGB", (1000, 800), color=(50, 100, 150)).save(bg_path, "JPEG")
        canvas = MontageBase._canvas_depuis_bg_ou_blanc(bg_path, (200, 100))
        assert canvas.size == (200, 100)

    def test_redressement_si_horizontal(self, tmp_path_str):
        """Un BG 1000×500 (horizontal) doit être redressé (90°) avant le resize."""
        bg_path = os.path.join(tmp_path_str, "bg_h.jpg")
        Image.new("RGB", (1000, 500), color="red").save(bg_path, "JPEG")
        canvas = MontageBase._canvas_depuis_bg_ou_blanc(
            bg_path, (200, 400), redresser_si_horizontal=True,
        )
        assert canvas.size == (200, 400)


# --- Tests MontageGenerator10x15 ---

class TestMontageGenerator10x15:
    def test_preview_cree_fichier(self, isoler_paths, photo_factice):
        path = MontageGenerator10x15.preview([photo_factice])
        assert os.path.exists(path)
        assert path.endswith("montage_prev.jpg")

    def test_preview_dimensions(self, isoler_paths, photo_factice):
        path = MontageGenerator10x15.preview([photo_factice])
        with Image.open(path) as img:
            assert img.size == MontageGenerator10x15.PREVIEW_SIZE

    def test_final_cree_fichier_avec_session_id(self, isoler_paths, photo_factice):
        id_sess = "2026-04-20_14h30_15"
        path = MontageGenerator10x15.final([photo_factice], id_sess)
        assert os.path.exists(path)
        assert id_sess in path

    def test_final_dimensions_1800x1200(self, isoler_paths, photo_factice):
        path = MontageGenerator10x15.final([photo_factice], "test")
        with Image.open(path) as img:
            assert img.size == (1800, 1200)


# --- Tests MontageGeneratorStrip ---

class TestMontageGeneratorStrip:
    def test_preview_cree_fichier(self, isoler_paths, trois_photos):
        path = MontageGeneratorStrip.preview(trois_photos)
        assert os.path.exists(path)

    def test_preview_thumbnail_respecte_max(self, isoler_paths, trois_photos):
        """Le thumbnail final ne doit jamais dépasser PREVIEW_THUMBNAIL_MAX."""
        path = MontageGeneratorStrip.preview(trois_photos)
        with Image.open(path) as img:
            w_max, h_max = MontageGeneratorStrip.PREVIEW_THUMBNAIL_MAX
            assert img.size[0] <= w_max
            assert img.size[1] <= h_max

    def test_preview_tolere_moins_de_3_photos(self, isoler_paths, photo_factice):
        """Si on passe 1 seule photo, pas de crash (utile si retake a pop())."""
        path = MontageGeneratorStrip.preview([photo_factice])
        assert os.path.exists(path)

    def test_final_dimensions_600x1800(self, isoler_paths, trois_photos):
        path = MontageGeneratorStrip.final(trois_photos, "test_session")
        with Image.open(path) as img:
            assert img.size == (600, 1800)

    def test_final_session_id_dans_nom(self, isoler_paths, trois_photos):
        id_sess = "2026-04-20_22h10_01"
        path = MontageGeneratorStrip.final(trois_photos, id_sess)
        assert id_sess in path
        assert os.path.exists(path)


# --- Test de régression : dimensions config = dimensions générées ---

class TestCoherenceConfig:
    def test_dimensions_10x15_final_correspondent_config(self, isoler_paths, photo_factice):
        """Garantit que si on change MONTAGE_10X15_SIZE dans config, la sortie suit."""
        path = MontageGenerator10x15.final([photo_factice], "cohérence")
        with Image.open(path) as img:
            assert img.size == MontageGenerator10x15.FINAL_SIZE

    def test_dimensions_strip_final_correspondent_config(self, isoler_paths, trois_photos):
        path = MontageGeneratorStrip.final(trois_photos, "cohérence")
        with Image.open(path) as img:
            assert img.size == MontageGeneratorStrip.FINAL_SIZE
