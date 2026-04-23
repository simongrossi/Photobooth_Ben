"""montage.py — génération de montages photo via PIL.

Module pur (pas de pygame, pas de globals UI). Testable isolément.
Expose deux classes (MontageGenerator10x15, MontageGeneratorStrip) qui partagent
une base commune (MontageBase) et la fonction helper `charger_et_corriger`.

Sprint 4.2 + 4.6 : extrait des 4 fonctions historiques generer_preview_* /
generer_montage_* qui étaient dupliquées dans Photobooth_start.py.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import (
    PATH_TEMP,
    PREFIXE_PRINT_10X15, PREFIXE_PRINT_STRIP,
    BG_10X15_FILE, OVERLAY_10X15,
    BG_STRIPS_FILE, OVERLAY_STRIPS,
    MONTAGE_10X15_SIZE, MONTAGE_STRIP_SIZE, STRIP_ROTATION_DEGREES,
    STRIP_PHOTO_RATIO, STRIP_MARGE_HAUT, STRIP_MARGE_LATERALE, STRIP_ESPACE_PHOTOS,
    MONTAGE_10X15_PREVIEW_SIZE, MONTAGE_10X15_PREVIEW_PHOTO_FIT,
    MONTAGE_10X15_PREVIEW_PHOTO_OFFSET, MONTAGE_10X15_PREVIEW_QUALITY,
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
)


def charger_et_corriger(chemin: str, rotation_forcee: float = 0) -> Image.Image:
    """Charge une image JPEG et la retourne en RGB. `with` ferme le file handle."""
    with Image.open(chemin) as src:
        img = src.convert("RGB")
    if rotation_forcee != 0:
        img = img.rotate(rotation_forcee, expand=True)
    return img


class MontageBase:
    """Helpers partagés pour la génération de montages PIL."""

    @staticmethod
    def _canvas_depuis_bg_ou_blanc(
        bg_path: str, size: tuple, rotation: float = 0, redresser_si_horizontal: bool = False,
    ) -> Image.Image:
        """Charge le fond ou retourne une toile blanche.
        `redresser_si_horizontal` : si le fond source est paysage, le met debout
        (rotation 90° expand) avant d'appliquer `rotation` et le resize final."""
        if bg_path and os.path.exists(bg_path) and os.path.isfile(bg_path):
            with Image.open(bg_path) as src:
                canvas = src.convert("RGB")
            if redresser_si_horizontal and canvas.width > canvas.height:
                canvas = canvas.rotate(90, expand=True)
            if rotation:
                canvas = canvas.rotate(rotation)
            return canvas.resize(size)
        return Image.new("RGB", size, "white")

    @staticmethod
    def _coller_overlay(
        canvas: Image.Image, overlay_path: str, size: tuple,
        rotation: float = 0, redresser_si_horizontal: bool = False,
    ) -> None:
        """Applique l'overlay RGBA si le fichier existe."""
        if not (overlay_path and os.path.exists(overlay_path)):
            return
        with Image.open(overlay_path) as src:
            ov = src.convert("RGBA")
        if redresser_si_horizontal and ov.width > ov.height:
            ov = ov.rotate(90, expand=True)
        if rotation:
            ov = ov.rotate(rotation)
        ov = ov.resize(size)
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
    PREVIEW_PHOTO_FIT    = MONTAGE_10X15_PREVIEW_PHOTO_FIT
    PREVIEW_PHOTO_OFFSET = MONTAGE_10X15_PREVIEW_PHOTO_OFFSET
    PREVIEW_QUALITY      = MONTAGE_10X15_PREVIEW_QUALITY

    FINAL_SIZE           = MONTAGE_10X15_SIZE
    FINAL_PHOTO_FIT      = MONTAGE_10X15_FINAL_PHOTO_FIT
    FINAL_PHOTO_OFFSET   = MONTAGE_10X15_FINAL_PHOTO_OFFSET
    FINAL_QUALITY        = MONTAGE_10X15_FINAL_QUALITY

    @classmethod
    def preview(cls, photos: list) -> str:
        path_prev = cls._chemin_prev()
        canvas = Image.new("RGB", cls.PREVIEW_SIZE, "white")
        img_brute = charger_et_corriger(photos[0])
        photo_fit = ImageOps.fit(img_brute, cls.PREVIEW_PHOTO_FIT, Image.Resampling.LANCZOS)
        canvas.paste(photo_fit, cls.PREVIEW_PHOTO_OFFSET)
        canvas.save(path_prev, quality=cls.PREVIEW_QUALITY)
        return path_prev

    @classmethod
    def final(cls, photos: list, id_session: str) -> str:
        path_hd = os.path.join(PATH_TEMP, f"{PREFIXE_PRINT_10X15}_{id_session}.jpg")
        canvas = cls._canvas_depuis_bg_ou_blanc(BG_10X15_FILE, cls.FINAL_SIZE)
        img_brute = charger_et_corriger(photos[0])
        photo_fit = ImageOps.fit(img_brute, cls.FINAL_PHOTO_FIT, Image.Resampling.LANCZOS)
        canvas.paste(photo_fit, cls.FINAL_PHOTO_OFFSET)
        cls._coller_overlay(canvas, OVERLAY_10X15, cls.FINAL_SIZE)
        cls._appliquer_watermark(canvas, WATERMARK_TAILLE_10X15, WATERMARK_POSITION_10X15)
        cls._appliquer_grain(canvas)
        canvas.save(path_hd, quality=cls.FINAL_QUALITY)
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
    def preview(cls, photos: list) -> str:
        path_prev = cls._chemin_prev()
        l_p = cls.PREVIEW_PHOTO_LARGEUR
        ratio = float(STRIP_PHOTO_RATIO)
        h_p = int(l_p * ratio)
        espacement = cls.PREVIEW_ESPACEMENT
        marge_hb = cls.PREVIEW_MARGE_HAUT_BAS
        hauteur_totale = (h_p * 3) + (espacement * 2) + (marge_hb * 2)

        bande_v = Image.new("RGB", (cls.PREVIEW_CANEVAS_LARGEUR, hauteur_totale), "white")
        offset_x = (cls.PREVIEW_CANEVAS_LARGEUR - l_p) // 2

        for i in range(min(len(photos), 3)):
            img = charger_et_corriger(photos[i])
            img_fit = ImageOps.fit(img, (l_p, h_p), Image.Resampling.LANCZOS)
            pos_y = marge_hb + i * (h_p + espacement)
            bande_v.paste(img_fit, (offset_x, pos_y))

        bande_v.thumbnail(cls.PREVIEW_THUMBNAIL_MAX, Image.Resampling.LANCZOS)
        bande_v.save(path_prev, "JPEG", quality=cls.PREVIEW_QUALITY)
        return path_prev

    @classmethod
    def final(cls, photos: list, id_session: str) -> str:
        path_hd = os.path.join(PATH_TEMP, f"{PREFIXE_PRINT_STRIP}_{id_session}.jpg")

        # Fond : redressement si horizontal, puis rotation 180° (imprimante tête-bêche)
        canvas = cls._canvas_depuis_bg_ou_blanc(
            BG_STRIPS_FILE, cls.FINAL_SIZE,
            rotation=cls.FINAL_ROTATION, redresser_si_horizontal=True,
        )

        marge_haut = STRIP_MARGE_HAUT
        marge_lat = STRIP_MARGE_LATERALE
        espace_entre = STRIP_ESPACE_PHOTOS
        photo_w = cls.FINAL_SIZE[0] - (2 * marge_lat)
        photo_h = int(photo_w * float(STRIP_PHOTO_RATIO))

        for i in range(min(len(photos), 3)):
            img = charger_et_corriger(photos[i])
            img_fit = ImageOps.fit(img, (photo_w, photo_h), Image.Resampling.LANCZOS)
            pos_y = marge_haut + i * (photo_h + espace_entre)
            canvas.paste(img_fit, (marge_lat, pos_y))

        cls._coller_overlay(
            canvas, OVERLAY_STRIPS, cls.FINAL_SIZE,
            rotation=cls.FINAL_ROTATION, redresser_si_horizontal=True,
        )
        cls._appliquer_watermark(canvas, WATERMARK_TAILLE_STRIP, WATERMARK_POSITION_STRIP)
        cls._appliquer_grain(canvas)

        canvas.save(path_hd, "JPEG", quality=cls.FINAL_QUALITY)
        return path_hd
