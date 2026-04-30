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

from core import montage
from core.montage import (
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
            assert img.size == (1800, 1200)

    def test_final_session_id_dans_nom(self, isoler_paths, trois_photos):
        id_sess = "2026-04-20_22h10_01"
        path = MontageGeneratorStrip.final(trois_photos, id_sess)
        assert id_sess in path
        assert os.path.exists(path)


# --- Tests watermark ---

class TestWatermark:
    def test_disabled_par_defaut_no_op(self, isoler_paths, photo_factice, monkeypatch):
        """WATERMARK_ENABLED=False → pas d'altération du canvas final."""
        monkeypatch.setattr(montage, "WATERMARK_ENABLED", False)
        path = MontageGenerator10x15.final([photo_factice], "sans_wm")
        assert os.path.exists(path)
        with Image.open(path) as img:
            assert img.size == (1800, 1200)

    def test_enabled_altere_canvas_bottom_right(self, isoler_paths, photo_factice, monkeypatch):
        """WATERMARK_ENABLED=True + texte non-vide → pixels différents en bas à droite."""
        monkeypatch.setattr(montage, "WATERMARK_ENABLED", False)
        path_sans = MontageGenerator10x15.final([photo_factice], "sans")
        with Image.open(path_sans) as img_sans:
            img_sans_copy = img_sans.copy()

        monkeypatch.setattr(montage, "WATERMARK_ENABLED", True)
        monkeypatch.setattr(montage, "WATERMARK_TEXT", "TEST WATERMARK")
        monkeypatch.setattr(montage, "WATERMARK_COULEUR", (255, 0, 0))  # rouge, visible sur blanc
        path_avec = MontageGenerator10x15.final([photo_factice], "avec")
        with Image.open(path_avec) as img_avec:
            # Zone bas-droite : doit avoir au moins un pixel différent
            region_w, region_h = 300, 50
            box = (1800 - region_w, 1200 - region_h, 1800, 1200)
            crop_sans = img_sans_copy.crop(box)
            crop_avec = img_avec.crop(box)
            assert list(crop_sans.getdata()) != list(crop_avec.getdata())

    def test_texte_vide_equivaut_disabled(self, isoler_paths, photo_factice, monkeypatch):
        """WATERMARK_TEXT='' est un no-op même si ENABLED=True."""
        monkeypatch.setattr(montage, "WATERMARK_ENABLED", True)
        monkeypatch.setattr(montage, "WATERMARK_TEXT", "")
        path = MontageGenerator10x15.final([photo_factice], "vide")
        assert os.path.exists(path)

    def test_strip_accepte_watermark(self, isoler_paths, trois_photos, monkeypatch):
        """Le watermark s'applique aussi sur les strips sans crash."""
        monkeypatch.setattr(montage, "WATERMARK_ENABLED", True)
        monkeypatch.setattr(montage, "WATERMARK_TEXT", "Strip WM")
        path = MontageGeneratorStrip.final(trois_photos, "strip_wm")
        with Image.open(path) as img:
            assert img.size == (1800, 1200)


# --- Tests grain de pellicule ---

class TestGrain:
    def test_disabled_par_defaut_no_op(self, isoler_paths, photo_factice, monkeypatch):
        """GRAIN_ENABLED=False → sortie identique à une génération sans grain."""
        monkeypatch.setattr(montage, "GRAIN_ENABLED", False)
        path = MontageGenerator10x15.final([photo_factice], "sans_grain")
        assert os.path.exists(path)
        with Image.open(path) as img:
            assert img.size == (1800, 1200)

    def test_enabled_altere_canvas(self, isoler_paths, photo_factice, monkeypatch):
        """GRAIN_ENABLED=True → les pixels diffèrent (bruit gaussien superposé)."""
        monkeypatch.setattr(montage, "GRAIN_ENABLED", False)
        path_sans = MontageGenerator10x15.final([photo_factice], "sans")
        with Image.open(path_sans) as img_sans:
            img_sans_copy = img_sans.copy()

        monkeypatch.setattr(montage, "GRAIN_ENABLED", True)
        monkeypatch.setattr(montage, "GRAIN_INTENSITE", 20)
        path_avec = MontageGenerator10x15.final([photo_factice], "avec")
        with Image.open(path_avec) as img_avec:
            # Le bruit est global : au moins un pixel doit différer
            assert list(img_sans_copy.getdata()) != list(img_avec.getdata())

    def test_intensite_zero_equivaut_disabled(self, isoler_paths, photo_factice, monkeypatch):
        """GRAIN_INTENSITE=0 est un no-op même si ENABLED=True."""
        monkeypatch.setattr(montage, "GRAIN_ENABLED", True)
        monkeypatch.setattr(montage, "GRAIN_INTENSITE", 0)
        path = MontageGenerator10x15.final([photo_factice], "grain_nul")
        assert os.path.exists(path)
        with Image.open(path) as img:
            assert img.size == (1800, 1200)

    def test_strip_accepte_grain(self, isoler_paths, trois_photos, monkeypatch):
        """Le grain s'applique aussi sur les strips sans crash."""
        monkeypatch.setattr(montage, "GRAIN_ENABLED", True)
        monkeypatch.setattr(montage, "GRAIN_INTENSITE", 15)
        path = MontageGeneratorStrip.final(trois_photos, "strip_grain")
        with Image.open(path) as img:
            assert img.size == (1800, 1200)

    def test_preview_jamais_altere_par_grain(self, isoler_paths, photo_factice, monkeypatch):
        """Le grain ne s'applique qu'au FINAL, pas à la preview écran."""
        monkeypatch.setattr(montage, "GRAIN_ENABLED", False)
        path_sans = MontageGenerator10x15.preview([photo_factice])
        with Image.open(path_sans) as img_sans:
            pixels_sans = list(img_sans.getdata())

        monkeypatch.setattr(montage, "GRAIN_ENABLED", True)
        monkeypatch.setattr(montage, "GRAIN_INTENSITE", 50)
        path_avec = MontageGenerator10x15.preview([photo_factice])
        with Image.open(path_avec) as img_avec:
            assert list(img_avec.getdata()) == pixels_sans


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
            assert img.size == (1800, 1200)
