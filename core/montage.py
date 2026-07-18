"""montage.py — génération de montages photo via PIL.

Module pur (pas de pygame, pas de globals UI). Testable isolément.
Expose deux classes (MontageGenerator10x15, MontageGeneratorStrip) qui partagent
une base commune (MontageBase) et la fonction helper `charger_et_corriger`.

Sprint 4.2 + 4.6 : extrait des 4 fonctions historiques generer_preview_* /
generer_montage_* qui étaient dupliquées dans Photobooth_start.py.
"""
from __future__ import annotations

import os
import gc

from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import (
    PATH_TEMP,
    PATH_MISE_EN_PAGE_10X15,
    PATH_MISE_EN_PAGE_STRIP,
    PATH_PRINT_STRIP,
    PREFIXE_PRINT_10X15, PREFIXE_PRINT_STRIP,
    BG_10X15_FILE, OVERLAY_10X15,
    BG_STRIPS_FILE, OVERLAY_STRIPS,
    MONTAGE_10X15_SIZE, MONTAGE_STRIP_SIZE, STRIP_ROTATION_DEGREES,
    STRIP_PHOTO_RATIO, STRIP_MARGE_HAUT, STRIP_MARGE_LATERALE, STRIP_ESPACE_PHOTOS,
    MONTAGE_10X15_PREVIEW_SIZE, MONTAGE_10X15_PREVIEW_QUALITY,
    MONTAGE_10X15_FINAL_PHOTO_FIT, MONTAGE_10X15_FINAL_PHOTO_OFFSET,
    MONTAGE_10X15_FINAL_QUALITY,
    STRIP_PREVIEW_PHOTO_LARGEUR, STRIP_PREVIEW_ESPACEMENT, STRIP_PREVIEW_MARGE_HB,
    STRIP_PREVIEW_CANVAS_LARGEUR, STRIP_PREVIEW_THUMBNAIL_MAX, STRIP_PREVIEW_QUALITY,
    STRIP_FINAL_QUALITY,
    POLICE_FICHIER,
    WATERMARK_ENABLED, WATERMARK_TEXT, WATERMARK_COULEUR, WATERMARK_ALPHA,
    WATERMARK_TAILLE_10X15, WATERMARK_TAILLE_STRIP,
    WATERMARK_POSITION_10X15, WATERMARK_POSITION_STRIP, WATERMARK_MARGE_PX,
    GRAIN_ENABLED, GRAIN_INTENSITE, GRAIN_SIGMA,
    PRINT_CALIB_TOP, PRINT_CALIB_BOTTOM, PRINT_CALIB_LEFT, PRINT_CALIB_RIGHT,
)
from core.mise_en_page import (
    MiseEnPage10x15,
    MiseEnPageStrip,
    charger_mise_en_page,
    charger_mise_en_page_strip,
)


def charger_et_corriger(
    chemin: str,
    rotation_forcee: float = 0,
    taille_cible: tuple[int, int] | None = None,
) -> Image.Image:
    """Charge une image en RGB, avec décodage JPEG réduit si possible."""
    with Image.open(chemin) as src:
        if taille_cible is not None:
            src.draft("RGB", taille_cible)
        img = src.convert("RGB")
    if rotation_forcee != 0:
        img = img.rotate(rotation_forcee, expand=True)
    return img


class MontageBase:
    """Helpers partagés pour la génération de montages PIL."""

    _transformed_asset_cache: dict[tuple, tuple[int, int, Image.Image]] = {}

    @classmethod
    def _charger_asset_transforme(
        cls,
        chemin: str,
        mode: str,
        size: tuple[int, int],
        rotation: float,
        redresser_si_horizontal: bool,
    ) -> Image.Image:
        """Charge, oriente et redimensionne un asset, et le met en cache."""
        stat = os.stat(chemin)
        key = (chemin, mode, size, rotation, redresser_si_horizontal)
        cache = cls._transformed_asset_cache.get(key)
        signature = (stat.st_mtime_ns, stat.st_size)
        if cache is not None and cache[:2] == signature:
            return cache[2].copy()

        with Image.open(chemin) as src:
            img = src.convert(mode)
        if redresser_si_horizontal and img.width > img.height:
            img = img.rotate(90, expand=True)
        if rotation:
            img = img.rotate(rotation)
        img = img.resize(size)

        if cache is not None:
            cache[2].close()
        cls._transformed_asset_cache[key] = (*signature, img)
        return img.copy()

    @classmethod
    def _canvas_depuis_bg_ou_blanc(
        cls,
        bg_path: str,
        size: tuple,
        rotation: float = 0,
        redresser_si_horizontal: bool = False,
    ) -> Image.Image:
        """Charge le fond ou retourne une toile blanche.
        `redresser_si_horizontal` : si le fond source est paysage, le met debout
        (rotation 90° expand) avant d'appliquer `rotation` et le resize final."""
        if bg_path and os.path.exists(bg_path) and os.path.isfile(bg_path):
            return cls._charger_asset_transforme(
                bg_path, "RGB", size, rotation, redresser_si_horizontal
            )
        return Image.new("RGB", size, "white")

    @classmethod
    def _coller_overlay(
        cls,
        canvas: Image.Image,
        overlay_path: str,
        size: tuple,
        rotation: float = 0,
        redresser_si_horizontal: bool = False,
    ) -> None:
        """Applique l'overlay RGBA si le fichier existe."""
        if not (overlay_path and os.path.exists(overlay_path)):
            return
        ov = cls._charger_asset_transforme(
            overlay_path, "RGBA", size, rotation, redresser_si_horizontal
        )
        canvas.paste(ov, (0, 0), ov)

    @staticmethod
    def _chemin_prev() -> str:
        return os.path.join(PATH_TEMP, "montage_prev.jpg")

    @staticmethod
    def _appliquer_watermark(canvas: Image.Image, taille: int, position: str) -> None:
        """Ajoute un texte semi-transparent à `canvas` (in-place) selon `position`.
        No-op si `WATERMARK_ENABLED=False` ou `WATERMARK_TEXT` vide."""
        if not WATERMARK_ENABLED or not WATERMARK_TEXT:
            return

        try:
            font = ImageFont.truetype(POLICE_FICHIER, taille)
        except (OSError, IOError):
            font = ImageFont.load_default()

        # Calque RGBA temporaire pour gérer l'alpha proprement
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)

        bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
        txt_w = bbox[2] - bbox[0]
        txt_h = bbox[3] - bbox[1]
        marge = WATERMARK_MARGE_PX

        if position == "bottom-left":
            x = marge
        elif position == "bottom-center":
            x = (canvas.width - txt_w) // 2
        else:  # bottom-right (défaut)
            x = canvas.width - txt_w - marge
        y = canvas.height - txt_h - marge - bbox[1]

        r, g, b = WATERMARK_COULEUR[:3]
        draw.text((x, y), WATERMARK_TEXT, font=font, fill=(r, g, b, WATERMARK_ALPHA))

        composite = Image.alpha_composite(canvas.convert("RGBA"), layer)
        canvas.paste(composite.convert("RGB"))

    @staticmethod
    def _appliquer_grain(canvas: Image.Image) -> None:
        """Superpose un bruit gaussien (film grain) sur `canvas` (in-place).
        No-op si `GRAIN_ENABLED=False` ou `GRAIN_INTENSITE <= 0`.

        Le bruit est généré en niveaux de gris puis projeté sur les 3 canaux,
        ce qui donne une texture argentique neutre (pas de dérive de teinte).
        Appelé après watermark pour que le grain s'applique aussi au texte."""
        if not GRAIN_ENABLED or GRAIN_INTENSITE <= 0:
            return
        alpha = min(GRAIN_INTENSITE, 100) / 100.0
        noise_l = Image.effect_noise(canvas.size, GRAIN_SIGMA)
        noise_rgb = Image.merge("RGB", (noise_l, noise_l, noise_l))
        blended = Image.blend(canvas, noise_rgb, alpha)
        canvas.paste(blended)


class MontageGenerator10x15(MontageBase):
    """Montage grand format 10x15. Preview = 900×600 simple ; final = 1800×1200 avec BG+overlay.
    Toutes les dimensions sont configurables dans config.py (section Sprint 4.8)."""

    PREVIEW_SIZE         = MONTAGE_10X15_PREVIEW_SIZE
    PREVIEW_QUALITY      = MONTAGE_10X15_PREVIEW_QUALITY

    FINAL_SIZE           = MONTAGE_10X15_SIZE
    FINAL_PHOTO_FIT      = MONTAGE_10X15_FINAL_PHOTO_FIT
    FINAL_PHOTO_OFFSET   = MONTAGE_10X15_FINAL_PHOTO_OFFSET
    FINAL_QUALITY        = MONTAGE_10X15_FINAL_QUALITY

    @classmethod
    def _mise_en_page_active(cls) -> MiseEnPage10x15:
        defaut = MiseEnPage10x15(
            x=cls.FINAL_PHOTO_OFFSET[0],
            y=cls.FINAL_PHOTO_OFFSET[1],
            largeur=cls.FINAL_PHOTO_FIT[0],
            hauteur=cls.FINAL_PHOTO_FIT[1],
        )
        return charger_mise_en_page(PATH_MISE_EN_PAGE_10X15, defaut, cls.FINAL_SIZE)

    @classmethod
    def _composer(
        cls,
        chemin_photo: str,
        taille_sortie: tuple[int, int] | None = None,
        resampling: Image.Resampling = Image.Resampling.LANCZOS,
    ) -> Image.Image:
        """Compose fond → photo → overlay avec la géométrie active."""
        taille_sortie = taille_sortie or cls.FINAL_SIZE
        canvas = cls._canvas_depuis_bg_ou_blanc(BG_10X15_FILE, taille_sortie)
        mise_en_page = cls._mise_en_page_active()
        echelle_x = taille_sortie[0] / cls.FINAL_SIZE[0]
        echelle_y = taille_sortie[1] / cls.FINAL_SIZE[1]
        zone = (
            max(1, round(mise_en_page.largeur * echelle_x)),
            max(1, round(mise_en_page.hauteur * echelle_y)),
        )
        position = (
            round(mise_en_page.x * echelle_x),
            round(mise_en_page.y * echelle_y),
        )
        img_brute = charger_et_corriger(chemin_photo, taille_cible=zone)
        photo_fit = ImageOps.fit(
            img_brute,
            zone,
            resampling,
        )
        canvas.paste(photo_fit, position)
        cls._coller_overlay(canvas, OVERLAY_10X15, taille_sortie)
        return canvas

    @classmethod
    def preview(cls, photos: list) -> str:
        path_prev = cls._chemin_prev()
        apercu = cls._composer(photos[0], taille_sortie=cls.PREVIEW_SIZE, resampling=Image.Resampling.BILINEAR)
        apercu.save(path_prev, quality=cls.PREVIEW_QUALITY)
        return path_prev

    @classmethod
    def final(cls, photos: list, id_session: str) -> str:
        path_hd = os.path.join(PATH_TEMP, f"{PREFIXE_PRINT_10X15}_{id_session}.jpg")
        canvas = cls._composer(photos[0])
        cls._appliquer_watermark(canvas, WATERMARK_TAILLE_10X15, WATERMARK_POSITION_10X15)
        cls._appliquer_grain(canvas)
        canvas.save(path_hd, quality=cls.FINAL_QUALITY)
        canvas.close()
        gc.collect()
        return path_hd


class MontageGeneratorStrip(MontageBase):
    """Montage bandelettes verticales. Preview = thumbnail 400×800 ; final = 600×1800
    avec BG/overlay rotés 180° (imprimante tête-bêche)."""

    # Preview (écran) — dimensions configurables dans config.py
    PREVIEW_PHOTO_LARGEUR   = STRIP_PREVIEW_PHOTO_LARGEUR
    PREVIEW_ESPACEMENT      = STRIP_PREVIEW_ESPACEMENT
    PREVIEW_MARGE_HAUT_BAS  = STRIP_PREVIEW_MARGE_HB
    PREVIEW_CANEVAS_LARGEUR = STRIP_PREVIEW_CANVAS_LARGEUR
    PREVIEW_THUMBNAIL_MAX   = STRIP_PREVIEW_THUMBNAIL_MAX
    PREVIEW_QUALITY         = STRIP_PREVIEW_QUALITY

    # Final (impression)
    FINAL_SIZE     = MONTAGE_STRIP_SIZE
    FINAL_QUALITY  = STRIP_FINAL_QUALITY
    FINAL_ROTATION = STRIP_ROTATION_DEGREES

    @classmethod
    def _mise_en_page_defaut(cls) -> MiseEnPageStrip:
        photo_w = cls.FINAL_SIZE[0] - (2 * STRIP_MARGE_LATERALE)
        photo_h = int(photo_w * float(STRIP_PHOTO_RATIO))
        return MiseEnPageStrip(photos=tuple(
            MiseEnPage10x15(
                x=STRIP_MARGE_LATERALE,
                y=STRIP_MARGE_HAUT + i * (photo_h + STRIP_ESPACE_PHOTOS),
                largeur=photo_w,
                hauteur=photo_h,
            )
            for i in range(3)
        ))

    @classmethod
    def _mise_en_page_active(cls) -> MiseEnPageStrip:
        return charger_mise_en_page_strip(
            PATH_MISE_EN_PAGE_STRIP, cls._mise_en_page_defaut(), cls.FINAL_SIZE,
        )

    @classmethod
    def _composer(
        cls,
        photos: list,
        taille_sortie: tuple[int, int] | None = None,
        resampling: Image.Resampling = Image.Resampling.LANCZOS,
    ) -> Image.Image:
        """Compose fond → trois photos → overlay avec la géométrie active."""
        taille_sortie = taille_sortie or cls.FINAL_SIZE
        canvas = cls._canvas_depuis_bg_ou_blanc(
            os.path.abspath(BG_STRIPS_FILE), taille_sortie,
            rotation=cls.FINAL_ROTATION, redresser_si_horizontal=True,
        )
        mise_en_page = cls._mise_en_page_active()
        echelle_x = taille_sortie[0] / cls.FINAL_SIZE[0]
        echelle_y = taille_sortie[1] / cls.FINAL_SIZE[1]
        for chemin, zone in zip(photos[:3], mise_en_page.photos):
            taille_photo = (
                max(1, round(zone.largeur * echelle_x)),
                max(1, round(zone.hauteur * echelle_y)),
            )
            position = (round(zone.x * echelle_x), round(zone.y * echelle_y))
            img = charger_et_corriger(chemin, taille_cible=taille_photo)
            img_fit = ImageOps.fit(
                img, taille_photo, resampling,
            )
            canvas.paste(img_fit, position)
        cls._coller_overlay(
            canvas, OVERLAY_STRIPS, taille_sortie,
            rotation=cls.FINAL_ROTATION, redresser_si_horizontal=True,
        )
        return canvas

    @classmethod
    def preview(cls, photos: list) -> str:
        path_prev = cls._chemin_prev()
        facteur = min(
            cls.PREVIEW_THUMBNAIL_MAX[0] / cls.FINAL_SIZE[0],
            cls.PREVIEW_THUMBNAIL_MAX[1] / cls.FINAL_SIZE[1],
            1.0,
        )
        taille_preview = (
            max(1, round(cls.FINAL_SIZE[0] * facteur)),
            max(1, round(cls.FINAL_SIZE[1] * facteur)),
        )
        bande_v = cls._composer(photos, taille_sortie=taille_preview, resampling=Image.Resampling.BILINEAR)
        bande_v.save(path_prev, "JPEG", quality=cls.PREVIEW_QUALITY)
        return path_prev

    @classmethod
    def final(cls, photos: list, id_session: str) -> str:
        # --- 1. GÉNÉRATION DE LA BANDELETTE (CLEAN) ---
        
        canvas = cls._composer(photos)
        cls._appliquer_watermark(canvas, WATERMARK_TAILLE_STRIP, WATERMARK_POSITION_STRIP)
        cls._appliquer_grain(canvas)

        # --- 2. SAUVEGARDE DE LA BANDELETTE "CLEAN" ---
        path_clean = os.path.join(PATH_PRINT_STRIP, f"{PREFIXE_PRINT_STRIP}_{id_session}_CLEAN.jpg")
        os.makedirs(os.path.dirname(path_clean), exist_ok=True)
        canvas.save(path_clean, "JPEG", quality=cls.FINAL_QUALITY)

        # --- 3. CRÉATION DU MONTAGE 10x15 (CALIBRATION DNP) ---
        dir_ready = os.path.join(PATH_PRINT_STRIP, "READY_TO_PRINT")
        os.makedirs(dir_ready, exist_ok=True)
        path_ready = os.path.join(dir_ready, f"{PREFIXE_PRINT_STRIP}_{id_session}_READY_TO_PRINT.jpg")
        
        # Le canevas 10x15 final
        canvas_10x15 = Image.new("RGB", MONTAGE_10X15_SIZE, "white")
        
        # Calcul de la zone utile (le rectangle qui contient les deux bandes)
        utile_w = MONTAGE_10X15_SIZE[0] - PRINT_CALIB_LEFT - PRINT_CALIB_RIGHT
        utile_h = MONTAGE_10X15_SIZE[1] - PRINT_CALIB_TOP - PRINT_CALIB_BOTTOM
        
        # Bloc intermédiaire pour assembler les deux bandelettes
        bloc_photos = Image.new("RGB", (utile_w, utile_h), "white")
        h_par_bande = utile_h // 2
        
        # Préparation de la bandelette horizontale (600x1800 -> 1800x600)
        bande_horiz = canvas.rotate(90, expand=True)
        
        # Redimensionnement précis pour remplir la moitié de la zone utile
        bande_finale = bande_horiz.resize((utile_w, h_par_bande), Image.Resampling.LANCZOS)
        
        # Collage des deux bandelettes
        bloc_photos.paste(bande_finale, (0, 0))              # Bande du haut
        bloc_photos.paste(bande_finale, (0, h_par_bande))     # Bande du bas
        
        # Collage du bloc complet sur le 10x15 avec l'offset de calibration
        # On utilise RIGHT et BOTTOM pour compenser la rotation de l'imprimante
        canvas_10x15.paste(bloc_photos, (PRINT_CALIB_RIGHT, PRINT_CALIB_BOTTOM))

        # Sauvegarde avec qualité maximale et sans sous-échantillonnage (plus net)
        canvas_10x15.save(path_ready, "JPEG", quality=cls.FINAL_QUALITY, subsampling=0)

        # Libération explicite de la mémoire
        canvas.close()
        canvas_10x15.close()
        bloc_photos.close()
        bande_horiz.close()
        bande_finale.close()
        gc.collect()

        return path_ready
