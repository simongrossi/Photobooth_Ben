"""ui.py — contexte UI partagé + helpers pygame.

Sprint item 7 : extrait de Photobooth_start.py pour séparer la logique UI
(rendu pygame, écrans de transition, animations) de la machine d'état.

`UIContext` est un singleton initialisé au boot (après pygame.init() + fontes)
via `UIContext.setup()`. Les helpers y accèdent via `UIContext.screen`, etc.

Dépendances :
- pygame (affichage)
- PIL (conversion Image → Surface dans get_pygame_surf)
- logger (log_info/warning)
- montage (charger_et_corriger dans get_pygame_surf)
- camera_mgr passé en argument à splash_connexion_camera (injection explicite)
"""
import math
import os
import sys
import threading
import time

import pygame
from PIL import Image

from config import (
    WIDTH, HEIGHT, SPINNER_FPS,
    ANIM_COULEUR_TETE, ANIM_COULEUR_QUEUE, ANIM_TAILLE_ROUE,
    ANIM_V_BASE, ANIM_V_MAX_ADD, ANIM_FREQ,
    ANIM_NB_POINTS, ANIM_RAYON_POINT, ANIM_V_ELASTIQUE,
    COULEUR_FOND_LOADER,
    TXT_SPLASH_CAMERA, TXT_SPLASH_CAMERA_OK, TXT_SPLASH_CAMERA_FAIL,
    TIMEOUT_SPLASH_CAMERA,
    DUREE_ECRAN_ERREUR,
    TEMPS_ATTENTE_IMP,
    SON_BEEP, SON_BEEP_FINAL, SON_SHUTTER, SON_SUCCESS,
)
from core.logger import log_warning


# ========================================================================================================
# --- Contexte UI (singleton class) ---
# ========================================================================================================

class UIContext:
    """Singleton porteur de screen + clock + fontes. Initialisé au boot."""

    screen = None
    clock = None
    font_titre = None
    font_boutons = None
    font_bandeau = None
    font_decompte = None
    font_imp_texte = None
    font_imp_compteur = None

    @classmethod
    def setup(cls, screen, clock, font_titre, font_boutons, font_bandeau, font_decompte) -> None:
        """Initialise le contexte UI. À appeler une fois au boot, après pygame.init()
        et chargement des fontes, avant tout autre helper de ce module."""
        cls.screen = screen
        cls.clock = clock
        cls.font_titre = font_titre
        cls.font_boutons = font_boutons
        cls.font_bandeau = font_bandeau
        cls.font_decompte = font_decompte


        # --- Chargement des polices d'impression ---
        import config
        try:
            cls.font_imp_texte = pygame.font.Font(config.POLICE_FICHIER, config.TAILLE_TEXTE_IMP_COURANT)
            cls.font_imp_compteur = pygame.font.Font(config.POLICE_FICHIER, config.TAILLE_COMPTEUR_IMP)
        except Exception as e:
            log_warning(f"Erreur chargement polices impression : {e}")
            # Fallback sur les polices existantes si ça rate
            cls.font_imp_texte = font_bandeau
            cls.font_imp_compteur = font_decompte
        # ----------------------------------------------------

        global _fond_impression_cache
        path_fond = "assets/interface/background.jpg"
        if os.path.exists(path_fond):
            try:
                raw = pygame.image.load(path_fond).convert()
                _fond_impression_cache = pygame.transform.scale(raw, (WIDTH, HEIGHT))
            except Exception as e:
                print(f"Erreur pré-chargement fond : {e}")


# ========================================================================================================
# --- Asset store pour l'écran d'accueil (cache des surfaces chargées au boot) ---
# ========================================================================================================

class AccueilAssets:
    """Cache des surfaces pygame de l'accueil, chargées une seule fois au boot.

    Évite de recharger les images à chaque frame — les `smoothscale` sont
    appliqués ici, les render blits utilisent directement les Surface prêtes.

    Utilisation :
        assets = AccueilAssets.charger(
            bg_path=FILE_BG_ACCUEIL,
            img_10x15_path=PATH_IMG_10X15, img_strip_path=PATH_IMG_STRIP,
            largeur_10x15=LARGEUR_ICONE_10X15, largeur_strip=LARGEUR_ICONE_STRIP,
            zoom_factor=ZOOM_FACTOR, taille_ecran=(WIDTH, HEIGHT),
        )
    """

    def __init__(self) -> None:
        self.fond = None
        self.icon_10x15_norm = None
        self.icon_10x15_select = None
        self.icon_strip_norm = None
        self.icon_strip_select = None

    @classmethod
    def charger(
        cls, bg_path: str, img_10x15_path: str, img_strip_path: str,
        largeur_10x15: int, largeur_strip: int, zoom_factor: float,
        taille_ecran: tuple,
    ) -> "AccueilAssets":
        """Charge toutes les surfaces depuis disque. Toute erreur individuelle est
        logguée en warning mais ne bloque pas le boot (l'app tourne en mode dégradé
        sans le ou les assets manquants)."""
        store = cls()

        # 1. Fond d'accueil
        if os.path.exists(bg_path):
            try:
                bg = pygame.image.load(bg_path).convert()
                store.fond = pygame.transform.scale(bg, taille_ecran)
            except Exception as e:
                log_warning(f"Chargement fond accueil échoué : {e}")
        else:
            log_warning(f"Fond d'accueil manquant : {bg_path}")

        # 2. Icône 10x15 (2 échelles : normale + sélectionnée)
        if os.path.exists(img_10x15_path):
            try:
                raw = pygame.image.load(img_10x15_path).convert_alpha()
                ratio = raw.get_height() / raw.get_width()
                h = int(largeur_10x15 * ratio)
                store.icon_10x15_norm = pygame.transform.smoothscale(raw, (largeur_10x15, h))
                store.icon_10x15_select = pygame.transform.smoothscale(
                    raw, (int(largeur_10x15 * zoom_factor), int(h * zoom_factor)),
                )
            except Exception as e:
                log_warning(f"Chargement icône 10x15 échoué : {e}")
        else:
            log_warning(f"Image 10x15 manquante : {img_10x15_path}")

        # 3. Icône strip (2 échelles)
        if os.path.exists(img_strip_path):
            try:
                raw = pygame.image.load(img_strip_path).convert_alpha()
                ratio = raw.get_height() / raw.get_width()
                h = int(largeur_strip * ratio)
                store.icon_strip_norm = pygame.transform.smoothscale(raw, (largeur_strip, h))
                store.icon_strip_select = pygame.transform.smoothscale(
                    raw, (int(largeur_strip * zoom_factor), int(h * zoom_factor)),
                )
            except Exception as e:
                log_warning(f"Chargement icône strip échoué : {e}")
        else:
            log_warning(f"Image strip manquante : {img_strip_path}")

        return store


# ========================================================================================================
# --- Sons (fallback silencieux si mixer indispo ou fichiers absents) ---
# ========================================================================================================

_mixer_ok = False
SONS = {}


def setup_sounds():
    """Init pygame.mixer + charge les sons optionnels. Silencieux si absents."""
    global _mixer_ok
    try:
        pygame.mixer.init()
        _mixer_ok = True
    except Exception as e:
        log_warning(f"pygame.mixer non disponible : {e}")
        return
    for nom, path in [
        ("beep", SON_BEEP),
        ("beep_final", SON_BEEP_FINAL),
        ("shutter", SON_SHUTTER),
        ("success", SON_SUCCESS),
    ]:
        if not os.path.exists(path):
            continue
        try:
            SONS[nom] = pygame.mixer.Sound(path)
        except Exception as e:
            log_warning(f"Son {nom} non chargé ({path}) : {e}")


_SON_FALLBACK = {"beep_final": "beep"}


def jouer_son(nom):
    """Joue un son si disponible, sinon fallback ou silencieux."""
    s = SONS.get(nom)
    if s is None and nom in _SON_FALLBACK:
        s = SONS.get(_SON_FALLBACK[nom])
    if s is None:
        return
    try:
        s.play()
    except Exception as e:
        log_warning(f"Lecture son {nom} échouée : {e}")


# ========================================================================================================
# --- Helpers de dessin ---
# ========================================================================================================

def obtenir_couleur_pulse(c1, c2, vitesse):
    """Interpolation oscillante entre c1 et c2 en fonction du temps."""
    f = (math.sin(time.time() * vitesse) + 1) / 2
    return tuple(int(c1[i] + (c2[i] - c1[i]) * f) for i in range(3))


def draw_text_shadow_soft(surface, text, font, color, x, y, shadow_alpha=100, offset=2):
    """Dessine un texte avec une ombre noire transparente (lisibilité sur fonds variés)."""
    shadow_surf = font.render(text, True, (0, 0, 0))
    temp_surf = pygame.Surface(shadow_surf.get_size(), pygame.SRCALPHA)
    temp_surf.blit(shadow_surf, (0, 0))
    temp_surf.set_alpha(shadow_alpha)
    surface.blit(temp_surf, (x + offset, y + offset))
    surface.blit(font.render(text, True, color), (x, y))


def inserer_background(screen, fond_image):
    """Blite le fond d'image ou un bleu de secours."""
    if fond_image:
        screen.blit(fond_image, (0, 0))
    else:
        screen.fill((155, 211, 242))


def get_pygame_surf_cropped(path, size_target, ratio_voulu=None):
    """Charge une image, la resize et retourne une pygame.Surface."""
    if not os.path.exists(path):
        return None
    try:
        with Image.open(path) as src:
            img = src.convert("RGB")
        img_fit = img.resize(size_target, Image.Resampling.LANCZOS)
        return pygame.image.fromstring(img_fit.tobytes(), img_fit.size, img_fit.mode)
    except Exception as e:
        log_warning(f"get_pygame_surf_cropped : {e}")
        return None


def get_pygame_surf(path_or_img, size):
    """Accepte un path ou une Image PIL, retourne une Surface pygame."""
    from core.montage import charger_et_corriger  # lazy import pour éviter cycle potentiel
    if isinstance(path_or_img, str):
        if not os.path.exists(path_or_img):
            return None
        img = charger_et_corriger(path_or_img)
    else:
        img = path_or_img
    img = img.resize(size, Image.Resampling.LANCZOS)
    return pygame.image.fromstring(img.tobytes(), img.size, img.mode)


# ========================================================================================================
# --- LoaderAnimation (roue de chargement) ---
# ========================================================================================================

class LoaderAnimation:
    """Spinner animé (roue à queue) pour les écrans d'attente + spinner de génération.

    Les sprites de points sont précalculés à l'init : couleur et alpha ne dépendent
    que de l'index, pas du temps. Chaque frame ne fait plus qu'un blit par point."""

    _sprites_cache: list["pygame.Surface"] | None = None
    _sprites_cache_key: tuple[int, int, tuple, tuple] | None = None

    def __init__(self):
        self.reset()
        self._sprites = self._build_sprites()

    @classmethod
    def _build_sprites(cls) -> list["pygame.Surface"]:
        """Pré-rend `ANIM_NB_POINTS` cercles à couleur+alpha finales.
        Cache partagé entre instances — la config ne change pas à l'exécution."""
        key = (ANIM_NB_POINTS, ANIM_RAYON_POINT, ANIM_COULEUR_TETE, ANIM_COULEUR_QUEUE)
        if cls._sprites_cache is not None and cls._sprites_cache_key == key:
            return cls._sprites_cache

        diametre = ANIM_RAYON_POINT * 2
        sprites: list[pygame.Surface] = []
        denom = max(ANIM_NB_POINTS - 1, 1)
        for i in range(ANIM_NB_POINTS):
            progression = i / denom
            fading = 1.0 - progression
            couleur = tuple(
                int(ANIM_COULEUR_TETE[j] + (ANIM_COULEUR_QUEUE[j] - ANIM_COULEUR_TETE[j]) * (1 - fading))
                for j in range(3)
            )
            alpha = int(255 * (fading ** 0.6))
            sprite = pygame.Surface((diametre, diametre), pygame.SRCALPHA)
            pygame.draw.circle(
                sprite, (*couleur, alpha),
                (ANIM_RAYON_POINT, ANIM_RAYON_POINT), ANIM_RAYON_POINT,
            )
            sprites.append(sprite)
        cls._sprites_cache = sprites
        cls._sprites_cache_key = key
        return sprites

    def reset(self) -> None:
        """Remet l'animation à son état initial (début de roue, longueur minimale)."""
        self.angle_tete = 0
        self.longueur_actuelle = 30
        self.dernier_temps = time.time()

    def update_and_draw(self, screen) -> None:
        """Fait tourner la roue d'une frame et la blite sur `screen`."""
        maintenant = time.time()
        dt = maintenant - self.dernier_temps
        self.dernier_temps = maintenant

        cycle = (math.sin(maintenant * ANIM_FREQ) + 1) / 2
        boost = math.pow(cycle, 4)

        vitesse_actuelle = ANIM_V_BASE + (boost * ANIM_V_MAX_ADD)
        self.angle_tete += vitesse_actuelle * dt * 50

        longueur_cible = 30 + (boost * 210)
        self.longueur_actuelle += (longueur_cible - self.longueur_actuelle) * ANIM_V_ELASTIQUE * dt

        cx = WIDTH // 2
        cy = HEIGHT // 2
        angle_tete = self.angle_tete
        longueur = self.longueur_actuelle
        denom = max(ANIM_NB_POINTS - 1, 1)
        sprites = self._sprites
        for i in reversed(range(ANIM_NB_POINTS)):
            progression = i / denom
            angle_point = math.radians(angle_tete - (progression * longueur))
            x = cx + math.cos(angle_point) * ANIM_TAILLE_ROUE
            y = cy + math.sin(angle_point) * ANIM_TAILLE_ROUE
            screen.blit(sprites[i], (x - ANIM_RAYON_POINT, y - ANIM_RAYON_POINT))


# ========================================================================================================
# --- Écrans de transition ---
# ========================================================================================================

def afficher_message_plein_ecran(message, couleur=(255, 215, 0), fond=COULEUR_FOND_LOADER):
    """Message centré plein écran + flip. Pour transitions courtes."""
    ctx = UIContext
    ctx.screen.fill(fond)
    try:
        txt = ctx.font_bandeau.render(message, True, couleur)
        ctx.screen.blit(
            txt,
            (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - txt.get_height() // 2),
        )
    except Exception as e:
        log_warning(f"afficher_message_plein_ecran : {e}")
    pygame.display.flip()


def executer_avec_spinner(fonction_longue, message):
    global _global_spinner  # On utilise le spinner partagé
    ctx = UIContext
    resultat = {}

    def _wrapper():
        try:
            resultat["value"] = fonction_longue()
        except BaseException as exc:
            resultat["error"] = exc

    t = threading.Thread(target=_wrapper, daemon=True)
    t.start()

    # Initialisation du spinner global s'il n'existe pas encore
    if _global_spinner is None:
        _global_spinner = LoaderAnimation()

    while t.is_alive():
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        # --- MODIFICATION ANTI-FLASH ---
        if _fond_impression_cache:
            ctx.screen.blit(_fond_impression_cache, (0, 0))
        else:
            ctx.screen.fill(COULEUR_FOND_LOADER)
        # -------------------------------

        # On utilise _global_spinner au lieu de local_loader
        _global_spinner.update_and_draw(ctx.screen)
        
        try:
            txt = ctx.font_bandeau.render(message, True, (255, 255, 255))
            ctx.screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT - 120))
        except Exception as e:
            log_warning(f"Rendu spinner : {e}")
            
        pygame.display.flip()
        ctx.clock.tick(SPINNER_FPS)

    t.join(timeout=1.0)
    if "error" in resultat:
        raise resultat["error"]
    return resultat.get("value")


def ecran_erreur(message, timeout=None):
    """Écran rouge avec la bonne police en taille intermédiaire."""
    ctx = UIContext
    if timeout is None:
        timeout = DUREE_ECRAN_ERREUR
    
    # On récupère le chemin du fichier utilisé par font_titre
    # Si font_titre n'a pas d'attribut .name, on utilise font_bandeau
    try:
        # On crée une version intermédiaire (taille 65 ici) à partir de ta police existante
        # Note : On suppose que ctx.font_path contient le chemin vers ton fichier .ttf
        # Si tu n'as pas font_path, on utilise le nom de la police chargée
        font_inter = pygame.font.Font(ctx.font_path, 65) 
    except Exception:
        # Solution de secours si le chemin n'est pas accessible
        font_inter = pygame.font.Font("assets/fonts/WesternBangBang-Regular.ttf", 65)

    t_start = time.time()
    while time.time() - t_start < timeout:
        # ... (le reste de ta boucle d'événements reste identique)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                return
        
        ctx.screen.fill((40, 10, 10))
        try:
            couleur_alerte = (255, 100, 100)
            
            # Titre "ERREUR"
            titre = ctx.font_titre.render("ERREUR", True, couleur_alerte)
            ctx.screen.blit(titre, (WIDTH // 2 - titre.get_width() // 2, HEIGHT // 2 - 220))
            
            # Message avec la BONNE police et la BONNE couleur
            msg = font_inter.render(message, True, couleur_alerte)
            ctx.screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 20))
            
            hint = ctx.font_bandeau.render(
                "Appuyez sur une touche ou patientez...", True, (170, 170, 170)
            )
            ctx.screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 100))
        except Exception as e:
            log_warning(f"Rendu écran erreur : {e}")
            
        pygame.display.flip()
        ctx.clock.tick(30)


# Singleton loader partagé pour l'écran d'attente d'impression (réutilisé entre sessions)
_mon_loader = None
_fond_impression_cache = None
_global_spinner = None


def ecran_attente_impression():
    """Roue d'attente fluide sans flash noir et sans saut d'animation."""
    # 1. TOUTES les déclarations global en PREMIER
    global _global_spinner, _fond_impression_cache
    ctx = UIContext

    # 2. Initialisation immédiate du spinner s'il n'existe pas
    if _global_spinner is None:
        _global_spinner = LoaderAnimation()

    # 3. ACTION ANTI-FLASH : On dessine TOUT DE SUITE
    if _fond_impression_cache:
        ctx.screen.blit(_fond_impression_cache, (0, 0))
    else:
        ctx.screen.fill(COULEUR_FOND_LOADER)
    pygame.display.flip() 

    # 4. BOUCLE D'ANIMATION
    temps_debut = time.time()
    while time.time() - temps_debut < TEMPS_ATTENTE_IMP:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        # Dessin du fond à chaque frame pour le mouvement de la roue
        if _fond_impression_cache:
            ctx.screen.blit(_fond_impression_cache, (0, 0))
        else:
            ctx.screen.fill(COULEUR_FOND_LOADER)

        # Utilisation UNIQUE de _global_spinner (pas de reset ici)
        _global_spinner.update_and_draw(ctx.screen)
        
        try:
            restant = max(0, int(TEMPS_ATTENTE_IMP - (time.time() - temps_debut)))
            
            # Utilisation des polices dédiées
            surf_txt = ctx.font_imp_texte.render("Impression en cours...", True, (255, 255, 255))
            surf_num = ctx.font_imp_compteur.render(f"{restant}s", True, (255, 255, 255))
            
            # Le chiffre (le plus gros) est placé à 150px du bord bas
            pos_y_num = HEIGHT - 10 - surf_num.get_height()
            # Le texte "Impression en cours" est placé juste au-dessus du chiffre
            pos_y_txt = pos_y_num - surf_txt.get_height() - 10 
            
            # Centrage horizontal classique
            ctx.screen.blit(surf_txt, (WIDTH // 2 - surf_txt.get_width() // 2, pos_y_txt))
            ctx.screen.blit(surf_num, (WIDTH // 2 - surf_num.get_width() // 2, pos_y_num))

        except Exception as e:
            log_warning(f"Rendu attente impression : {e}")
            
        pygame.display.flip()
        ctx.clock.tick(SPINNER_FPS)

def splash_connexion_camera(camera_mgr, timeout=None):
    """Splash au boot : tente de connecter la caméra avec animation + retry.
    Retourne True si connectée dans le timeout, False sinon (mode dégradé)."""
    ctx = UIContext
    if timeout is None:
        timeout = TIMEOUT_SPLASH_CAMERA
    t_start = time.time()
    frame_count = 0
    while time.time() - t_start < timeout:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        if not camera_mgr.is_connected and frame_count % 30 == 0:
            if camera_mgr.init():
                camera_mgr.set_liveview(1)

        if camera_mgr.is_connected:
            afficher_message_plein_ecran(TXT_SPLASH_CAMERA_OK, couleur=(100, 255, 100))
            time.sleep(0.6)
            return True

        dots = "." * (1 + (frame_count // 15) % 3)
        afficher_message_plein_ecran(f"{TXT_SPLASH_CAMERA}{dots}", couleur=(255, 215, 0))
        ctx.clock.tick(30)
        frame_count += 1

    afficher_message_plein_ecran(TXT_SPLASH_CAMERA_FAIL, couleur=(255, 150, 150))
    time.sleep(1.5)
    return False
