from __future__ import annotations

# Imports explicites depuis config (plus de `import *` pour dépendances visibles).
# Liste triée alphabétiquement, mise à jour en ajoutant de nouvelles constantes.
from config import (
    ACTIVER_IMPRESSION,
    ALPHA_TEXTE_REPOS, ARDUINO_BAUDRATE, ARDUINO_ENABLED, ARDUINO_PORT,
    BANDEAU_10X15, BANDEAU_ACCUEIL, BANDEAU_ALPHA,
    BANDEAU_COULEUR, BANDEAU_HAUTEUR, BANDEAU_STRIP, COULEUR_DECOMPTE,
    COULEUR_FLASH, COULEUR_SOURIEZ, COULEUR_TEXTE_OFF, COULEUR_TEXTE_ON, COULEUR_TEXTE_REPOS,
    DELAI_SECURITE,
    DUREE_CONFIRM_ABANDON, DUREE_FLASH_BLANC, DUREE_IDLE_SLIDESHOW, DUREE_PAR_IMAGE_SLIDESHOW,
    FILE_BG_ACCUEIL, FORMAT_TIMESTAMP, HEIGHT,
    INTERVALLE_CHECK_DISQUE_S, INTERVALLE_CHECK_TEMP_S, LARGEUR_ICONE_10X15, LARGEUR_ICONE_STRIP, MARGE_ACCUEIL,
    MODE_10x15, MODE_STRIP, NB_MAX_IMAGES_SLIDESHOW,
    NOM_IMPRIMANTE_10X15, NOM_IMPRIMANTE_STRIP, OFFSET_DROITE_10X15, OFFSET_DROITE_STRIP,
    PATH_DATA, PATH_IMG_10X15, PATH_IMG_STRIP, PATH_PRINT,
    PATH_PRINT_10X15, PATH_PRINT_STRIP, PATH_RAW, PATH_SKIPPED,
    PATH_SKIPPED_DELETED, PATH_SKIPPED_RETAKE, PATH_SOUNDS, PATH_TEMP,
    POLICE_FICHIER, PREFIXE_DELETED, PREFIXE_PRINT_10X15, PREFIXE_PRINT_STRIP,
    PREFIXE_RAW, PREFIXE_RETAKE, PULSE_LENT_MAX, PULSE_LENT_MIN, PULSE_LENT_VITESSE, PULSE_MAX,
    PULSE_MIN, PULSE_VITESSE,
    SEUIL_DISQUE_CRITIQUE_MB, SEUIL_TEMP_CRITIQUE_C,
    STRIP_BURST_DELAI_S, STRIP_MODE_BURST,
    TAILLE_DECOMPTE, TAILLE_TEXTE_BANDEAU,
    TEMP_PATH,
    TAILLE_TEXTE_BOUTON, TAILLE_TITRE_ACCUEIL, TEMPS_DECOMPTE, TEXTE_PHOTO_COUNT,
    TOUCHE_DROITE, TOUCHE_GAUCHE, TOUCHE_MILIEU,
    TXT_BURST_COUNTDOWN, TXT_ERREUR_CAPTURE,
    TXT_ERREUR_IMPRIMANTE, TXT_PREPARATION_IMP, TXT_SLIDESHOW_INVITATION, WIDTH, ZOOM_FACTOR,
)
import config  # accès qualifié `config.X` dans les render functions
try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]
import os
import signal
import sys
import time
import shutil
import math
from typing import Optional

from PIL import Image, ImageOps
from datetime import datetime



# ========================================================================================================
# --- MACHINE D'ÉTAT + SESSION STATE (extraits dans core/session.py) ---
# ========================================================================================================
from core.session import (  # noqa: E402
    Etat,
    SessionState,
    terminer_session_et_revenir_accueil as _terminer_session_et_revenir_accueil,
)


# ========================================================================================================
# --- PRÉPARATION DES DOSSIERS & LOGS --- ############################################################
# ========================================================================================================

# On centralise TOUS les dossiers définis dans config.py
dossiers_requis = [
    PATH_RAW, PATH_TEMP, PATH_PRINT, PATH_SKIPPED,
    PATH_PRINT_10X15, PATH_PRINT_STRIP,
    PATH_SKIPPED_RETAKE, PATH_SKIPPED_DELETED,
    PATH_SOUNDS,
    "logs"
]

# Logging : extrait dans logger.py (Sprint 4.6). On importe les 4 helpers.
from core.logger import log_info, log_warning, log_critical  # noqa: E402


def _preparer_dossiers_et_logs() -> None:
    """Crée les dossiers requis, purge les temporaires et trace le démarrage."""
    for d in dossiers_requis:
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
            print(f"📁 Dossier créé : {d}")

    _purger_temp_et_verifier_disque()

    log_info("====================================================")
    log_info("DÉMARRAGE DU PHOTOBOOTH (Dossiers OK)")
    log_info("====================================================")


def _purger_temp_et_verifier_disque() -> None:
    """Nettoie PATH_TEMP (fichiers résiduels d'une session crashée) au boot,
    et log l'espace disque disponible. Avertit si < 1 Go.

    Appelé une seule fois au démarrage. Pour le monitoring continu pendant
    l'événement, voir `DiskMonitor` dans core/monitoring.py."""
    # Purge des fichiers temporaires résiduels
    nb_supprimes = 0
    try:
        for nom in os.listdir(PATH_TEMP):
            chemin = os.path.join(PATH_TEMP, nom)
            if os.path.isfile(chemin):
                try:
                    os.remove(chemin)
                    nb_supprimes += 1
                except OSError:
                    pass
    except FileNotFoundError:
        pass
    if nb_supprimes:
        print(f"🧹 {nb_supprimes} fichier(s) temporaire(s) supprimé(s)")

    # Check espace disque
    try:
        usage = shutil.disk_usage(PATH_DATA)
        libre_go = usage.free / (1024 ** 3)
        if libre_go < 1.0:
            print(f"⚠️ Espace disque critique : {libre_go:.2f} Go libres")
        else:
            print(f"💾 Espace disque libre : {libre_go:.1f} Go")
    except Exception as e:
        print(f"⚠️ Impossible de vérifier l'espace disque : {e}")

# ========================================================================================================
# --- GESTION CANON (Sprint 4.1 + 4.6 : CameraManager extrait dans camera.py) ---
# La classe CameraManager vit désormais dans camera.py. Import + wrappers de compat.
# ========================================================================================================

from core.camera import CameraManager  # noqa: E402


camera_mgr: CameraManager | None = None


# Wrapper de compat — seul `get_canon_frame` est encore appelé (dans render_decompte).
def get_canon_frame() -> Optional[pygame.Surface]:  # type: ignore
    """Retourne la frame preview caméra courante sous forme de pygame.Surface, ou None."""
    if camera_mgr is None:
        return None
    return camera_mgr.get_preview_frame()


# ========================================================================================================
# --- 2. FONCTIONS TECHNIQUES --- ########################################################################
# ========================================================================================================

def capturer_hq(id_session: str, index_photo: int) -> Optional[str]: 
    """Procédure de capture : UI (flash + SOURIEZ animé) + appel CameraManager.capture_hq().

    La capture subprocess (2-3 s) tourne dans un thread daemon pendant qu'on anime
    "SOURIEZ ..." en plein écran sur le thread principal. L'UI reste donc réactive
    (QUIT pris en compte) et le texte anime des points pour signaler que ça travaille.

    Args:
        id_session: timestamp de la session (FORMAT_TIMESTAMP).
        index_photo: numéro de la photo dans la session (1, 2 ou 3 en strip).

    Returns:
        Chemin complet du fichier JPEG si capture OK, None si échec.
    """
    import threading

    nom_final = f"{PREFIXE_RAW}_{id_session}_{index_photo}.jpg"
    chemin_complet = os.path.join(PATH_RAW, nom_final)

    # 1. FLASH BLANC pur (effet "shutter" bref)
    screen.fill(COULEUR_FLASH)
    pygame.display.flip()
    jouer_son("shutter")
    time.sleep(DUREE_FLASH_BLANC)

    # 2. Capture en thread + animation SOURIEZ pendant
    resultat: dict = {}

    def _worker():
        try:
            if camera_mgr is None:
                resultat["success"] = False
                return
            resultat["success"] = camera_mgr.capture_hq(chemin_complet)
        except BaseException as exc:
            resultat["error"] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    # Boucle d'animation : SOURIEZ avec 3 points qui défilent, tant que le thread tourne
    frame = 0
    while t.is_alive():
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        screen.fill(COULEUR_FLASH)
        try:
            dots = "." * (1 + (frame // 10) % 3)
            txt_flash = font_titre.render(f"SOURIEZ {dots}", True, COULEUR_SOURIEZ)
            text_x = (WIDTH // 2) - (txt_flash.get_width() // 2)
            text_y = (HEIGHT // 2) - (txt_flash.get_height() // 2)
            screen.blit(txt_flash, (text_x, text_y))
        except Exception as e:
            log_warning(f"Affichage SOURIEZ échoué : {e}")
        pygame.display.flip()
        clock.tick(30)
        frame += 1

    t.join(timeout=1.0)

    # Propager une éventuelle exception du thread
    if "error" in resultat:
        log_critical(f"Erreur capture worker : {resultat['error']}")
        return None

    success = resultat.get("success", False)

    if success:
        log_info(f"✅ Photo sauvegardée : {nom_final}")
        return chemin_complet
    log_critical(f"ÉCHEC : Le fichier {nom_final} est introuvable.")
    return None


# Helpers de dessin (obtenir_couleur_pulse, draw_text_shadow_soft) : extraits dans ui.py (item 7)

# ========================================================================================================
# --- 3. TRAITEMENT IMAGE (Sprint 4.6 : extrait dans montage.py) ---
# Les classes MontageBase, MontageGenerator10x15, MontageGeneratorStrip et la fonction
# helper `charger_et_corriger` vivent désormais dans montage.py. Module pur (pas de
# pygame, pas de globals UI), testable isolément. Import + wrappers de compat ci-dessous.
# ========================================================================================================

from core.montage import MontageGenerator10x15, MontageGeneratorStrip  # noqa: E402


# get_pygame_surf_cropped / get_pygame_surf / inserer_background : extraits dans ui.py (item 7)


# LoaderAnimation + ecran_attente_impression : extraits dans ui.py (item 7)


# --- PrinterManager (Sprint 4.3) : extrait dans printer.py (Sprint 4.6) ---
from core.printer import PrinterManager  # noqa: E402

# Singleton global utilisé par les wrappers et — pour du nouveau code — à appeler directement.
printer_mgr = PrinterManager(NOM_IMPRIMANTE_10X15, NOM_IMPRIMANTE_STRIP)


# ========================================================================================================
# ========================================================================================================
# --- 6. INITIALISATION & BOUCLE PRINCIPALE --- ##########################################################
# ========================================================================================================
# ========================================================================================================

def _ui_non_initialisee(*args, **kwargs):
    raise RuntimeError("UI pygame non initialisée : appeler main() pour lancer le photobooth")


# ========================================================================================================
# --- ARDUINO NANO (3 boutons-poussoirs à LED intégrée) ---
# Le contrôleur ouvre le port série, injecte des pygame.KEYDOWN pour chaque bouton
# pressé et pilote les LEDs selon la machine d'état via `arduino_ctrl.tick(...)`.
# Inerte (no-op) si ARDUINO_ENABLED=False, port absent ou pyserial manquant —
# le photobooth reste utilisable au clavier.
# ========================================================================================================
from core.arduino import ArduinoController  # noqa: E402


# --- Monitoring disque + slideshow listing (extraits dans core/monitoring.py) ---
from core.monitoring import DiskMonitor, TempMonitor, lister_images_slideshow  # noqa: E402


screen = None
clock = None
font_titre = None
font_boutons = None
font_bandeau = None
font_decompte = None
font_filigrane = None
UIContext = None
AccueilAssets = None
setup_sounds = _ui_non_initialisee
jouer_son = _ui_non_initialisee
draw_text_shadow_soft = _ui_non_initialisee
inserer_background = _ui_non_initialisee
afficher_message_plein_ecran = _ui_non_initialisee
executer_avec_spinner = _ui_non_initialisee
ecran_erreur = _ui_non_initialisee
ecran_attente_impression = _ui_non_initialisee
splash_connexion_camera = _ui_non_initialisee
arduino_ctrl: ArduinoController | None = None
disk_monitor: DiskMonitor | None = None
temp_monitor: TempMonitor | None = None
BANDEAU_CACHE = None
session = SessionState(last_activity_ts=0.0)
running = True
slideshow_images = []
slideshow_last_refresh = 0.0
slideshow_cached_surface = None
slideshow_cached_for_idx = -1
fond_accueil = None
icon_10x15_norm = None
icon_10x15_select = None
icon_strip_norm = None
icon_strip_select = None


def _charger_polices():
    """Charge les polices pygame ou bascule sur Arial si l'asset manque."""
    try:
        if os.path.exists(POLICE_FICHIER):
            return (
                pygame.font.Font(POLICE_FICHIER, TAILLE_TITRE_ACCUEIL),
                pygame.font.Font(POLICE_FICHIER, TAILLE_TEXTE_BOUTON),
                pygame.font.Font(POLICE_FICHIER, TAILLE_TEXTE_BANDEAU),
                pygame.font.Font(POLICE_FICHIER, TAILLE_DECOMPTE),
                pygame.font.Font(POLICE_FICHIER, config.STRIP_FILIGRANE_TAILLE),
            )
        raise FileNotFoundError
    except Exception:
        return (
            pygame.font.SysFont("Arial", TAILLE_TITRE_ACCUEIL, bold=True),
            pygame.font.SysFont("Arial", TAILLE_TEXTE_BOUTON),
            pygame.font.SysFont("Arial", TAILLE_TEXTE_BANDEAU, bold=True),
            pygame.font.SysFont("Arial", TAILLE_DECOMPTE, bold=True),
            pygame.font.SysFont("Arial", config.STRIP_FILIGRANE_TAILLE, bold=True),
        )


def _initialiser_runtime() -> None:
    """Initialise les singletons runtime. Aucun effet de bord lourd à l'import."""
    global camera_mgr, screen, clock
    global font_titre, font_boutons, font_bandeau, font_decompte, font_filigrane
    global UIContext, AccueilAssets, setup_sounds, jouer_son, draw_text_shadow_soft
    global inserer_background, afficher_message_plein_ecran, executer_avec_spinner
    global ecran_erreur, ecran_attente_impression, splash_connexion_camera
    global arduino_ctrl, disk_monitor, temp_monitor, BANDEAU_CACHE, session, running
    global slideshow_images, slideshow_last_refresh, slideshow_cached_surface, slideshow_cached_for_idx
    global fond_accueil, icon_10x15_norm, icon_10x15_select, icon_strip_norm, icon_strip_select

    if pygame is None:
        raise RuntimeError("pygame est requis pour lancer Photobooth_start.py")

    _preparer_dossiers_et_logs()

    from ui import (
        UIContext as _UIContext,
        AccueilAssets as _AccueilAssets,
        setup_sounds as _setup_sounds,
        jouer_son as _jouer_son,
        draw_text_shadow_soft as _draw_text_shadow_soft,
        inserer_background as _inserer_background,
        afficher_message_plein_ecran as _afficher_message_plein_ecran,
        executer_avec_spinner as _executer_avec_spinner,
        ecran_erreur as _ecran_erreur,
        ecran_attente_impression as _ecran_attente_impression,
        splash_connexion_camera as _splash_connexion_camera,
    )

    UIContext = _UIContext
    AccueilAssets = _AccueilAssets
    setup_sounds = _setup_sounds
    jouer_son = _jouer_son
    draw_text_shadow_soft = _draw_text_shadow_soft
    inserer_background = _inserer_background
    afficher_message_plein_ecran = _afficher_message_plein_ecran
    executer_avec_spinner = _executer_avec_spinner
    ecran_erreur = _ecran_erreur
    ecran_attente_impression = _ecran_attente_impression
    splash_connexion_camera = _splash_connexion_camera

    camera_mgr = CameraManager()
    camera_mgr.init()
    if camera_mgr.is_connected:
        camera_mgr.set_liveview(1)

    pygame.init()
    _display_flags = (pygame.FULLSCREEN | pygame.NOFRAME) if config.KIOSK_FULLSCREEN else 0
    screen = pygame.display.set_mode((WIDTH, HEIGHT), _display_flags)
    if config.KIOSK_FULLSCREEN:
        pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()
    pygame.font.init()

    font_titre, font_boutons, font_bandeau, font_decompte, font_filigrane = _charger_polices()
    UIContext.setup(screen, clock, font_titre, font_boutons, font_bandeau, font_decompte)
    setup_sounds()

    arduino_ctrl = ArduinoController(
        port=ARDUINO_PORT if ARDUINO_ENABLED else None,
        baudrate=ARDUINO_BAUDRATE,
        key_left=TOUCHE_GAUCHE,
        key_mid=TOUCHE_MILIEU,
        key_right=TOUCHE_DROITE,
    )
    arduino_ctrl.start()

    disk_monitor = DiskMonitor(
        path=PATH_DATA, seuil_mb=SEUIL_DISQUE_CRITIQUE_MB, intervalle_s=INTERVALLE_CHECK_DISQUE_S,
    )
    temp_monitor = TempMonitor(
        path=TEMP_PATH, seuil_c=SEUIL_TEMP_CRITIQUE_C, intervalle_s=INTERVALLE_CHECK_TEMP_S,
    )

    BANDEAU_CACHE = pygame.Surface((WIDTH, BANDEAU_HAUTEUR))
    BANDEAU_CACHE.set_alpha(BANDEAU_ALPHA)
    BANDEAU_CACHE.fill(BANDEAU_COULEUR)

    session = SessionState(last_activity_ts=time.time())
    running = True
    slideshow_images = []
    slideshow_last_refresh = 0.0
    slideshow_cached_surface = None
    slideshow_cached_for_idx = -1

    accueil_assets = AccueilAssets.charger(
        bg_path=FILE_BG_ACCUEIL,
        img_10x15_path=PATH_IMG_10X15,
        img_strip_path=PATH_IMG_STRIP,
        largeur_10x15=LARGEUR_ICONE_10X15,
        largeur_strip=LARGEUR_ICONE_STRIP,
        zoom_factor=ZOOM_FACTOR,
        taille_ecran=(WIDTH, HEIGHT),
    )
    fond_accueil = accueil_assets.fond
    icon_10x15_norm = accueil_assets.icon_10x15_norm
    icon_10x15_select = accueil_assets.icon_10x15_select
    icon_strip_norm = accueil_assets.icon_strip_norm
    icon_strip_select = accueil_assets.icon_strip_select
    print("✅ Interface chargée (AccueilAssets).")

    session.abandon_confirm_until = 0.0


def terminer_session_et_revenir_accueil(issue: str) -> None:
    """Wrapper module-local : délègue à core.session en passant le `session` global."""
    _terminer_session_et_revenir_accueil(session, issue)


def _generer_montage_final(session: SessionState) -> str:
    """Génère le montage HD adapté au mode courant et retourne son chemin."""
    if session.mode_actuel == "strips":
        return MontageGeneratorStrip.final(session.photos_validees, session.id_session_timestamp)
    return MontageGenerator10x15.final(session.photos_validees, session.id_session_timestamp)


def _destination_montage_imprime(session: SessionState) -> str:
    """Chemin d'archive du montage final selon le mode courant."""
    if session.mode_actuel == "strips":
        # On pointe vers le sous-dossier et on ajoute le suffixe
        return os.path.join(PATH_PRINT_STRIP, "READY_TO_PRINT", f"{PREFIXE_PRINT_STRIP}_{session.id_session_timestamp}_READY_TO_PRINT.jpg")
    return os.path.join(PATH_PRINT_10X15, f"{PREFIXE_PRINT_10X15}_{session.id_session_timestamp}.jpg")


def traiter_impression_session(session: SessionState) -> str:
    """Génère, archive et imprime le montage final avec diagnostic précis."""
    try:
        p = executer_avec_spinner(
            lambda: _generer_montage_final(session),
            TXT_PREPARATION_IMP,
        )
        destination = _destination_montage_imprime(session)

        # Copie si nécessaire (Strips gèrent leur propre chemin)
        if session.mode_actuel != "strips":
            shutil.copy(p, destination)
        else:
            destination = p

        if not ACTIVER_IMPRESSION:
            log_info(f"Impression désactivée : montage enregistré ({destination})")
            afficher_message_plein_ecran("Impression désactivée - montage enregistré", couleur=(255, 215, 0))
            time.sleep(1.2)
            return "print_disabled"

        # --- MODIFICATION ANTI-FLASH ---
        from ui import helpers
        if hasattr(helpers, '_fond_impression_cache') and helpers._fond_impression_cache:
            helpers.UIContext.screen.blit(helpers._fond_impression_cache, (0, 0))
            pygame.display.flip()

        # ===========================================================
        # --- NOUVELLE VÉRIFICATION DE SÉCURITÉ (Saturations/État) ---
        # ===========================================================
        # On appelle is_ready qui renvoie désormais True ou False
        if printer_mgr.is_ready(session.mode_actuel):
            if printer_mgr.send(destination, session.mode_actuel):
                jouer_son("success")
                ecran_attente_impression()
                return "printed"
            else:
                # En cas d'échec d'envoi, on affiche l'erreur stockée
                ecran_erreur(printer_mgr.last_error or TXT_ERREUR_IMPRIMANTE)
                return "print_failed"
        else:
            # ICI : Au lieu d'afficher "status" (qui est juste False),
            # on affiche le message texte précis qu'on a mémorisé.
            log_warning(f"Impression bloquée : {printer_mgr.last_error}")
            ecran_erreur(printer_mgr.last_error) 
            return "print_failed"
        # ===========================================================

    except Exception as e:
        log_critical(f"Erreur impression finale : {e}")
        ecran_erreur(TXT_ERREUR_IMPRIMANTE)
        return "print_failed"

def demander_arret(signum=None, frame=None) -> None:
    """Demande un arrêt propre de la boucle principale."""
    global running
    running = False
    if signum is not None:
        log_info(f"Signal d'arrêt reçu ({signum})")



# ========================================================================================================
# --- RENDER FUNCTIONS (Sprint item 11) ---
# Chaque état a sa fonction de rendu. Accèdent aux globals du module (screen, fontes,
# assets, caches). `session` est passé explicitement pour rendre la dépendance visible.
# ========================================================================================================

def _render_accueil_slideshow(session: SessionState, idle_seconds: float) -> None:
    """Rendu du slideshow plein écran avec invitation pulsée.

    Scan les images toutes les 30 s (évite l'I/O disque par frame). Affiche chaque
    image pendant `DUREE_PAR_IMAGE_SLIDESHOW` secondes. Si `PATH_PRINT_*` est vide,
    on garde le fond d'accueil avec juste l'invitation par-dessus."""
    global slideshow_images, slideshow_last_refresh, slideshow_cached_for_idx, slideshow_cached_surface

    # Rafraîchit la liste tous les 30 s pour inclure les nouvelles impressions
    if time.time() - slideshow_last_refresh > 30.0 or not slideshow_images:
        slideshow_images = lister_images_slideshow(
            [PATH_PRINT_10X15, PATH_PRINT_STRIP], NB_MAX_IMAGES_SLIDESHOW,
        )
        slideshow_last_refresh = time.time()
        slideshow_cached_for_idx = -1

    screen.fill((0, 0, 0))
    if slideshow_images:
        temps_slideshow = idle_seconds - DUREE_IDLE_SLIDESHOW
        idx = int(temps_slideshow / DUREE_PAR_IMAGE_SLIDESHOW) % len(slideshow_images)
        if idx != slideshow_cached_for_idx:
            try:
                raw = pygame.image.load(slideshow_images[idx]).convert()
                iw, ih = raw.get_size()
                scale = min(WIDTH / iw, HEIGHT / ih)
                slideshow_cached_surface = pygame.transform.smoothscale(
                    raw, (int(iw * scale), int(ih * scale)),
                )
                slideshow_cached_for_idx = idx
            except Exception as e:
                log_warning(f"Slideshow load échoué : {e}")
                slideshow_cached_surface = None

        if slideshow_cached_surface:
            sx = (WIDTH - slideshow_cached_surface.get_width()) // 2
            sy = (HEIGHT - slideshow_cached_surface.get_height()) // 2
            screen.blit(slideshow_cached_surface, (sx, sy))
    else:
        inserer_background(screen, fond_accueil)

    # Invitation pulsée + bandeau noir pour lisibilité
    alpha_inv = 150 + int(80 * math.sin(time.time() * 2))
    inv_surf = font_titre.render(TXT_SLIDESHOW_INVITATION, True, (255, 255, 255))
    inv_surf.set_alpha(alpha_inv)
    inv_x = WIDTH // 2 - inv_surf.get_width() // 2
    inv_bg = pygame.Surface((WIDTH, inv_surf.get_height() + 30), pygame.SRCALPHA)
    inv_bg.fill((0, 0, 0, 130))
    screen.blit(inv_bg, (0, HEIGHT - inv_surf.get_height() - 60))
    screen.blit(inv_surf, (inv_x, HEIGHT - inv_surf.get_height() - 45))


def _render_accueil_normal(session: SessionState) -> None:
    """Rendu de l'accueil standard : 2 icônes (10x15/strip) cliquables + bandeau de conseil.

    L'icône sélectionnée (session.mode_actuel) est zoomée et pulse. Le bandeau
    indique le bouton à presser pour démarrer. Si l'espace disque est critique
    (disk_monitor.critique), on superpose un bandeau rouge d'alerte en haut.
    Idem pour la température CPU (temp_monitor.critique), bandeau orange."""
    inserer_background(screen, fond_accueil)
    marge_centrale = MARGE_ACCUEIL
    axe_y_centre = (HEIGHT // 2) - 60

    # Effet de clignotement doux (pulsation)
    amplitude = (PULSE_MAX - PULSE_MIN) // 2
    pulse = (PULSE_MIN + amplitude) + int(amplitude * math.sin(time.time() * PULSE_VITESSE))

    amp_lente = (PULSE_LENT_MAX - PULSE_LENT_MIN) // 2
    pulse_lent = (PULSE_LENT_MIN + amp_lente) + int(amp_lente * math.sin(time.time() * PULSE_LENT_VITESSE))

    facteur_pulse = (pulse - PULSE_MIN) / (PULSE_MAX - PULSE_MIN) if (PULSE_MAX - PULSE_MIN) != 0 else 0
    couleur_choisie = tuple(
        int(COULEUR_TEXTE_OFF[i] + (COULEUR_TEXTE_ON[i] - COULEUR_TEXTE_OFF[i]) * facteur_pulse)
        for i in range(3)
    )

    # Bloc gauche : 10x15
    if icon_10x15_norm:
        is_sel = (session.mode_actuel == "10x15")
        img_draw = icon_10x15_select if is_sel else icon_10x15_norm
        x_10 = (WIDTH // 2) - img_draw.get_width() - (marge_centrale // 2) + OFFSET_DROITE_10X15
        y_10 = axe_y_centre - (img_draw.get_height() // 2)
        img_draw.set_alpha(pulse if is_sel else 130)
        screen.blit(img_draw, (x_10, y_10))

        color_txt_10 = couleur_choisie if is_sel else COULEUR_TEXTE_REPOS
        txt_10 = font_boutons.render(MODE_10x15, True, color_txt_10)
        if not is_sel:
            txt_10.set_alpha(ALPHA_TEXTE_REPOS)
        screen.blit(txt_10, (x_10 + img_draw.get_width() // 2 - txt_10.get_width() // 2,
                             y_10 + img_draw.get_height() + 20))

    # Bloc droit : STRIPS
    if icon_strip_norm:
        is_sel = (session.mode_actuel == "strips")
        img_draw = icon_strip_select if is_sel else icon_strip_norm
        x_s = (WIDTH // 2) + (marge_centrale // 2) + OFFSET_DROITE_STRIP
        y_s = axe_y_centre - (img_draw.get_height() // 2)
        img_draw.set_alpha(pulse if is_sel else 130)
        screen.blit(img_draw, (x_s, y_s))

        color_txt_s = couleur_choisie if is_sel else COULEUR_TEXTE_REPOS
        txt_s = font_boutons.render(MODE_STRIP, True, color_txt_s)
        if not is_sel:
            txt_s.set_alpha(ALPHA_TEXTE_REPOS)
        screen.blit(txt_s, (x_s + img_draw.get_width() // 2 - txt_s.get_width() // 2,
                            y_s + img_draw.get_height() + 20))

    # Bandeau navigation (surface cachée Sprint 3.4)
    screen.blit(BANDEAU_CACHE, (0, HEIGHT - BANDEAU_HAUTEUR))

    if session.mode_actuel == "10x15":
        msg_txt = BANDEAU_10X15
    elif session.mode_actuel == "strips":
        msg_txt = BANDEAU_STRIP
    else:
        msg_txt = BANDEAU_ACCUEIL

    couleur_txt = (pulse, pulse, pulse) if session.mode_actuel else (pulse_lent, pulse_lent, pulse_lent)
    msg_rendu = font_bandeau.render(msg_txt, True, couleur_txt)
    pos_x = WIDTH // 2 - msg_rendu.get_width() // 2
    pos_y = (HEIGHT - BANDEAU_HAUTEUR // 2) - (msg_rendu.get_height() // 2)
    screen.blit(msg_rendu, (pos_x, pos_y))

    # Indicateur disque critique (Sprint 5.6) + température CPU
    alerte_h = 40
    y_alerte = 0
    if disk_monitor.critique and disk_monitor.libre_mb is not None:
        alerte = pygame.Surface((WIDTH, alerte_h), pygame.SRCALPHA)
        alerte.fill((180, 20, 20, 220))
        screen.blit(alerte, (0, y_alerte))
        txt_alerte = font_bandeau.render(
            f"⚠ ESPACE DISQUE CRITIQUE — {disk_monitor.libre_mb:.0f} Mo libres",
            True, (255, 255, 255),
        )
        screen.blit(
            txt_alerte,
            (WIDTH // 2 - txt_alerte.get_width() // 2,
             y_alerte + (alerte_h - txt_alerte.get_height()) // 2),
        )
        y_alerte += alerte_h

    if temp_monitor.critique and temp_monitor.temp_c is not None:
        alerte = pygame.Surface((WIDTH, alerte_h), pygame.SRCALPHA)
        alerte.fill((200, 120, 20, 220))
        screen.blit(alerte, (0, y_alerte))
        txt_alerte = font_bandeau.render(
            f"🌡 CPU CHAUD — {temp_monitor.temp_c:.1f} °C",
            True, (255, 255, 255),
        )
        screen.blit(
            txt_alerte,
            (WIDTH // 2 - txt_alerte.get_width() // 2,
             y_alerte + (alerte_h - txt_alerte.get_height()) // 2),
        )


def render_accueil(session: SessionState) -> None:
    """ACCUEIL : slideshow d'attente si idle > seuil ET mode_actuel is None,
    sinon rendu normal (icônes + bandeau + alertes disque/température).

    Dispatcher entre `_render_accueil_slideshow` et `_render_accueil_normal`.
    Déclenche aussi les checks monitoring périodiques (rate-limités)."""
    disk_monitor.tick()
    temp_monitor.tick()

    idle_seconds = time.time() - session.last_activity_ts
    if idle_seconds > DUREE_IDLE_SLIDESHOW and session.mode_actuel is None:
        _render_accueil_slideshow(session, idle_seconds)
    else:
        _render_accueil_normal(session)


_masque_decompte_cache: dict[tuple[int, int], "pygame.Surface"] = {}  # type: ignore


def _get_masque_decompte(bande_w: int, alpha: int) -> "pygame.Surface":  # type: ignore
    """Retourne la bande noire latérale du décompte, mise en cache par (largeur, alpha).

    Évite une allocation pygame.Surface par frame (≈60/s pendant le décompte)."""
    key = (bande_w, alpha)
    surf = _masque_decompte_cache.get(key)
    if surf is None:
        surf = pygame.Surface((bande_w, HEIGHT))
        surf.fill((0, 0, 0))
        surf.set_alpha(alpha)
        _masque_decompte_cache[key] = surf
    return surf


def render_decompte(session: SessionState) -> None:
    """DECOMPTE : preview caméra + compteur + capture HQ + transition d'état.

    C'est plus qu'un simple rendu — cette fonction orchestre :
    1. Initialisation de l'id_session si première photo.
    2. Boucle de décompte visuel (N...1) avec preview caméra LiveView.
    3. Appel bloquant à `capturer_hq()` (flash + SOURIEZ + subprocess gphoto2).
    4. Transition d'état : VALIDATION si OK, ACCUEIL + metadata "capture_failed"
       si échec."""
    # LOGIQUE DE RATIO ET MASQUE SELON LE MODE
    if session.mode_actuel == "strips":
        p_ratio = config.STRIP_PHOTO_RATIO
        alpha_masque = config.MASQUE
    else:
        p_ratio = 0.66
        alpha_masque = 0

    # Pré-calcul du masque latéral (indépendant de la frame)
    masque_surf = None
    bande_w = 0
    if alpha_masque > 0:
        largeur_visible = HEIGHT / p_ratio
        bande_w = int((WIDTH - largeur_visible) // 2)
        if bande_w > 0:
            masque_surf = _get_masque_decompte(bande_w, alpha_masque)

    # Init id session si première photo
    if len(session.photos_validees) == 0:
        session.id_session_timestamp = datetime.now().strftime(FORMAT_TIMESTAMP)
        session.session_start_ts = time.time()
        log_info(f"🚀 NOUVELLE SESSION : {session.id_session_timestamp}")

    # Boucle du décompte visuel
    for i in range(TEMPS_DECOMPTE, 0, -1):
        jouer_son("beep_final" if i == 1 else "beep")
        t_start = time.time()
        while time.time() - t_start < 1:
            surf = get_canon_frame()
            if surf:
                screen.blit(pygame.transform.scale(surf, (WIDTH, HEIGHT)), (0, 0))

                if masque_surf is not None:
                    screen.blit(masque_surf, (0, 0))
                    screen.blit(masque_surf, (WIDTH - bande_w, 0))

                if session.mode_actuel == "strips":
                    txt_label = f"{TEXTE_PHOTO_COUNT} {len(session.photos_validees) + 1} / 3"
                    label_surf = font_boutons.render(txt_label, True, COULEUR_DECOMPTE)
                    label_x = WIDTH // 2 - label_surf.get_width() // 2
                    draw_text_shadow_soft(
                        screen, txt_label, font_boutons, COULEUR_DECOMPTE,
                        label_x, 30, shadow_alpha=180, offset=3,
                    )

                    if config.STRIP_FILIGRANE_ENABLED:
                        photos_restantes = 3 - len(session.photos_validees)
                        fili_surf = font_filigrane.render(str(photos_restantes), True, COULEUR_DECOMPTE)
                        fili_surf.set_alpha(config.STRIP_FILIGRANE_ALPHA)
                        screen.blit(fili_surf, (
                            WIDTH // 2 - fili_surf.get_width() // 2,
                            HEIGHT // 2 - fili_surf.get_height() // 2,
                        ))

                num_surf = font_decompte.render(str(i), True, COULEUR_DECOMPTE)
                screen.blit(num_surf, (WIDTH // 2 - num_surf.get_width() // 2, HEIGHT // 2 - num_surf.get_height() // 2))

            pygame.display.flip()
            pygame.event.pump()

    # CAPTURE HQ + transition
    index_photo = len(session.photos_validees) + 1
    chemin_photo = capturer_hq(session.id_session_timestamp, index_photo)

    if chemin_photo:
        session.photos_validees.append(chemin_photo)
        session.etat = Etat.VALIDATION
    else:
        log_critical("Erreur capture : retour à l'accueil")
        ecran_erreur(TXT_ERREUR_CAPTURE)
        terminer_session_et_revenir_accueil("capture_failed")

    session.dernier_clic_time = time.time()


def render_validation(session: SessionState) -> bool:
    """VALIDATION : aperçu de la dernière photo + bandeau boutons + burst countdown.

    Returns:
        True si une auto-validation burst a eu lieu (caller doit `continue` pour
        éviter le flip d'un frame de transition), False sinon.
    """
    inserer_background(screen, fond_accueil)

    # Mode burst strip : auto-validation après STRIP_BURST_DELAI_S
    if (STRIP_MODE_BURST and session.mode_actuel == "strips"
            and len(session.photos_validees) < 3):
        ecoule_valid = time.time() - session.dernier_clic_time
        if ecoule_valid >= STRIP_BURST_DELAI_S:
            session.img_preview_cache = None
            session.etat = Etat.DECOMPTE
            session.dernier_clic_time = time.time()
            return True

    # 1. Gestion de l'aperçu (Image seule)
    if not session.img_preview_cache and len(session.photos_validees) > 0:
        derniere_photo = session.photos_validees[-1]

        if session.mode_actuel == "strips":
            hauteur_cible = getattr(config, 'PREVISU_H_STRIP', 600)
            r_v = float(getattr(config, 'STRIP_PHOTO_RATIO', 1.0))
        else:
            hauteur_cible = getattr(config, 'PREVISU_H', 533)
            r_v = 0.66

        largeur_cible = int(hauteur_cible / r_v)

        # `with` garantit la fermeture du handle fichier (sinon fuite mémoire 30 FPS)
        with Image.open(derniere_photo) as raw_img:
            oriented = ImageOps.exif_transpose(raw_img)
        pil_img = ImageOps.fit(oriented, (largeur_cible, hauteur_cible), Image.Resampling.LANCZOS)
        session.img_preview_cache = pygame.image.fromstring(
            pil_img.tobytes(), pil_img.size, pil_img.mode
        ).convert()

    # 2. Affichage de l'aperçu centré
    if session.img_preview_cache:
        m_t = str(session.mode_actuel).lower().strip()
        dec = (getattr(config, 'DECALAGE_Y_PREVISU_10X15', 0) if m_t == "10x15"
               else getattr(config, 'DECALAGE_Y_PREVISU_STRIPS', 0))
        x_p = (WIDTH // 2) - (session.img_preview_cache.get_width() // 2)
        y_p = (HEIGHT // 2) - (session.img_preview_cache.get_height() // 2) + dec
        pygame.draw.rect(screen, (255, 255, 255),
                         (x_p - 10, y_p - 10, session.img_preview_cache.get_width() + 20, session.img_preview_cache.get_height() + 20))
        screen.blit(session.img_preview_cache, (x_p, y_p))

    # 3. Bandeau + boutons
    y_b = HEIGHT - BANDEAU_HAUTEUR
    screen.blit(BANDEAU_CACHE, (0, y_b))
    y_t = y_b + (BANDEAU_HAUTEUR // 2) - (font_bandeau.get_height() // 2)

    if session.mode_actuel == "strips":
        txt_g = config.TXT_VALID_REPRENDRE_STRIP
        txt_m = config.TXT_VALID_VALIDER_STRIP
        txt_d = config.TXT_VALID_ACCUEIL_STRIP
    else:
        txt_g = config.TXT_VALID_REPRENDRE_10X15
        txt_m = config.TXT_VALID_VALIDER_10X15
        txt_d = config.TXT_VALID_ACCUEIL_10X15

    screen.blit(font_bandeau.render(txt_g, True, config.COULEUR_TEXTE_G), (80, y_t))
    t_m = font_bandeau.render(txt_m, True, config.COULEUR_TEXTE_M)
    screen.blit(t_m, (WIDTH // 2 - t_m.get_width() // 2, y_t))
    t_d = font_bandeau.render(txt_d, True, config.COULEUR_TEXTE_D)
    screen.blit(t_d, (WIDTH - 80 - t_d.get_width(), y_t))

    # Compteur PHOTO N/3 (strips)
    if session.mode_actuel == "strips":
        txt_c = f"{config.TEXTE_PHOTO_COUNT} {len(session.photos_validees)} / 3"
        draw_text_shadow_soft(screen, txt_c, font_bandeau, (255, 215, 0),
                              WIDTH // 2 - font_bandeau.size(txt_c)[0] // 2, 10)

    # Countdown burst "Photo suivante dans Xs" si actif
    if (STRIP_MODE_BURST and session.mode_actuel == "strips"
            and len(session.photos_validees) < 3):
        restant = STRIP_BURST_DELAI_S - (time.time() - session.dernier_clic_time)
        if restant > 0:
            txt_burst = f"{TXT_BURST_COUNTDOWN} {restant:.0f}s"
            burst_surf = font_bandeau.render(txt_burst, True, (255, 255, 255))
            bx = WIDTH // 2 - burst_surf.get_width() // 2
            by = 70
            burst_bg = pygame.Surface(
                (burst_surf.get_width() + 40, burst_surf.get_height() + 12),
                pygame.SRCALPHA,
            )
            burst_bg.fill((0, 0, 0, 160))
            screen.blit(burst_bg, (bx - 20, by - 6))
            screen.blit(burst_surf, (bx, by))
    return False


def render_fin(session: SessionState) -> None:
    """FIN : aperçu du montage final + bandeau 3 boutons + overlay confirmation abandon."""
    inserer_background(screen, fond_accueil)

    # 1. Récupération du chemin de l'image
    p_prev = session.path_montage if session.path_montage else os.path.join(
        getattr(config, 'PATH_TEMP', 'temp'), "montage_prev.jpg"
    )

    # 2. Chargement et redimensionnement dynamique (respecte le ratio du fichier)
    if session.img_preview_cache is None and os.path.exists(p_prev):
        try:
            raw_m = pygame.image.load(p_prev).convert_alpha()
            ratio_reel = raw_m.get_width() / raw_m.get_height()
            
            h_max_fin = 650 if session.mode_actuel == "strips" else 520
            w_ajustee = int(h_max_fin * ratio_reel)

            session.img_preview_cache = pygame.transform.smoothscale(raw_m, (w_ajustee, h_max_fin))
        except Exception as e:
            log_warning(f"Erreur chargement aperçu FIN : {e}")

    # 3. Affichage de l'aperçu centré (Le cadre blanc est déjà dans l'image)
    if session.img_preview_cache:
        dec_y = getattr(config, 'DECALAGE_Y_MONTAGE_FINAL_STRIP', 0) if session.mode_actuel == "strips" else getattr(config, 'DECALAGE_Y_PREVISU_10X15', 0)
        
        x_m = (WIDTH - session.img_preview_cache.get_width()) // 2
        y_m = (HEIGHT // 2 - session.img_preview_cache.get_height() // 2) + dec_y
        
        screen.blit(session.img_preview_cache, (x_m, y_m))

    # 4. Bandeau de boutons
    y_b = HEIGHT - BANDEAU_HAUTEUR
    screen.blit(BANDEAU_CACHE, (0, y_b))
    y_t = y_b + (BANDEAU_HAUTEUR // 2) - (font_bandeau.get_height() // 2)
    
    # Bouton Reprendre (Gauche)
    txt_g_surf = font_bandeau.render(config.TXT_BOUTON_REPRENDRE, True, config.COULEUR_TEXTE_G)
    screen.blit(txt_g_surf, (80, y_t))
    
    # Bouton Imprimer (Milieu)
    t_m = font_bandeau.render(config.TXT_BOUTON_IMPRIMER, True, config.COULEUR_TEXTE_M)
    screen.blit(t_m, (WIDTH // 2 - t_m.get_width() // 2, y_t))
    
    # Bouton Supprimer (Droite)
    t_d = font_bandeau.render(config.TXT_BOUTON_SUPPRIMER, True, config.COULEUR_TEXTE_D)
    screen.blit(t_d, (WIDTH - 80 - t_d.get_width(), y_t))

    # 5. Overlay de confirmation d'abandon
    if session.abandon_confirm_until and time.time() < session.abandon_confirm_until:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        screen.blit(overlay, (0, 0))
        
        t1 = font_titre.render(config.TXT_CONFIRM_ABANDON_1, True, (255, 120, 120))
        screen.blit(t1, (WIDTH // 2 - t1.get_width() // 2, HEIGHT // 2 - 120))
        
        t2 = font_bandeau.render(config.TXT_CONFIRM_ABANDON_2, True, (255, 255, 255))
        screen.blit(t2, (WIDTH // 2 - t2.get_width() // 2, HEIGHT // 2 + 20))
    elif session.abandon_confirm_until:
        session.abandon_confirm_until = 0.0


# ========================================================================================================
# --- EVENT HANDLERS (Sprint item 9) ---
# Un handler par état qui peut recevoir des touches (ACCUEIL/VALIDATION/FIN).
# Chaque handler mute `session` en place. Les `return` anticipés remplacent les
# `continue` du code inline (le for event loop extérieur passe à l'event suivant).
# DECOMPTE n'a pas de handler car l'état est non-interactif (géré par render_decompte).
# ========================================================================================================

def handle_accueil_event(event: pygame.event.Event, session: SessionState,   # type: ignore
                         maintenant: float, ecoule: float) -> None:
    """ACCUEIL : G/D sélectionnent le mode, M valide et passe à DECOMPTE.
    Debounce via DELAI_SECURITE. Mute session en place."""
    if ecoule < DELAI_SECURITE:
        return
    if event.key == TOUCHE_GAUCHE:
        print("Mode 10x15 sélectionné")
        session.mode_actuel = "10x15"
    elif event.key == TOUCHE_DROITE:
        print("Mode Bandelettes sélectionné")
        session.mode_actuel = "strips"
    elif event.key == TOUCHE_MILIEU and session.mode_actuel:
        print(f"🚀 {session.mode_actuel} Validé !")
        session.photos_validees = []
        session.dernier_clic_time = maintenant
        session.etat = Etat.DECOMPTE


def _handle_validation_10x15(event: pygame.event.Event, session: SessionState,  # type: ignore
                             maintenant: float) -> None:
    """VALIDATION mode 10x15 : retake / imprimer / abandon (debounce géré par caller)."""
    if event.key == TOUCHE_GAUCHE:
        # Retake : archive en RETAKE puis retourne au décompte
        print("LOG: [10x15] -> Refaire : Archivage RETAKE et relance")
        try:
            p = executer_avec_spinner(
                lambda: MontageGenerator10x15.final(session.photos_validees, session.id_session_timestamp),
                TXT_PREPARATION_IMP,
            )
            dest = os.path.join(PATH_SKIPPED_RETAKE, f"{PREFIXE_RETAKE}_{session.id_session_timestamp}.jpg")
            shutil.move(p, dest)
        except Exception as e:
            log_critical(f"Erreur 10x15 Retake: {e}")
        session.photos_validees = []
        session.etat = Etat.DECOMPTE
        session.dernier_clic_time = maintenant

    elif event.key == TOUCHE_MILIEU:
        # Imprimer direct + retour accueil
        print("LOG: [10x15] -> Impression directe et Accueil")
        issue = traiter_impression_session(session)
        pygame.event.clear()
        terminer_session_et_revenir_accueil(issue)
        session.dernier_clic_time = maintenant

    elif event.key == TOUCHE_DROITE:
        # Abandon : archive en DELETED et retour accueil
        print("LOG: [10x15] -> Abandon : Archivage DELETED et Accueil")
        try:
            p = executer_avec_spinner(
                lambda: MontageGenerator10x15.final(session.photos_validees, session.id_session_timestamp),
                TXT_PREPARATION_IMP,
            )
            dest = os.path.join(PATH_SKIPPED_DELETED, f"{PREFIXE_DELETED}_{session.id_session_timestamp}.jpg")
            shutil.move(p, dest)
        except Exception as e:
            log_critical(f"Erreur 10x15 Deleted: {e}")
        terminer_session_et_revenir_accueil("abandoned")
        session.dernier_clic_time = maintenant


def _handle_validation_strips(event: pygame.event.Event, session: SessionState,  # type: ignore
                              maintenant: float) -> None:
    """VALIDATION mode strips : retake dernière / valider-continue / annuler."""
    if event.key == TOUCHE_GAUCHE:
        print("LOG: [Strips] -> Refaire la dernière photo")
        if session.photos_validees:
            session.photos_validees.pop()
        session.img_preview_cache = None
        session.etat = Etat.DECOMPTE
        session.dernier_clic_time = maintenant

    elif event.key == TOUCHE_MILIEU:
        session.img_preview_cache = None
        if len(session.photos_validees) < 3:
            print(f"LOG: [Strips] -> Photo {len(session.photos_validees)} validée")
            session.etat = Etat.DECOMPTE
        else:
            print("LOG: [Strips] -> 3 photos OK, passage à l'écran FIN")
            session.path_montage = MontageGeneratorStrip.preview(session.photos_validees)
            session.etat = Etat.FIN
        session.dernier_clic_time = maintenant

    elif event.key == TOUCHE_DROITE:
        terminer_session_et_revenir_accueil("abandoned")
        session.dernier_clic_time = maintenant


def handle_validation_event(event: pygame.event.Event, session: SessionState,  # type: ignore
                            maintenant: float, ecoule: float) -> None:
    """VALIDATION : dispatch selon mode (10x15 vs strips). Debounce 0.5 s."""
    if ecoule < 0.5:
        return
    if session.mode_actuel == "10x15":
        _handle_validation_10x15(event, session, maintenant)
    elif session.mode_actuel == "strips":
        _handle_validation_strips(event, session, maintenant)


def handle_fin_event(event: pygame.event.Event, session: SessionState,   # type: ignore
                     maintenant: float, ecoule: float) -> None:
    """FIN : recommencer / imprimer / abandon (double-press confirm). Debounce 1 s.

    Le bouton droit (abandon) utilise une fenêtre de confirmation de
    DUREE_CONFIRM_ABANDON secondes : 1er appui arme, 2e appui confirme."""
    if ecoule < 1.0:
        return

    if event.key == TOUCHE_GAUCHE:
        # Recommencer : archive en RETAKE + repars au décompte (garde id_session)
        print("LOG: [FIN] -> Recommencer : Archivage et relance")
        session.abandon_confirm_until = 0.0
        try:
            if session.mode_actuel == "strips":
                p = executer_avec_spinner(
                    lambda: MontageGeneratorStrip.final(session.photos_validees, session.id_session_timestamp),
                    TXT_PREPARATION_IMP,
                )
            else:
                p = executer_avec_spinner(
                    lambda: MontageGenerator10x15.final(session.photos_validees, session.id_session_timestamp),
                    TXT_PREPARATION_IMP,
                )
            if os.path.exists(p):
                nom_dest = f"{PREFIXE_RETAKE}_{session.id_session_timestamp}.jpg"
                shutil.move(p, os.path.join(PATH_SKIPPED_RETAKE, nom_dest))
        except Exception as e:
            log_critical(f"Erreur archivage Recommencer : {e}")

        session.photos_validees = []
        session.img_preview_cache = None
        session.path_montage = ""
        session.etat = Etat.DECOMPTE
        session.dernier_clic_time = maintenant
        pygame.event.clear()
        return

    if event.key == TOUCHE_MILIEU:
        # Imprimer : génère HD, copie en PRINT_<mode>, envoie CUPS
        print(f"LOG: [FIN] -> Impression ({session.mode_actuel})")
        session.abandon_confirm_until = 0.0
        issue = traiter_impression_session(session)
        pygame.event.clear()
        terminer_session_et_revenir_accueil(issue)
        session.dernier_clic_time = maintenant
        return

    if event.key == TOUCHE_DROITE:
        # Abandon avec confirmation double-press
        if session.abandon_confirm_until and time.time() < session.abandon_confirm_until:
            # 2e appui dans la fenêtre → abandon confirmé
            print("LOG: [FIN] -> Abandon confirmé (deleted_)")
            session.abandon_confirm_until = 0.0
            try:
                if session.mode_actuel == "strips":
                    p = executer_avec_spinner(
                        lambda: MontageGeneratorStrip.final(session.photos_validees, session.id_session_timestamp),
                        TXT_PREPARATION_IMP,
                    )
                else:
                    p = executer_avec_spinner(
                        lambda: MontageGenerator10x15.final(session.photos_validees, session.id_session_timestamp),
                        TXT_PREPARATION_IMP,
                    )
                if os.path.exists(p):
                    nom_deleted = f"{PREFIXE_DELETED}_{session.id_session_timestamp}.jpg"
                    shutil.move(p, os.path.join(PATH_SKIPPED_DELETED, nom_deleted))
            except Exception as e:
                log_critical(f"Erreur archivage Supprimer : {e}")
            terminer_session_et_revenir_accueil("abandoned")
            session.dernier_clic_time = maintenant
        else:
            # 1er appui → on arme la fenêtre de confirmation
            print("LOG: [FIN] -> Demande de confirmation abandon")
            session.abandon_confirm_until = time.time() + DUREE_CONFIRM_ABANDON
            session.dernier_clic_time = maintenant


# ========================================================================================================
# --- BOUCLE PRINCIPALE --- ##############################################################################
# ========================================================================================================

def main() -> None:
    """Point d'entrée runtime. Importer ce module ne lance plus le kiosque."""
    signal.signal(signal.SIGTERM, demander_arret)
    signal.signal(signal.SIGINT, demander_arret)
    _initialiser_runtime()

    try:
        # --- Splash de connexion caméra (Sprint 2.1) ---
        # Si `camera` a été obtenue à l'init top du fichier, le splash se ferme immédiatement.
        # Sinon on montre un écran visible avec retry jusqu'à TIMEOUT_SPLASH_CAMERA.
        splash_connexion_camera(camera_mgr)

        while running:
            screen.fill((10, 10, 10))

            # --------------------------------------------------------------------------------------------
            # --- 1 ------ GESTION DES ÉVÉNEMENTS (TOUCHES) --- ##########################################
            # --------------------------------------------------------------------------------------------
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    demander_arret()

                # ON VÉRIFIE QUE C'EST UNE TOUCHE CLAVIER
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        demander_arret()
                        continue

                    maintenant = time.time()
                    ecoule = maintenant - session.dernier_clic_time

                    # Sprint 6.2 : si le slideshow était actif (idle > seuil en ACCUEIL), la 1re
                    # touche ne déclenche aucune action — elle réveille juste l'interface.
                    slideshow_etait_actif = (
                        session.etat is Etat.ACCUEIL
                        and session.mode_actuel is None
                        and (maintenant - session.last_activity_ts) > DUREE_IDLE_SLIDESHOW
                    )
                    session.last_activity_ts = maintenant
                    if slideshow_etait_actif:
                        continue

                    # Dispatch par état vers le handler approprié
                    if session.etat is Etat.ACCUEIL:
                        handle_accueil_event(event, session, maintenant, ecoule)
                    elif session.etat is Etat.VALIDATION:
                        handle_validation_event(event, session, maintenant, ecoule)
                    elif session.etat is Etat.FIN:
                        handle_fin_event(event, session, maintenant, ecoule)

            # --------------------------------------------------------------------------------------------
            # --- 2 ------ DESSIN A L'ECRAN --- ##########################################################
            # --------------------------------------------------------------------------------------------

            if session.etat is Etat.ACCUEIL:
                render_accueil(session)

            elif session.etat is Etat.DECOMPTE:
                render_decompte(session)
                continue

            elif session.etat is Etat.VALIDATION:
                if render_validation(session):
                    continue  # auto-advance burst → on saute au prochain tour

            elif session.etat is Etat.FIN:
                render_fin(session)

            # --- Synchronisation des LEDs Arduino avec l'état courant ---
            # Les messages série ne sont émis que lors des transitions (mémorisation interne),
            # donc l'appel est quasi-gratuit à 30 FPS.
            if arduino_ctrl is not None:
                arduino_ctrl.tick(
                    etat_name=session.etat.value,
                    mode_actuel=session.mode_actuel,
                    abandon_armed=(session.abandon_confirm_until and time.time() < session.abandon_confirm_until),
                )

            pygame.display.flip()
            clock.tick(30)
    finally:
        if arduino_ctrl is not None:
            arduino_ctrl.close()
        if camera_mgr is not None:
            camera_mgr.close()
        pygame.quit()


if __name__ == "__main__":
    main()