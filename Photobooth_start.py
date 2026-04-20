from __future__ import annotations

# Imports explicites depuis config (plus de `import *` pour dépendances visibles).
# Liste triée alphabétiquement, mise à jour en ajoutant de nouvelles constantes.
from config import (
    ALPHA_TEXTE_REPOS, BANDEAU_10X15, BANDEAU_ACCUEIL, BANDEAU_ALPHA,
    BANDEAU_COULEUR, BANDEAU_HAUTEUR, BANDEAU_STRIP, COULEUR_DECOMPTE,
    COULEUR_FLASH, COULEUR_SOURIEZ, COULEUR_TEXTE_OFF, COULEUR_TEXTE_ON, COULEUR_TEXTE_REPOS,
    DELAI_SECURITE,
    DUREE_CONFIRM_ABANDON, DUREE_FLASH_BLANC, DUREE_IDLE_SLIDESHOW, DUREE_PAR_IMAGE_SLIDESHOW,
    FILE_BG_ACCUEIL, FORMAT_TIMESTAMP, HEIGHT,
    INTERVALLE_CHECK_DISQUE_S, LARGEUR_ICONE_10X15, LARGEUR_ICONE_STRIP, MARGE_ACCUEIL,
    MODE_10x15, MODE_STRIP, NB_MAX_IMAGES_SLIDESHOW,
    NOM_IMPRIMANTE_10X15, NOM_IMPRIMANTE_STRIP, OFFSET_DROITE_10X15, OFFSET_DROITE_STRIP,
    PATH_DATA, PATH_IMG_10X15, PATH_IMG_STRIP, PATH_PRINT,
    PATH_PRINT_10X15, PATH_PRINT_STRIP, PATH_RAW, PATH_SKIPPED,
    PATH_SKIPPED_DELETED, PATH_SKIPPED_RETAKE, PATH_SOUNDS, PATH_TEMP,
    POLICE_FICHIER, PREFIXE_DELETED, PREFIXE_PRINT_10X15, PREFIXE_PRINT_STRIP,
    PREFIXE_RAW, PREFIXE_RETAKE, PULSE_LENT_MAX, PULSE_LENT_MIN, PULSE_LENT_VITESSE, PULSE_MAX,
    PULSE_MIN, PULSE_VITESSE, SEUIL_DISQUE_CRITIQUE_MB, STRIP_BURST_DELAI_S,
    STRIP_MODE_BURST, TAILLE_DECOMPTE, TAILLE_TEXTE_BANDEAU,
    TAILLE_TEXTE_BOUTON, TAILLE_TITRE_ACCUEIL, TEMPS_DECOMPTE, TEXTE_PHOTO_COUNT,
    TOUCHE_DROITE, TOUCHE_GAUCHE, TOUCHE_MILIEU,
    TXT_BURST_COUNTDOWN, TXT_CONFIRM_ABANDON_1, TXT_CONFIRM_ABANDON_2, TXT_ERREUR_CAPTURE,
    TXT_ERREUR_IMPRIMANTE, TXT_PREPARATION_IMP, TXT_SLIDESHOW_INVITATION, WIDTH, ZOOM_FACTOR,
)
import config  # accès qualifié `config.X` dans les render functions
import pygame
import os
import sys
import time
import json
import shutil
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from PIL import Image, ImageOps
from datetime import datetime


# ========================================================================================================
# --- MACHINE D'ÉTAT (Sprint 4.5) ---
# Les états de la boucle principale étaient des strings ("ACCUEIL", "DECOMPTE", ...),
# vulnérables aux typos et sans support IDE. On passe à un Enum pour gagner la sécurité
# de typage sans toucher à la structure de la boucle elle-même.
# ========================================================================================================

class Etat(Enum):
    ACCUEIL = "ACCUEIL"
    DECOMPTE = "DECOMPTE"
    VALIDATION = "VALIDATION"
    FIN = "FIN"


# ========================================================================================================
# --- ÉTAT DE SESSION (Sprint item 10) ---
# Toutes les variables mutables de session sont encapsulées dans un dataclass.
# Évite la dizaine de `global x` dispersés et rend le state machine explicitable.
# Les subsystèmes indépendants (slideshow, monitoring disque) gardent leurs propres
# globals pour rester modulaires.
# ========================================================================================================

@dataclass
class SessionState:
    """État mutable d'une session photobooth + état transverse (idle, confirm abandon)."""

    etat: Etat = Etat.ACCUEIL
    mode_actuel: str | None = None
    photos_validees: list = field(default_factory=list)
    id_session_timestamp: str = ""
    session_start_ts: float = 0.0
    path_montage: str = ""
    img_preview_cache: object = None   # pygame.Surface | None
    dernier_clic_time: float = 0.0
    abandon_confirm_until: float = 0.0  # timestamp limite de la fenêtre de confirmation
    last_activity_ts: float = 0.0       # pour déclenchement slideshow idle

    def reset_pour_accueil(self):
        """Reset complet après fin de session (printed/abandoned/capture_failed).
        Préserve les compteurs temporels (last_activity_ts, etc.)."""
        self.etat = Etat.ACCUEIL
        self.mode_actuel = None
        self.photos_validees = []
        self.id_session_timestamp = ""
        self.img_preview_cache = None
        self.path_montage = ""




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

for d in dossiers_requis:
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
        print(f"📁 Dossier créé : {d}")

# Logging : extrait dans logger.py (Sprint 4.6). On importe les 4 helpers.
from core.logger import log_info, log_warning, log_critical  # noqa: E402


def _purger_temp_et_verifier_disque() -> None:
    """Nettoie PATH_TEMP (fichiers résiduels d'une session crashée) au boot,
    et log l'espace disque disponible. Avertit si < 1 Go.

    Appelé une seule fois au démarrage. Pour le monitoring continu pendant
    l'événement, voir `verifier_disque_periodiquement()`."""
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


_purger_temp_et_verifier_disque()


log_info("====================================================")
log_info("DÉMARRAGE DU PHOTOBOOTH (Dossiers OK)")
log_info("====================================================")


# ========================================================================================================
# --- GESTION CANON (Sprint 4.1 + 4.6 : CameraManager extrait dans camera.py) ---
# La classe CameraManager vit désormais dans camera.py. Import + wrappers de compat.
# ========================================================================================================

from core.camera import CameraManager  # noqa: E402


# Singleton global
camera_mgr = CameraManager()
camera_mgr.init()
if camera_mgr.is_connected:
    camera_mgr.set_liveview(1)


# Wrapper de compat — seul `get_canon_frame` est encore appelé (dans render_decompte).
def get_canon_frame() -> Optional[pygame.Surface]:
    """Retourne la frame preview caméra courante sous forme de pygame.Surface, ou None."""
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

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
pygame.font.init()

try:
    if os.path.exists(POLICE_FICHIER):
        font_titre        = pygame.font.Font(POLICE_FICHIER, TAILLE_TITRE_ACCUEIL)
        font_boutons    = pygame.font.Font(POLICE_FICHIER, TAILLE_TEXTE_BOUTON)  # <--- Nouveau
        font_bandeau    = pygame.font.Font(POLICE_FICHIER, TAILLE_TEXTE_BANDEAU) # <--- Nouveau
        font_decompte   = pygame.font.Font(POLICE_FICHIER, TAILLE_DECOMPTE)
    else:
        raise FileNotFoundError
except Exception:
    # Fallback Arial
    font_titre       = pygame.font.SysFont("Arial", TAILLE_TITRE_ACCUEIL, bold=True)
    font_boutons    = pygame.font.SysFont("Arial", TAILLE_TEXTE_BOUTON)
    font_bandeau    = pygame.font.SysFont("Arial", TAILLE_TEXTE_BANDEAU, bold=True)
    font_decompte   = pygame.font.SysFont("Arial", TAILLE_DECOMPTE, bold=True)


# ========================================================================================================
# --- UI : extrait dans ui.py (item 7) ---
# Le contexte UI (screen, clock, fontes) est injecté dans UIContext après l'init pygame.
# Les helpers (jouer_son, afficher_message_plein_ecran, executer_avec_spinner, ecran_erreur,
# splash_connexion_camera, ecran_attente_impression) sont importés depuis ui.py.
# ========================================================================================================

from ui import (  # noqa: E402
    UIContext, AccueilAssets, setup_sounds, jouer_son,
    draw_text_shadow_soft, inserer_background, executer_avec_spinner,
    ecran_erreur, ecran_attente_impression,
    splash_connexion_camera,
)

UIContext.setup(screen, clock, font_titre, font_boutons, font_bandeau, font_decompte)
setup_sounds()


_dernier_check_disque_ts = 0.0
_disque_critique = False
_disque_libre_mb = None


def verifier_disque_periodiquement() -> None:
    """Check périodique (INTERVALLE_CHECK_DISQUE_S) de l'espace disque libre.

    Met à jour les flags module-level `_disque_critique` et `_disque_libre_mb`
    lus par le rendu ACCUEIL pour afficher un bandeau rouge si on descend sous
    SEUIL_DISQUE_CRITIQUE_MB. Non-bloquant, silencieux sauf sur la transition
    OK→critique où on log un warning."""
    global _dernier_check_disque_ts, _disque_critique, _disque_libre_mb
    maintenant = time.time()
    if maintenant - _dernier_check_disque_ts < INTERVALLE_CHECK_DISQUE_S:
        return
    _dernier_check_disque_ts = maintenant
    try:
        _disque_libre_mb = shutil.disk_usage(PATH_DATA).free / (1024 ** 2)
        etait_critique = _disque_critique
        _disque_critique = _disque_libre_mb < SEUIL_DISQUE_CRITIQUE_MB
        # On n'alerte que sur la transition pour éviter le spam de log
        if _disque_critique and not etait_critique:
            log_warning(
                f"Espace disque critique : {_disque_libre_mb:.0f} Mo libres "
                f"(seuil : {SEUIL_DISQUE_CRITIQUE_MB} Mo)"
            )
    except Exception as e:
        log_warning(f"Check disque périodique échoué : {e}")


def terminer_session_et_revenir_accueil(issue: str) -> None:
    """Centralise la fin de session : écrit la metadata + reset du SessionState.

    Args:
        issue: "printed" | "abandoned" | "capture_failed" (consommé par stats.py).

    Le caller reste responsable de `session.dernier_clic_time = maintenant`."""
    ecrire_metadata_session(issue, len(session.photos_validees), time.time() - session.session_start_ts)
    session.reset_pour_accueil()


def ecrire_metadata_session(issue: str, nb_photos: int, duree_s: float) -> None:
    """Ajoute une ligne JSON dans data/sessions.jsonl.

    Format append-only : une ligne par session terminée. Facile à scanner
    post-événement via `stats.py`. Non-bloquant — toute erreur est loggée
    en warning."""
    try:
        entry = {
            "session_id": session.id_session_timestamp or None,
            "mode": session.mode_actuel,
            "issue": issue,          # "printed" | "retake" | "abandoned" | "capture_failed"
            "nb_photos": nb_photos,
            "duree_s": round(duree_s, 1),
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        chemin = os.path.join(PATH_DATA, "sessions.jsonl")
        with open(chemin, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log_warning(f"Écriture metadata session échouée : {e}")


# --- CACHE DES SURFACES STATIQUES (Sprint 3.4) ---
# Le bandeau noir semi-transparent est identique dans 3 états (ACCUEIL, VALIDATION, FIN).
# Le construire une seule fois évite 30 allocations pygame.Surface / sec.
BANDEAU_CACHE = pygame.Surface((WIDTH, BANDEAU_HAUTEUR))
BANDEAU_CACHE.set_alpha(BANDEAU_ALPHA)
BANDEAU_CACHE.fill(BANDEAU_COULEUR)


def lister_images_slideshow() -> list[str]:
    """Scan les dossiers d'impression (PATH_PRINT_10X15 + PATH_PRINT_STRIP) pour
    alimenter le slideshow d'attente. Retourne les NB_MAX_IMAGES_SLIDESHOW fichiers
    les plus récents, tri mtime décroissant."""
    fichiers = []
    for dossier in (PATH_PRINT_10X15, PATH_PRINT_STRIP):
        try:
            for nom in os.listdir(dossier):
                chemin = os.path.join(dossier, nom)
                if os.path.isfile(chemin) and nom.lower().endswith((".jpg", ".jpeg", ".png")):
                    try:
                        fichiers.append((os.path.getmtime(chemin), chemin))
                    except OSError:
                        continue
        except FileNotFoundError:
            continue
    fichiers.sort(key=lambda x: x[0], reverse=True)  # plus récents d'abord
    return [f[1] for f in fichiers[:NB_MAX_IMAGES_SLIDESHOW]]


# --- ÉTAT DE SESSION (Sprint item 10) ---
# Toutes les variables mutables encapsulées dans un dataclass.
session = SessionState(last_activity_ts=time.time())

# --- Contrôle de la boucle principale ---
running = True

# --- Slideshow d'attente (Sprint 6.2) ---
# Subsystème indépendant : garde ses propres globals plutôt que d'alourdir SessionState.
slideshow_images = []                 # liste de paths scannés à la demande
slideshow_last_refresh = 0.0          # dernier scan disque (évite de scanner chaque frame)
slideshow_cached_surface = None       # surface pygame de l'image courante
slideshow_cached_for_idx = -1         # l'index pour lequel la surface est valide


# --- CHARGEMENT DES SURFACES (cache boot-time via AccueilAssets) ---
accueil_assets = AccueilAssets.charger(
    bg_path=FILE_BG_ACCUEIL,
    img_10x15_path=PATH_IMG_10X15,
    img_strip_path=PATH_IMG_STRIP,
    largeur_10x15=LARGEUR_ICONE_10X15,
    largeur_strip=LARGEUR_ICONE_STRIP,
    zoom_factor=ZOOM_FACTOR,
    taille_ecran=(WIDTH, HEIGHT),
)
# Alias pour les render functions qui accèdent aux globals
fond_accueil = accueil_assets.fond
icon_10x15_norm = accueil_assets.icon_10x15_norm
icon_10x15_select = accueil_assets.icon_10x15_select
icon_strip_norm = accueil_assets.icon_strip_norm
icon_strip_select = accueil_assets.icon_strip_select
print("✅ Interface chargée (AccueilAssets).")

# --- Splash de connexion caméra (Sprint 2.1) ---
# Si `camera` a été obtenue à l'init top du fichier, le splash se ferme immédiatement.
# Sinon on montre un écran visible avec retry jusqu'à TIMEOUT_SPLASH_CAMERA.
splash_connexion_camera(camera_mgr)

# Flag de fenêtre de confirmation d'abandon en état FIN (Sprint 2.8)
session.abandon_confirm_until = 0.0


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
        slideshow_images = lister_images_slideshow()
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
    (_disque_critique), on superpose un bandeau rouge d'alerte en haut."""
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

    # Indicateur disque critique (Sprint 5.6)
    if _disque_critique and _disque_libre_mb is not None:
        alerte_h = 40
        alerte = pygame.Surface((WIDTH, alerte_h), pygame.SRCALPHA)
        alerte.fill((180, 20, 20, 220))
        screen.blit(alerte, (0, 0))
        txt_alerte = font_bandeau.render(
            f"⚠ ESPACE DISQUE CRITIQUE — {_disque_libre_mb:.0f} Mo libres",
            True, (255, 255, 255),
        )
        screen.blit(
            txt_alerte,
            (WIDTH // 2 - txt_alerte.get_width() // 2, (alerte_h - txt_alerte.get_height()) // 2),
        )


def render_accueil(session: SessionState) -> None:
    """ACCUEIL : slideshow d'attente si idle > seuil ET mode_actuel is None,
    sinon rendu normal (icônes + bandeau + alerte disque).

    Dispatcher entre `_render_accueil_slideshow` et `_render_accueil_normal`.
    Déclenche aussi le check disque périodique (rate-limité)."""
    verifier_disque_periodiquement()

    idle_seconds = time.time() - session.last_activity_ts
    if idle_seconds > DUREE_IDLE_SLIDESHOW and session.mode_actuel is None:
        _render_accueil_slideshow(session, idle_seconds)
    else:
        _render_accueil_normal(session)


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

    # Init id session si première photo
    if len(session.photos_validees) == 0:
        session.id_session_timestamp = datetime.now().strftime(FORMAT_TIMESTAMP)
        session.session_start_ts = time.time()
        log_info(f"🚀 NOUVELLE SESSION : {session.id_session_timestamp}")

    # Boucle du décompte visuel
    for i in range(TEMPS_DECOMPTE, 0, -1):
        jouer_son("beep")
        t_start = time.time()
        while time.time() - t_start < 1:
            surf = get_canon_frame()
            if surf:
                screen.blit(pygame.transform.scale(surf, (WIDTH, HEIGHT)), (0, 0))

                if alpha_masque > 0:
                    largeur_visible = HEIGHT / p_ratio
                    bande_w = int((WIDTH - largeur_visible) // 2)
                    if bande_w > 0:
                        masque_surf = pygame.Surface((bande_w, HEIGHT))
                        masque_surf.set_alpha(alpha_masque)
                        masque_surf.fill((0, 0, 0))
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
    """FIN : aperçu du montage final + bandeau 3 boutons + overlay confirmation abandon.

    En mode strip, le montage est lu depuis `session.path_montage` (produit par
    `MontageGeneratorStrip.preview()` à la transition VALIDATION→FIN). En mode
    10x15, l'aperçu est chargé depuis PATH_TEMP/montage_prev.jpg."""
    inserer_background(screen, fond_accueil)

    # Récupération de l'image
    p_prev = session.path_montage if session.path_montage else os.path.join(
        getattr(config, 'PATH_TEMP', 'temp'), "montage_prev.jpg"
    )

    if session.img_preview_cache is None:
        if os.path.exists(p_prev):
            try:
                raw_m = pygame.image.load(p_prev).convert_alpha()
                h_max_fin = 600 if session.mode_actuel == "strips" else 520
                ratio_m = raw_m.get_width() / raw_m.get_height()
                session.img_preview_cache = pygame.transform.smoothscale(raw_m, (int(h_max_fin * ratio_m), h_max_fin))
            except Exception as e:
                log_warning(f"Erreur chargement aperçu FIN : {e}")

    # Application des décalages spécifiques
    if session.img_preview_cache:
        if session.mode_actuel == "strips":
            dec_y = getattr(config, 'DECALAGE_Y_MONTAGE_FINAL_STRIP', 0)
        else:
            dec_y = getattr(config, 'DECALAGE_Y_PREVISU_10X15', 0)

        x_m = (WIDTH - session.img_preview_cache.get_width()) // 2
        y_m = (HEIGHT // 2 - session.img_preview_cache.get_height() // 2) + dec_y

        pygame.draw.rect(screen, (255, 255, 255),
                         (x_m - 10, y_m - 10, session.img_preview_cache.get_width() + 20, session.img_preview_cache.get_height() + 20))
        screen.blit(session.img_preview_cache, (x_m, y_m))

    # Bandeau de boutons
    y_b = HEIGHT - BANDEAU_HAUTEUR
    screen.blit(BANDEAU_CACHE, (0, y_b))
    y_t = y_b + (BANDEAU_HAUTEUR // 2) - (font_bandeau.get_height() // 2)
    txt_g = config.TXT_BOUTON_REPRENDRE if session.mode_actuel == "10x15" else config.TXT_BOUTON_ACCUEIL
    screen.blit(font_bandeau.render(txt_g, True, config.COULEUR_TEXTE_G), (80, y_t))
    t_m = font_bandeau.render(config.TXT_BOUTON_IMPRIMER, True, config.COULEUR_TEXTE_M)
    screen.blit(t_m, (WIDTH // 2 - t_m.get_width() // 2, y_t))
    t_d = font_bandeau.render(config.TXT_BOUTON_SUPPRIMER, True, config.COULEUR_TEXTE_D)
    screen.blit(t_d, (WIDTH - 80 - t_d.get_width(), y_t))

    # Overlay de confirmation d'abandon (Sprint 2.8)
    if session.abandon_confirm_until:
        if time.time() < session.abandon_confirm_until:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 170))
            screen.blit(overlay, (0, 0))
            t1 = font_titre.render(TXT_CONFIRM_ABANDON_1, True, (255, 120, 120))
            screen.blit(t1, (WIDTH // 2 - t1.get_width() // 2, HEIGHT // 2 - 120))
            t2 = font_bandeau.render(TXT_CONFIRM_ABANDON_2, True, (255, 255, 255))
            screen.blit(t2, (WIDTH // 2 - t2.get_width() // 2, HEIGHT // 2 + 20))
        else:
            session.abandon_confirm_until = 0.0


# ========================================================================================================
# --- EVENT HANDLERS (Sprint item 9) ---
# Un handler par état qui peut recevoir des touches (ACCUEIL/VALIDATION/FIN).
# Chaque handler mute `session` en place. Les `return` anticipés remplacent les
# `continue` du code inline (le for event loop extérieur passe à l'event suivant).
# DECOMPTE n'a pas de handler car l'état est non-interactif (géré par render_decompte).
# ========================================================================================================

def handle_accueil_event(event: pygame.event.Event, session: SessionState,
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


def _handle_validation_10x15(event: pygame.event.Event, session: SessionState,
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
        try:
            p = executer_avec_spinner(
                lambda: MontageGenerator10x15.final(session.photos_validees, session.id_session_timestamp),
                TXT_PREPARATION_IMP,
            )
            dest = os.path.join(PATH_PRINT_10X15, f"{PREFIXE_PRINT_10X15}_{session.id_session_timestamp}.jpg")
            shutil.copy(p, dest)
            if printer_mgr.send(dest, "10x15"):
                jouer_son("success")
                ecran_attente_impression()
            else:
                ecran_erreur(TXT_ERREUR_IMPRIMANTE)
        except Exception as e:
            log_critical(f"Erreur 10x15 Print/Impression: {e}")
            ecran_erreur(TXT_ERREUR_IMPRIMANTE)

        pygame.event.clear()
        terminer_session_et_revenir_accueil("printed")
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


def _handle_validation_strips(event: pygame.event.Event, session: SessionState,
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


def handle_validation_event(event: pygame.event.Event, session: SessionState,
                            maintenant: float, ecoule: float) -> None:
    """VALIDATION : dispatch selon mode (10x15 vs strips). Debounce 0.5 s."""
    if ecoule < 0.5:
        return
    if session.mode_actuel == "10x15":
        _handle_validation_10x15(event, session, maintenant)
    elif session.mode_actuel == "strips":
        _handle_validation_strips(event, session, maintenant)


def handle_fin_event(event: pygame.event.Event, session: SessionState,
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
        try:
            if session.mode_actuel == "strips":
                p = executer_avec_spinner(
                    lambda: MontageGeneratorStrip.final(session.photos_validees, session.id_session_timestamp),
                    TXT_PREPARATION_IMP,
                )
                destination = os.path.join(
                    PATH_PRINT_STRIP, f"{PREFIXE_PRINT_STRIP}_{session.id_session_timestamp}.jpg",
                )
            else:
                p = executer_avec_spinner(
                    lambda: MontageGenerator10x15.final(session.photos_validees, session.id_session_timestamp),
                    TXT_PREPARATION_IMP,
                )
                destination = os.path.join(
                    PATH_PRINT_10X15, f"{PREFIXE_PRINT_10X15}_{session.id_session_timestamp}.jpg",
                )

            shutil.copy(p, destination)

            if printer_mgr.send(destination, session.mode_actuel):
                jouer_son("success")
                ecran_attente_impression()
            else:
                ecran_erreur(TXT_ERREUR_IMPRIMANTE)
        except Exception as e:
            log_critical(f"Erreur Impression finale : {e}")
            ecran_erreur(TXT_ERREUR_IMPRIMANTE)

        pygame.event.clear()
        terminer_session_et_revenir_accueil("printed")
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

while running:
    screen.fill((10, 10, 10))    
    
    # ----------------------------------------------------------------------------------------------------
    # --- 1 ------ GESTION DES ÉVÉNEMENTS (TOUCHES) --- ##################################################
    # ----------------------------------------------------------------------------------------------------
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
            
        # ON VÉRIFIE QUE C'EST UNE TOUCHE CLAVIER
        if event.type == pygame.KEYDOWN:
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


    # ----------------------------------------------------------------------------------------------------
    # ----------------------------------------------------------------------------------------------------
    # ----------------------------------------------------------------------------------------------------
    # ----------------------------------------------------------------------------------------------------
    # --- 2 ------ DESSIN A L'ECRAN --- ##################################################################
    # ----------------------------------------------------------------------------------------------------

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
    pygame.display.flip()
    clock.tick(30)

pygame.quit()

