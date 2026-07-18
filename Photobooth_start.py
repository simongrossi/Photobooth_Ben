from __future__ import annotations

# Imports explicites depuis config (plus de `import *` pour dépendances visibles).
# Liste triée alphabétiquement, mise à jour en ajoutant de nouvelles constantes.
from config import (
    ACTIVER_DIAPORAMA_VEILLE, ACTIVER_IMPRESSION, ACTIVER_IMPRESSIONS_MULTIPLES,
    ACTIVER_QUOTA_IMPRESSIONS,
    ALPHA_TEXTE_REPOS, ARDUINO_BAUDRATE, ARDUINO_ENABLED, ARDUINO_PORT,
    BANDEAU_10X15, BANDEAU_ACCUEIL, BANDEAU_ALPHA,
    BANDEAU_COULEUR, BANDEAU_HAUTEUR, BANDEAU_STRIP, COULEUR_DECOMPTE,
    COULEUR_FLASH, COULEUR_SOURIEZ, COULEUR_TEXTE_OFF, COULEUR_TEXTE_ON, COULEUR_TEXTE_REPOS,
    DELAI_DEBLOCAGE_QUOTA, DELAI_SECURITE,
    DUREE_CONFIRM_ABANDON, DUREE_FLASH_BLANC, DUREE_IDLE_SLIDESHOW, DUREE_PAR_IMAGE_SLIDESHOW,
    BG_ACCUEIL_EFFECTIF, FORMAT_TIMESTAMP, HEIGHT,
    INTERVALLE_CHECK_DISQUE_S, INTERVALLE_CHECK_TEMP_S, LARGEUR_ICONE_10X15, LARGEUR_ICONE_STRIP, MARGE_ACCUEIL,
    MODE_10x15, MODE_STRIP, NB_MAX_IMAGES_SLIDESHOW,
    NOM_IMPRIMANTE_10X15, NOM_IMPRIMANTE_STRIP, OFFSET_DROITE_10X15, OFFSET_DROITE_STRIP,
    PATH_DATA, PATH_IMG_10X15, PATH_IMG_STRIP, PATH_PRINT,
    PATH_PRINT_10X15, PATH_PRINT_STRIP, PATH_RAW, PATH_SKIPPED,
    PATH_SKIPPED_DELETED, PATH_SKIPPED_RETAKE, PATH_SOUNDS, PATH_TEMP,
    PATH_SLIDESHOW_PERSO, POLICE_EFFECTIVE, PREFIXE_DELETED, PREFIXE_PRINT_10X15, PREFIXE_PRINT_STRIP,
    PREFIXE_RAW, PREFIXE_RETAKE, PULSE_LENT_MAX, PULSE_LENT_MIN, PULSE_LENT_VITESSE, PULSE_MAX,
    PULSE_MIN, PULSE_VITESSE,
    QUOTA_IMPRESSIONS_INCREMENT,
    SEUIL_DISQUE_CRITIQUE_MB, SEUIL_TEMP_CRITIQUE_C,
    STRIP_BURST_DELAI_S, STRIP_MODE_BURST,
    TAILLE_DECOMPTE, TAILLE_TEXTE_BANDEAU,
    TEMP_PATH,
    TAILLE_TEXTE_BOUTON, TAILLE_TITRE_ACCUEIL, TEMPS_DECOMPTE, TEXTE_PHOTO_COUNT,
    TOUCHE_DROITE, TOUCHE_GAUCHE, TOUCHE_MILIEU,
    TXT_BURST_COUNTDOWN, TXT_ERREUR_CAPTURE,
    TXT_ERREUR_IMPRIMANTE, TXT_PREPARATION_IMP, TXT_SLIDESHOW_INVITATION, WIDTH, ZOOM_FACTOR,
    MAX_COPIES_IMPRESSION,
)
import config  # accès qualifié `config.X` dans les render functions
try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]
import gc
import os
import signal
import sys
import time
import shutil
import math

import threading # Assure-toi que cet import est présent au tout début de ton script global
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
from core.evenements import charger_evenement_actif  # noqa: E402
from core import quota as quota_mgr  # noqa: E402
from core.quota import SaisieSequence  # noqa: E402


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
    import time

    nom_final = f"{PREFIXE_RAW}_{id_session}_{index_photo}.jpg"
    chemin_complet = os.path.join(PATH_RAW, nom_final)

    # 1. FLASH BLANC pur (effet "shutter" bref)
    screen.fill(COULEUR_FLASH)
    pygame.display.flip()
    jouer_son("shutter")
    time.sleep(DUREE_FLASH_BLANC)

    chevrons = _get_chevrons_capture()

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
        
        # --- ENTRÉE EN SCÈNE DU CHENILLARD ---
        if chevrons:
            cx = (WIDTH // 2) - (chevrons[0].get_width() // 2)
            cy = (HEIGHT // 5) - (chevrons[0].get_height() // 2)

            etape_animation = int(time.time() * 4) % 3

            for index, chevron in enumerate(chevrons):
                if index == etape_animation:
                    chevron.set_alpha(255)
                else:
                    chevron.set_alpha(50)
                
                screen.blit(chevron, (cx, cy))

        # --- AFFICHAGE DU TEXTE SOURIEZ ---
        try:
            dots = "." * (1 + (frame // 10) % 3)
            txt_flash = font_titre.render(f"SOURIEZ {dots}", True, COULEUR_SOURIEZ)
            text_x = (WIDTH // 2) - (txt_flash.get_width() // 2)
            text_y = (HEIGHT // 2) - (txt_flash.get_height() // 2) + 100
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
from core.monitoring import (  # noqa: E402
    DiskMonitor,
    TempMonitor,
    formater_ligne_perf,
    lire_rss_mb,
    lister_images_slideshow,
    doit_rafraichir_slideshow,
)
from core.performance import ecrire_performance, resumer_durees  # noqa: E402


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
_perf_capture_num = 0  # compteur de captures depuis le lancement (instrumentation #20)
_chevrons_capture_cache = None
_texte_surface_cache = {}
_overlay_abandon_cache = None
fond_accueil = None
icon_10x15_norm = None
icon_10x15_select = None
icon_strip_norm = None
icon_strip_select = None


def _surface_texte_cache(font, texte: str, couleur: tuple, alpha: int = 255):
    """Retourne une surface de texte immuable partagée entre les frames."""
    key = (id(font), texte, couleur, alpha)
    surf = _texte_surface_cache.get(key)
    if surf is None:
        surf = font.render(texte, True, couleur)
        if alpha != 255:
            surf.set_alpha(alpha)
        _texte_surface_cache[key] = surf
    return surf


def _get_overlay_abandon():
    """Construit une seule fois le voile plein écran de confirmation."""
    global _overlay_abandon_cache
    if _overlay_abandon_cache is None:
        _overlay_abandon_cache = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        _overlay_abandon_cache.fill((0, 0, 0, 170))
    return _overlay_abandon_cache


def _get_chevrons_capture():
    """Charge et redimensionne une seule fois les sprites de capture."""
    global _chevrons_capture_cache
    if _chevrons_capture_cache is not None:
        return _chevrons_capture_cache
    try:
        _chevrons_capture_cache = [
            pygame.transform.smoothscale(
                pygame.image.load(
                    os.path.join(config.PATH_INTERFACE, f"fleche_{i}.png")
                ).convert_alpha(),
                (100, 200),
            )
            for i in range(1, 4)
        ]
    except pygame.error:
        log_warning("Impossible de charger les images fleche_1, 2 ou 3.png")
        _chevrons_capture_cache = []
    return _chevrons_capture_cache


def _charger_polices():
    """Charge les polices pygame ou bascule sur Arial si l'asset manque."""
    try:
        if os.path.exists(POLICE_EFFECTIVE):
            return (
                pygame.font.Font(POLICE_EFFECTIVE, TAILLE_TITRE_ACCUEIL),
                pygame.font.Font(POLICE_EFFECTIVE, TAILLE_TEXTE_BOUTON),
                pygame.font.Font(POLICE_EFFECTIVE, TAILLE_TEXTE_BANDEAU),
                pygame.font.Font(POLICE_EFFECTIVE, TAILLE_DECOMPTE),
                pygame.font.Font(POLICE_EFFECTIVE, config.STRIP_FILIGRANE_TAILLE),
                pygame.font.Font(POLICE_EFFECTIVE, config.TAILLE_TEXTE_ALERTE),
            )
        raise FileNotFoundError
    except Exception:
        return (
            pygame.font.SysFont("Arial", TAILLE_TITRE_ACCUEIL, bold=True),
            pygame.font.SysFont("Arial", TAILLE_TEXTE_BOUTON),
            pygame.font.SysFont("Arial", TAILLE_TEXTE_BANDEAU, bold=True),
            pygame.font.SysFont("Arial", TAILLE_DECOMPTE, bold=True),
            pygame.font.SysFont("Arial", config.STRIP_FILIGRANE_TAILLE, bold=True),
            pygame.font.SysFont("Arial", config.TAILLE_TEXTE_ALERTE, bold=True),
        )


def _initialiser_runtime() -> None:
    """Initialise les singletons runtime. Aucun effet de bord lourd à l'import."""
    global camera_mgr, screen, clock
    global font_titre, font_boutons, font_bandeau, font_decompte, font_filigrane, font_alerte
    global UIContext, AccueilAssets, setup_sounds, jouer_son, draw_text_shadow_soft
    global inserer_background, afficher_message_plein_ecran, executer_avec_spinner
    global ecran_erreur, ecran_attente_impression, splash_connexion_camera
    global arduino_ctrl, disk_monitor, temp_monitor, BANDEAU_CACHE, session, running
    global slideshow_images, slideshow_last_refresh, slideshow_cached_surface, slideshow_cached_for_idx
    global fond_accueil, icon_10x15_norm, icon_10x15_select, icon_strip_norm, icon_strip_select

    if pygame is None:
        raise RuntimeError("pygame est requis pour lancer Photobooth_start.py")

    _preparer_dossiers_et_logs()


#Purger file d'attent CUPS au démarrage pour éviter les blocages si des tâches résiduelles sont présentes.
    printer_mgr.purger_file_attente()

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

    pygame.init()
    _display_flags = (pygame.FULLSCREEN | pygame.NOFRAME) if config.KIOSK_FULLSCREEN else 0
    screen = pygame.display.set_mode((WIDTH, HEIGHT), _display_flags)
    if config.KIOSK_FULLSCREEN:
        pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()
    pygame.font.init()

    font_titre, font_boutons, font_bandeau, font_decompte, font_filigrane, font_alerte = _charger_polices()
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
        bg_path=BG_ACCUEIL_EFFECTIF,
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
    duree_s = time.time() - session.session_start_ts if session.session_start_ts else 0.0
    ecrire_performance(
        "session_end",
        session_id=session.id_session_timestamp or None,
        mode=session.mode_actuel,
        issue=issue,
        photos=len(session.photos_validees),
        duration_ms=round(duree_s * 1000, 3),
        rss_mb=lire_rss_mb(),
        temperature_c=temp_monitor.temp_c if temp_monitor is not None else None,
    )
    _terminer_session_et_revenir_accueil(session, issue)


def _journaliser_action(action: str, **details) -> None:
    """Trace uniquement les actions utilisateur, jamais les frames."""
    log_info(f"[ACTION] {action} mode={session.mode_actuel}")
    ecrire_performance(
        "action",
        action=action,
        session_id=session.id_session_timestamp or None,
        mode=session.mode_actuel,
        **details,
    )


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

def demander_nombre_copies(session: SessionState) -> int:
    """Affiche un écran avec un compteur dynamique pour choisir le nombre de copies.
    - S'adapte au mode 'strips' en proposant uniquement des multiples de 2 (2 ou 4 copies).
    - Titre à HEIGHT // 5
    - Gros chiffre central en blanc
    - Bouton central vert : IMPRIMER
    - MOINS en blanc (ou gris intermédiaire si min atteint)
    - PLUS en rouge (ou gris intermédiaire si max atteint)
    - Bandeau de 90px collé tout en bas de l'écran."""
    log_info(f"📺 Affichage de l'écran choix du nombre de copies (Mode actuel : {session.mode_actuel})")
    
    # En mode strips, le minimum est de 2 bandelettes, sinon 1 pour le 10x15
    est_strip = (session.mode_actuel == "strips")
    compteur = 2 if est_strip else 1 
    
    selection_validee = False
    temps_debut = time.time()
    DELAI_CHOIX = 20.0 

    # --- PALETTE DE COULEURS DE L'ÉCRAN ---
    COULEUR_VERTE = (0, 200, 0)
    COULEUR_BLANCHE = (255, 255, 255)
    COULEUR_ROUGE = (220, 50, 50)       
    COULEUR_GRIS_LISIBLE = (70, 70, 70) 

    # --- CONFIGURATION ET POSITIONNEMENT DU BANDEAU ---
    HAUTEUR_BANDEAU_CHOIX = 90  
    bandeau_bas = pygame.Surface((WIDTH, HAUTEUR_BANDEAU_CHOIX))
    bandeau_bas.fill((0, 0, 0))
    bandeau_bas.set_alpha(90)   
    y_bandeau = HEIGHT - HAUTEUR_BANDEAU_CHOIX

    # Plafonnement par le quota : on ne propose jamais plus de copies que de
    # feuilles DNP restantes (1 feuille = 2 bandelettes en strips). Le blocage
    # total (restant = 0) est géré en amont par _verifier_quota_ou_debloquer.
    if ACTIVER_QUOTA_IMPRESSIONS:
        restant = quota_mgr.quota_restant()
        plafond_quota = restant * 2 if est_strip else restant
    else:
        plafond_quota = None

    while not selection_validee:
        # Définition dynamique du pas (step) et du maximum selon le mode
        pas = 2 if est_strip else 1
        minimum_autorise = 2 if est_strip else 1
        maximum_autorise = 4 if est_strip else MAX_COPIES_IMPRESSION
        if plafond_quota is not None:
            maximum_autorise = max(minimum_autorise, min(maximum_autorise, plafond_quota))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
                
            elif event.type == pygame.KEYDOWN:
                if event.key == TOUCHE_GAUCHE:
                    if compteur > minimum_autorise:
                        compteur -= pas
                        jouer_son("click")
                        
                elif event.key == TOUCHE_DROITE:
                    if compteur < maximum_autorise:
                        compteur += pas
                        jouer_son("click")
                        
                elif event.key == TOUCHE_MILIEU:
                    selection_validee = True

        if time.time() - temps_debut > DELAI_CHOIX:
            log_info("⏰ Temps écoulé, validation auto.")
            selection_validee = True

        # 1. FOND DE L'ACCUEIL
        inserer_background(screen, fond_accueil)
        
        # 2. TITRE
        texte_titre = "NOMBRE D'IMPRESSIONS" if est_strip else "NOMBRE D'IMPRESSIONS"
        txt_question = font_boutons.render(texte_titre, True, COULEUR_BLANCHE)
        y_titre = HEIGHT // 5 
        screen.blit(txt_question, (WIDTH // 2 - txt_question.get_width() // 2, y_titre))

        # 3. LE COMPTEUR (Gros chiffre central en blanc)
        txt_compteur = font_decompte.render(str(compteur), True, COULEUR_BLANCHE)
        cx = WIDTH // 2 - txt_compteur.get_width() // 2
        cy = HEIGHT // 2 - txt_compteur.get_height() // 2
        screen.blit(txt_compteur, (cx, cy))

        # 4. RENDU DU BANDEAU NOIR COLLÉ EN BAS
        screen.blit(bandeau_bas, (0, y_bandeau))

        # 5. GESTION DYNAMIQUE DES COULEURS DES TEXTES
        couleur_moins = COULEUR_BLANCHE if compteur > minimum_autorise else COULEUR_GRIS_LISIBLE
        couleur_plus = COULEUR_ROUGE if compteur < maximum_autorise else COULEUR_GRIS_LISIBLE

        txt_btn_gauche = font_boutons.render("[ - ] MOINS", True, couleur_moins)
        txt_btn_milieu = font_boutons.render("[ IMPRIMER ]", True, COULEUR_VERTE)
        txt_btn_droite = font_boutons.render("PLUS [ + ]", True, couleur_plus)

        # Alignement vertical au milieu du bandeau du bas
        y_boutons = y_bandeau + (HAUTEUR_BANDEAU_CHOIX // 2) - (txt_btn_milieu.get_height() // 2)
        MARGE_BORD = 80 
        
        screen.blit(txt_btn_gauche, (MARGE_BORD, y_boutons))
        screen.blit(txt_btn_milieu, (WIDTH // 2 - txt_btn_milieu.get_width() // 2, y_boutons))
        pos_droite = WIDTH - txt_btn_droite.get_width() - MARGE_BORD
        screen.blit(txt_btn_droite, (pos_droite, y_boutons))

        pygame.display.flip()
        clock.tick(30)

    # --- CALCUL DYNAMIQUE ET ADAPTÉ DU TEMPS POUR LE FICHIER CONFIG ---
    if est_strip:
        # 2 bandelettes = 1 impression réelle = 15s | 4 bandelettes = 2 impressions réelles = 30s
        config.TEMPS_ATTENTE_IMP = int((compteur / 2) * 15)
    else:
        config.TEMPS_ATTENTE_IMP = compteur * 15

    log_info(f"🔢 Choix validé : {compteur} | Temps configuré : {config.TEMPS_ATTENTE_IMP}s")
    return compteur


def ecran_deblocage_quota(session: SessionState) -> bool:
    """Écran « quota atteint » : saisie du code G→D→M puis confirmation par re-saisie.

    Deux phases pilotées par la même séquence (gauche→droite→milieu) :
    la première saisit le code, la seconde le confirme pour écarter les fausses
    détections des boutons. Succès → quota += QUOTA_IMPRESSIONS_INCREMENT et
    retourne True (l'impression peut s'enchaîner). Inactivité de
    DELAI_DEBLOCAGE_QUOTA secondes ou mauvaise touche en phase 2 → retour
    phase 1 / abandon (False). La séquence n'est volontairement pas affichée.
    """
    log_info("🔒 Quota d'impressions atteint : affichage de l'écran de déblocage")
    sequence = SaisieSequence((TOUCHE_GAUCHE, TOUCHE_DROITE, TOUCHE_MILIEU))
    phase_confirmation = False
    dernier_appui_ts = time.time()
    flash_rouge_until = 0.0
    ANTI_REBOND_S = 0.3  # DELAI_SECURITE (2 s) rendrait la séquence insaisissable

    COULEUR_BLANCHE = (255, 255, 255)
    COULEUR_ROUGE = (220, 50, 50)
    COULEUR_VERTE = (0, 200, 0)
    COULEUR_GRIS = (70, 70, 70)

    while True:
        maintenant = time.time()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN and event.key in (TOUCHE_GAUCHE, TOUCHE_MILIEU, TOUCHE_DROITE):
                if maintenant - dernier_appui_ts < ANTI_REBOND_S:
                    continue
                dernier_appui_ts = maintenant
                resultat = sequence.presser(event.key)
                if resultat == "reset":
                    jouer_son("beep")
                    flash_rouge_until = maintenant + 0.25
                    if phase_confirmation:
                        # Erreur pendant la confirmation : tout reprendre du début
                        phase_confirmation = False
                elif resultat == "en_cours":
                    jouer_son("click")
                elif resultat == "complete":
                    jouer_son("click")
                    if not phase_confirmation:
                        phase_confirmation = True
                        sequence.reinitialiser()
                    else:
                        etat = quota_mgr.debloquer(QUOTA_IMPRESSIONS_INCREMENT)
                        ecrire_performance(
                            "quota_deblocage",
                            source="kiosque",
                            increment=QUOTA_IMPRESSIONS_INCREMENT,
                            quota=etat["quota"],
                            tirages_total=etat["tirages_total"],
                        )
                        log_info(
                            f"🔓 Quota débloqué : +{QUOTA_IMPRESSIONS_INCREMENT} "
                            f"(quota={etat['quota']}, tirages={etat['tirages_total']})"
                        )
                        jouer_son("success")
                        afficher_message_plein_ecran(
                            f"Quota debloque : +{QUOTA_IMPRESSIONS_INCREMENT} impressions",
                            couleur=COULEUR_VERTE,
                        )
                        time.sleep(1.5)
                        return True

        if maintenant - dernier_appui_ts > DELAI_DEBLOCAGE_QUOTA:
            log_info("⏰ Écran de déblocage quota : timeout, retour sans déblocage")
            return False

        # --- RENDU ---
        inserer_background(screen, fond_accueil)
        if maintenant < flash_rouge_until:
            voile = pygame.Surface((WIDTH, HEIGHT))
            voile.fill(COULEUR_ROUGE)
            voile.set_alpha(90)
            screen.blit(voile, (0, 0))

        titre = "QUOTA D'IMPRESSIONS ATTEINT"
        sous_titre = (
            "Confirmer : ressaisir le code" if phase_confirmation
            else "Saisir le code de deblocage"
        )
        txt_titre = font_boutons.render(titre, True, COULEUR_ROUGE)
        screen.blit(txt_titre, (WIDTH // 2 - txt_titre.get_width() // 2, HEIGHT // 5))
        couleur_sous_titre = COULEUR_VERTE if phase_confirmation else COULEUR_BLANCHE
        txt_sous = font_boutons.render(sous_titre, True, couleur_sous_titre)
        screen.blit(txt_sous, (WIDTH // 2 - txt_sous.get_width() // 2, HEIGHT // 5 + 70))

        # Pastilles de progression (une par touche de la séquence)
        nb_pastilles = len(sequence.sequence)
        rayon, espace = 22, 90
        x0 = WIDTH // 2 - ((nb_pastilles - 1) * espace) // 2
        y0 = HEIGHT // 2
        for i in range(nb_pastilles):
            couleur = COULEUR_VERTE if i < sequence.progression else COULEUR_GRIS
            pygame.draw.circle(screen, couleur, (x0 + i * espace, y0), rayon)

        pygame.display.flip()
        clock.tick(30)


def _verifier_quota_ou_debloquer(session: SessionState) -> bool:
    """True si l'impression peut continuer (quota restant, bridage désactivé,
    ou déblocage par code réussi)."""
    if not ACTIVER_QUOTA_IMPRESSIONS or quota_mgr.quota_restant() > 0:
        return True
    _journaliser_action("quota_atteint")
    return ecran_deblocage_quota(session)


def traiter_impression_session(session) -> str:
    """Genere, archive et imprime le montage final avec diagnostic precis."""
    try:
        perf_montage_t0 = time.perf_counter()
        p = executer_avec_spinner(
            lambda: _generer_montage_final(session),
            TXT_PREPARATION_IMP,
        )
        duree_montage_ms = (time.perf_counter() - perf_montage_t0) * 1000
        log_info(
            f"[PERF] montage_final mode={session.mode_actuel} "
            f"duree={duree_montage_ms / 1000:.3f}s"
        )
        ecrire_performance(
            "montage_final",
            session_id=session.id_session_timestamp,
            mode=session.mode_actuel,
            duration_ms=round(duree_montage_ms, 3),
        )
        destination = _destination_montage_imprime(session)

        # Copie si necessaire (Strips gerent leur propre chemin)
        if session.mode_actuel != "strips":
            shutil.copy(p, destination)
        else:
            destination = p

        if not ACTIVER_IMPRESSION:
            log_info(f"Impression desactivee : montage enregistre ({destination})")
            afficher_message_plein_ecran("Impression desactivee - montage enregistre", couleur=(255, 215, 0))
            time.sleep(1.2)
            return "print_disabled"

        # Sans copies multiples, une pression lance directement une seule feuille :
        # 1 photo en 10×15 ou les 2 bandelettes déjà assemblées en mode strips.
        est_strip = (session.mode_actuel == "strips")
        nb_copies = demander_nombre_copies(session) if ACTIVER_IMPRESSIONS_MULTIPLES else (2 if est_strip else 1)

        # --- CONVERSION EN IMPRESSIONS PHYSIQUES REELLES ---
        nb_impressions_reelles = int(nb_copies / 2) if est_strip else nb_copies

        # --- MODIFICATION ANTI-FLASH ---
        from ui import helpers
        if hasattr(helpers, '_fond_impression_cache') and helpers._fond_impression_cache:
            helpers.UIContext.screen.blit(helpers._fond_impression_cache, (0, 0))
            pygame.display.flip()

        # ===========================================================
        # --- VERIFICATION DE SECURITE (Etat initial de la machine) ---
        # ===========================================================
        # is_ready renvoie True si prêt, sinon une chaîne décrivant le problème
        # (mémorisée aussi dans last_error). Une chaîne est truthy : on teste
        # `is not True` pour ne PAS partir imprimer sur « FILE D'ATTENTE PLEINE ».
        verification_t0 = time.perf_counter()
        etat_imprimante = printer_mgr.is_ready(session.mode_actuel)
        verification_ms = (time.perf_counter() - verification_t0) * 1000
        ecrire_performance(
            "printer_check",
            session_id=session.id_session_timestamp,
            mode=session.mode_actuel,
            duration_ms=round(verification_ms, 3),
            ready=etat_imprimante is True,
            detail=None if etat_imprimante is True else str(etat_imprimante),
        )
        if etat_imprimante is not True:
            log_warning(f"Impression bloquée : {etat_imprimante}")
            ecran_erreur(printer_mgr.last_error or TXT_ERREUR_IMPRIMANTE)
            return "print_failed"

        # ===========================================================
        # --- ETAPE 1 : FONCTION INTERNE D'ENVOI EN ARRIÈRE-PLAN ---
        # ===========================================================
        perf_session_id = session.id_session_timestamp
        perf_mode = session.mode_actuel

        def boucle_envoi_dnp():
            for i in range(nb_impressions_reelles):
                log_info(f"🚀 [Thread DNP] Envoi de l'impression physique {i+1}/{nb_impressions_reelles}...")

                # CUPS copie le contenu dans son spool : inutile de dupliquer le
                # JPEG sur la carte SD pour chaque ticket.
                envoi_t0 = time.perf_counter()
                envoi_ok = printer_mgr.send(destination, perf_mode, verifier=False)
                if envoi_ok:
                    # Une feuille DNP réellement partie vers CUPS = un tirage compté.
                    quota_mgr.enregistrer_tirage(1)
                ecrire_performance(
                    "printer_submit",
                    session_id=perf_session_id,
                    mode=perf_mode,
                    copy=i + 1,
                    duration_ms=round((time.perf_counter() - envoi_t0) * 1000, 3),
                    success=envoi_ok,
                )

                # Attente entre deux impressions pour ne pas saturer CUPS
                if nb_impressions_reelles > 1 and i < (nb_impressions_reelles - 1):
                    log_info("⏳ Thread DNP : Pause de 15s avant le prochain envoi...")
                    time.sleep(15.0)
            
            # Une fois toutes les impressions envoyées, on joue le son de succès
            jouer_son("success")

        # ===========================================================
        # --- ETAPE 2 : CONFIGURATION DU TIMER ET LANCEMENT CONCURRENT ---
        # ===========================================================
        # 1 photo = 15s | 2 photos = 32s | 3 photos = 48s
        if nb_impressions_reelles == 1:
            helpers.TEMPS_ATTENTE_IMP = 14
        else:
            helpers.TEMPS_ATTENTE_IMP = nb_impressions_reelles * 13

        log_info(f"⏱️ Configuration de la roue visuelle sur {helpers.TEMPS_ATTENTE_IMP}s")
        
        # ON LANCE L'ENVOI DANS UN THREAD SÉPARÉ (Il s'exécute en arrière-plan)
        thread_imprimante = threading.Thread(target=boucle_envoi_dnp)
        thread_imprimante.daemon = True # S'arrête automatiquement si le programme principal coupe
        thread_imprimante.start()

        # ON LANCE IMMEDIATEMENT L'ECRAN DE LA ROUE (Qui s'affiche en même temps)
        ecran_attente_impression()
        
        return "printed"

    except Exception as e:
        log_critical(f"Erreur impression finale : {e}")
        ecran_erreur(TXT_ERREUR_IMPRIMANTE)
        return "print_failed"


def demander_arret(signum=None, frame=None) -> None:
    """Demande un arret propre de la boucle principale."""
    global running
    running = False
    if signum is not None:
        log_info(f"Signal d'arret recu ({signum})")



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
    maintenant = time.time()
    if doit_rafraichir_slideshow(slideshow_last_refresh, maintenant):
        slideshow_images = lister_images_slideshow(
            [PATH_PRINT_10X15, PATH_PRINT_STRIP, PATH_SLIDESHOW_PERSO], NB_MAX_IMAGES_SLIDESHOW,
        )
        slideshow_last_refresh = maintenant
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

    # --- CORRECTION : BANDEAU HARMONISÉ ---
    # 1. On affiche le même bandeau que sur l'accueil normal
    screen.blit(BANDEAU_CACHE, (0, HEIGHT - BANDEAU_HAUTEUR))

    # 2. Rendu du texte avec pulsation
    alpha_inv = 150 + int(80 * math.sin(time.time() * 2))
    inv_surf = _surface_texte_cache(font_bandeau, TXT_SLIDESHOW_INVITATION, (255, 255, 255))
    inv_surf.set_alpha(alpha_inv)
    
    # 3. Calcul du centrage parfait dans le bandeau
    inv_x = WIDTH // 2 - inv_surf.get_width() // 2
    
    # On utilise la même logique de centrage vertical que _render_accueil_normal
    # (Centre du bandeau - moitié de la hauteur du texte)
    inv_y = (HEIGHT - BANDEAU_HAUTEUR // 2) - (inv_surf.get_height() // 2)
    
    screen.blit(inv_surf, (inv_x, inv_y))


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
    if ACTIVER_DIAPORAMA_VEILLE and idle_seconds > DUREE_IDLE_SLIDESHOW and session.mode_actuel is None:
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
        if not session.evenement_charge:
            evenement = charger_evenement_actif()
            session.evenement_charge = True
            if evenement:
                session.evenement_id = evenement["id"]
                session.evenement_nom = evenement["nom"]
                session.evenement_tags = evenement["tags"]
        log_info(f"🚀 NOUVELLE SESSION : {session.id_session_timestamp}")
        ecrire_performance(
            "session_start",
            session_id=session.id_session_timestamp,
            mode=session.mode_actuel,
            event_id=session.evenement_id,
        )

    # Boucle du décompte visuel (+ instrumentation perf #20 : compte les frames
    # preview pour mesurer le fps réel du LiveView pendant le décompte)
    perf_frames_ok = 0
    perf_t0 = time.time()
    render_durations_ms = []
    derniere_preview_affichee = None
    derniere_generation = -1
    if camera_mgr is not None:
        camera_mgr.start_preview()
    for i in range(TEMPS_DECOMPTE, 0, -1):
        jouer_son("beep_final" if i == 1 else "beep")
        t_start = time.time()
        while time.time() - t_start < 1:
            render_t0 = time.perf_counter()
            if camera_mgr is not None:
                surf, generation = camera_mgr.get_preview_frame_info()
            else:
                surf, generation = None, -1
            if surf and generation != derniere_generation:
                perf_frames_ok += 1
                derniere_generation = generation
                derniere_preview_affichee = surf

            if derniere_preview_affichee:
                screen.blit(derniere_preview_affichee, (0, 0))

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
                        fili_surf = _surface_texte_cache(
                            font_filigrane,
                            str(photos_restantes),
                            COULEUR_DECOMPTE,
                            config.STRIP_FILIGRANE_ALPHA,
                        )
                        screen.blit(fili_surf, (
                            WIDTH // 2 - fili_surf.get_width() // 2,
                            HEIGHT // 2 - fili_surf.get_height() // 2,
                        ))

            else:
                # Le LiveView peut ne pas avoir encore livré sa première frame.
                # On garde un fond explicite et, surtout, le décompte reste visible.
                screen.fill((10, 10, 10))

            num_surf = _surface_texte_cache(font_decompte, str(i), COULEUR_DECOMPTE)
            screen.blit(num_surf, (WIDTH // 2 - num_surf.get_width() // 2, HEIGHT // 2 - num_surf.get_height() // 2))

            pygame.display.flip()
            render_durations_ms.append((time.perf_counter() - render_t0) * 1000)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    demander_arret()
            if not running:
                return
            clock.tick(30)

    # --- Instrumentation perf #20 : fps preview mesuré sur le décompte ---
    perf_elapsed = time.time() - perf_t0
    perf_fps = (perf_frames_ok / perf_elapsed) if perf_elapsed > 0 else None
    preview_metrics = camera_mgr.preview_metrics() if camera_mgr is not None else {}
    render_metrics = resumer_durees(render_durations_ms, seuil_lent_ms=33.3)

    # CAPTURE HQ + transition (chronométrée pour le log PERF)
    index_photo = len(session.photos_validees) + 1
    perf_t_cap = time.time()
    chemin_photo = capturer_hq(session.id_session_timestamp, index_photo)
    perf_capture_s = time.time() - perf_t_cap
    capture_metrics = camera_mgr.capture_metrics if camera_mgr is not None else {}
    rss_mb = lire_rss_mb()
    gc_objs = len(gc.get_objects())

    global _perf_capture_num
    _perf_capture_num += 1
    log_info(formater_ligne_perf(
        capture_num=_perf_capture_num,
        preview_fps=perf_fps,
        capture_s=perf_capture_s,
        rss_mb=rss_mb,
        gc_objs=gc_objs,
    ))
    ecrire_performance(
        "capture",
        session_id=session.id_session_timestamp,
        mode=session.mode_actuel,
        photo_index=index_photo,
        success=bool(chemin_photo),
        preview_fps=round(perf_fps, 3) if perf_fps is not None else None,
        countdown_render_ms=render_metrics,
        camera_preview=preview_metrics,
        capture_phases_ms=capture_metrics,
        capture_total_ms=round(perf_capture_s * 1000, 3),
        rss_mb=round(rss_mb, 3) if rss_mb is not None else None,
        gc_objs=gc_objs,
        temperature_c=temp_monitor.temp_c if temp_monitor is not None else None,
    )

    if chemin_photo:
        session.photos_validees.append(chemin_photo)
        session.etat = Etat.VALIDATION
    else:
        log_critical("Erreur capture : retour à l'accueil")
        ecran_erreur(TXT_ERREUR_CAPTURE)
        terminer_session_et_revenir_accueil("capture_failed")

    session.dernier_clic_time = time.time()


def _dessiner_texte_centre_avec_garde(screen, text: str, font, color: tuple, y: int, max_width: int) -> None:
    """Dessine un texte centré horizontalement, en le redimensionnant s'il dépasse max_width."""
    surf = font.render(text, True, color)
    if surf.get_width() > max_width:
        new_width = max_width
        new_height = int(surf.get_height() * (new_width / surf.get_width()))
        surf = pygame.transform.smoothscale(surf, (new_width, new_height))
    screen.blit(surf, (WIDTH // 2 - surf.get_width() // 2, y))


def _dessiner_actions_bandeau(actions: tuple[tuple[str, tuple], ...], y_bandeau: int) -> None:
    """Répartit les actions dans des zones égales sans chevauchement."""
    largeur_zone = WIDTH / len(actions)
    largeur_max = int(largeur_zone - 48)
    hauteur_max = BANDEAU_HAUTEUR - 10

    for index, (texte, couleur) in enumerate(actions):
        surf = _surface_texte_cache(font_bandeau, texte, couleur)
        facteur = min(1.0, largeur_max / surf.get_width(), hauteur_max / surf.get_height())
        if facteur < 1.0:
            nouvelle_taille = (
                max(1, round(surf.get_width() * facteur)),
                max(1, round(surf.get_height() * facteur)),
            )
            surf = pygame.transform.smoothscale(surf, nouvelle_taille)

        centre_x = (index + 0.5) * largeur_zone
        x = round(centre_x - surf.get_width() / 2)
        y = y_bandeau + (BANDEAU_HAUTEUR - surf.get_height()) // 2
        screen.blit(surf, (x, y))


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
        perf_preview_t0 = time.perf_counter()
        derniere_photo = session.photos_validees[-1]

        if session.mode_actuel == "strips":
            hauteur_cible = getattr(config, 'PREVISU_H_STRIP', 600)
            r_v = float(getattr(config, 'STRIP_PHOTO_RATIO', 1.0))
        else:
            hauteur_cible = getattr(config, 'PREVISU_H', 533)
            r_v = 0.66

        largeur_cible = int(hauteur_cible / r_v)

        with Image.open(derniere_photo) as raw_img:
            raw_img.draft("RGB", (largeur_cible, hauteur_cible))
            oriented = ImageOps.exif_transpose(raw_img)
        pil_img = ImageOps.fit(oriented, (largeur_cible, hauteur_cible), Image.Resampling.BILINEAR)
        session.img_preview_cache = pygame.image.fromstring(
            pil_img.tobytes(), pil_img.size, pil_img.mode
        ).convert()
        duree_preview_ms = (time.perf_counter() - perf_preview_t0) * 1000
        log_info(
            f"[PERF] preview_validation mode={session.mode_actuel} "
            f"duree={duree_preview_ms / 1000:.3f}s"
        )
        ecrire_performance(
            "preview_validation",
            session_id=session.id_session_timestamp,
            mode=session.mode_actuel,
            photo_index=len(session.photos_validees),
            duration_ms=round(duree_preview_ms, 3),
        )

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

    if session.mode_actuel == "strips":
        txt_g = config.TXT_VALID_REPRENDRE_STRIP
        txt_m = config.TXT_VALID_VALIDER_STRIP
        txt_d = config.TXT_VALID_ACCUEIL_STRIP
    else:
        txt_g = config.TXT_VALID_REPRENDRE_10X15
        txt_m = config.TXT_VALID_VALIDER_10X15
        txt_d = config.TXT_VALID_ACCUEIL_10X15

    _dessiner_actions_bandeau((
        (txt_g, config.COULEUR_TEXTE_G),
        (txt_m, config.COULEUR_TEXTE_M),
        (txt_d, config.COULEUR_TEXTE_D),
    ), y_b)

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
    
    # 4. Overlay de confirmation d'abandon (À insérer juste avant le return False)
    if session.abandon_confirm_until and time.time() < session.abandon_confirm_until:
        screen.blit(_get_overlay_abandon(), (0, 0))
        
        # Message principal (Titre rouge doux)
        _dessiner_texte_centre_avec_garde(screen, config.TXT_CONFIRM_ABANDON_1, font_alerte, (255, 120, 120), HEIGHT // 2 - 100, int(WIDTH * 0.55))
        
        # Message d'instruction (Petit texte blanc)
        _dessiner_texte_centre_avec_garde(screen, config.TXT_CONFIRM_ABANDON_2, font_bandeau, (255, 255, 255), HEIGHT // 2 + 40, int(WIDTH * 0.7))
        
    elif session.abandon_confirm_until:
        session.abandon_confirm_until = 0.0

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
    _dessiner_actions_bandeau((
        (config.TXT_BOUTON_REPRENDRE, config.COULEUR_TEXTE_G),
        (config.TXT_BOUTON_IMPRIMER, config.COULEUR_TEXTE_M),
        (config.TXT_BOUTON_SUPPRIMER, config.COULEUR_TEXTE_D),
    ), y_b)

    # 5. Overlay de confirmation d'abandon
    if session.abandon_confirm_until and time.time() < session.abandon_confirm_until:
        screen.blit(_get_overlay_abandon(), (0, 0))
        
        _dessiner_texte_centre_avec_garde(screen, config.TXT_CONFIRM_ABANDON_1, font_alerte, (255, 120, 120), HEIGHT // 2 - 120, int(WIDTH * 0.55))
        
        _dessiner_texte_centre_avec_garde(screen, config.TXT_CONFIRM_ABANDON_2, font_bandeau, (255, 255, 255), HEIGHT // 2 + 20, int(WIDTH * 0.7))
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
        session.mode_actuel = "10x15"
        _journaliser_action("select_format")
        if camera_mgr is not None:
            camera_mgr.start_preview()
    elif event.key == TOUCHE_DROITE:
        session.mode_actuel = "strips"
        _journaliser_action("select_format")
        if camera_mgr is not None:
            camera_mgr.start_preview()
    elif event.key == TOUCHE_MILIEU and session.mode_actuel:
        _journaliser_action("confirm_format")
        session.photos_validees = []
        session.dernier_clic_time = maintenant
        session.etat = Etat.DECOMPTE


def _handle_validation_10x15(event: pygame.event.Event, session: SessionState,  # type: ignore
                             maintenant: float) -> None:
    """VALIDATION mode 10x15 : retake / imprimer / abandon (debounce géré par caller)."""
    if event.key == TOUCHE_GAUCHE:
        # Retake : archive en RETAKE puis retourne au décompte
        _journaliser_action("retake")

        session.img_preview_cache = None

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
        _journaliser_action("print")
        session.abandon_confirm_until = 0.0
        if not _verifier_quota_ou_debloquer(session):
            # Quota atteint et déblocage refusé : la session reste affichée
            session.dernier_clic_time = maintenant
            pygame.event.clear()
            return
        issue = traiter_impression_session(session)
        pygame.event.clear()
        terminer_session_et_revenir_accueil(issue)
        session.dernier_clic_time = maintenant

    elif event.key == TOUCHE_DROITE:
        # Abandon avec confirmation double-press
        if session.abandon_confirm_until and time.time() < session.abandon_confirm_until:
            _journaliser_action("abandon_confirmed")
            session.abandon_confirm_until = 0.0
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
        else:
            _journaliser_action("abandon_requested")
            session.abandon_confirm_until = time.time() + DUREE_CONFIRM_ABANDON
        
        session.dernier_clic_time = maintenant


def _handle_validation_strips(event: pygame.event.Event, session: SessionState,  # type: ignore
                              maintenant: float) -> None:
    """VALIDATION mode strips : retake dernière / valider-continue / annuler."""
    if event.key == TOUCHE_GAUCHE:
        _journaliser_action("retake")
        if session.photos_validees:
            session.photos_validees.pop()
        session.img_preview_cache = None
        session.etat = Etat.DECOMPTE
        session.dernier_clic_time = maintenant

    elif event.key == TOUCHE_MILIEU:
        session.img_preview_cache = None
        if len(session.photos_validees) < 3:
            _journaliser_action("validate_photo", photo_index=len(session.photos_validees))
            session.etat = Etat.DECOMPTE
        else:
            _journaliser_action("finish_strip")
            session.path_montage = MontageGeneratorStrip.preview(session.photos_validees)
            session.etat = Etat.FIN
        session.dernier_clic_time = maintenant

    elif event.key == TOUCHE_DROITE:
        _journaliser_action("abandon")
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
        _journaliser_action("restart_session")
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
        _journaliser_action("print")
        session.abandon_confirm_until = 0.0
        if not _verifier_quota_ou_debloquer(session):
            # Quota atteint et déblocage refusé : la session reste affichée
            session.dernier_clic_time = maintenant
            pygame.event.clear()
            return
        issue = traiter_impression_session(session)
        pygame.event.clear()
        terminer_session_et_revenir_accueil(issue)
        session.dernier_clic_time = maintenant
        return

    if event.key == TOUCHE_DROITE:
        # Abandon avec confirmation double-press
        if session.abandon_confirm_until and time.time() < session.abandon_confirm_until:
            # 2e appui dans la fenêtre → abandon confirmé
            _journaliser_action("abandon_confirmed")
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
            _journaliser_action("abandon_requested")
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
                        ACTIVER_DIAPORAMA_VEILLE
                        and session.etat is Etat.ACCUEIL
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
