from config import * # Cela importe TOUTES les variables de ton fichier config
import config
import pygame
import cv2
import os
import sys
import time
import json
import subprocess
import threading
import numpy as np
import gphoto2 as gp
import shutil
import math
from enum import Enum
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
from logger import log_error, log_info, log_warning, log_critical, log_file  # noqa: E402


def _purger_temp_et_verifier_disque():
    """Sprint 3.6 : nettoie PATH_TEMP (fichiers résiduels d'une session crashée)
    et log l'espace disque disponible. Avertit si < 1 Go."""
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

from camera import CameraManager  # noqa: E402


# Singleton global
camera_mgr = CameraManager()
camera_mgr.init()
if camera_mgr.is_connected:
    camera_mgr.set_liveview(1)


# --- Wrappers de compat pour le code existant ---
def init_camera():
    """Wrapper historique : retourne l'objet gphoto2 interne ou None."""
    camera_mgr.init()
    return camera_mgr.raw_camera


def set_liveview(cam, state):  # noqa: ARG001 — cam ignoré (lu par le manager)
    camera_mgr.set_liveview(state)


def get_canon_frame():
    return camera_mgr.get_preview_frame()


# Variable globale historique — certains appelants lisent encore `camera` pour tester la
# présence (splash_connexion_camera). On fournit un accès mais le source de vérité est le
# manager. L'ancienne réassignation `camera = init_camera()` n'a plus d'effet.
class _CameraProxy:
    """Compat : `camera` globale était un objet gphoto2 ; on l'expose via le manager."""
    def __bool__(self):
        return camera_mgr.is_connected

    def __getattr__(self, name):
        cam = camera_mgr.raw_camera
        if cam is None:
            raise AttributeError(f"caméra non connectée (attribut demandé : {name})")
        return getattr(cam, name)


camera = _CameraProxy()

# ========================================================================================================
# --- 2. FONCTIONS TECHNIQUES --- ########################################################################
# ========================================================================================================

def capturer_hq(id_session, index_photo):
    """Procédure de capture : UI (flash + SOURIEZ) + appel CameraManager.capture_hq().
    Retourne le chemin complet si OK, None sinon."""
    nom_final = f"{PREFIXE_RAW}_{id_session}_{index_photo}.jpg"
    chemin_complet = os.path.join(PATH_RAW, nom_final)

    # 1. FLASH BLANC pur (Sprint 2.2) — effet "shutter" bref
    screen.fill(COULEUR_FLASH)
    pygame.display.flip()
    jouer_son("shutter")  # Sprint 2.3
    time.sleep(DUREE_FLASH_BLANC)

    # 2. Flash blanc avec "SOURIEZ !" pendant la capture subprocess (bloquante côté caméra)
    screen.fill(COULEUR_FLASH)
    try:
        txt_flash = font_titre.render("SOURIEZ !", True, COULEUR_SOURIEZ)
        text_x = (WIDTH // 2) - (txt_flash.get_width() // 2)
        text_y = (HEIGHT // 2) - (txt_flash.get_height() // 2)
        screen.blit(txt_flash, (text_x, text_y))
    except Exception as e:
        log_error(f"Affichage SOURIEZ échoué : {e}")
    pygame.display.flip()

    # 3. Capture réelle via le CameraManager (gère retry, reset session, relance LiveView)
    success = camera_mgr.capture_hq(chemin_complet)

    if success:
        log_info(f"✅ Photo sauvegardée : {nom_final}")
        return chemin_complet
    log_critical(f"ÉCHEC : Le fichier {nom_final} est introuvable.")
    return None


def obtenir_couleur_pulse(c1, c2, vitesse):
    """ Calcule une couleur oscillant entre c1 et c2 """
    # Calcul d'un facteur entre 0.0 et 1.0 avec le temps
    f = (math.sin(time.time() * vitesse) + 1) / 2
    
    # Mélange des composantes R, G, B
    r = int(c1[0] + (c2[0] - c1[0]) * f)
    g = int(c1[1] + (c2[1] - c1[1]) * f)
    b = int(c1[2] + (c2[2] - c1[2]) * f)
    return (r, g, b)

def draw_text_shadow_soft(surface, text, font, color, x, y, shadow_alpha=100, offset=2):
    """Dessine un texte avec une ombre noire transparente"""
    # 1. Créer une surface pour l'ombre (Noire)
    shadow_surf = font.render(text, True, (0, 0, 0))
    
    # 2. Créer une surface de la même taille capable de gérer la transparence
    temp_surf = pygame.Surface(shadow_surf.get_size(), pygame.SRCALPHA)
    temp_surf.blit(shadow_surf, (0, 0))
    
    # 3. Appliquer l'opacité (0 = invisible, 255 = noir total)
    # 120 est un bon compromis pour une ombre élégante
    temp_surf.set_alpha(shadow_alpha)
    
    # 4. Dessiner l'ombre puis le texte
    surface.blit(temp_surf, (x + offset, y + offset))
    surface.blit(font.render(text, True, color), (x, y))

# ========================================================================================================
# --- 3. TRAITEMENT IMAGE (Sprint 4.6 : extrait dans montage.py) ---
# Les classes MontageBase, MontageGenerator10x15, MontageGeneratorStrip et la fonction
# helper `charger_et_corriger` vivent désormais dans montage.py. Module pur (pas de
# pygame, pas de globals UI), testable isolément. Import + wrappers de compat ci-dessous.
# ========================================================================================================

from montage import (
    MontageBase,
    MontageGenerator10x15,
    MontageGeneratorStrip,
    charger_et_corriger,
)


# --- Wrappers de compat : les call sites historiques continuent de fonctionner ---
def generer_preview_10x15(photos):
    return MontageGenerator10x15.preview(photos)

def generer_montage_final_10x15(photos, id_session):
    return MontageGenerator10x15.final(photos, id_session)

def generer_preview_ecran_strip(photos):
    return MontageGeneratorStrip.preview(photos)

def generer_montage_impression_strip(photos, id_session):
    return MontageGeneratorStrip.final(photos, id_session)


def get_pygame_surf_cropped(path, size_target, ratio_voulu):
    if not os.path.exists(path):
        return None
    try:
        # On ouvre l'image brute, sans laisser PIL décider du sens via l'EXIF
        with Image.open(path) as src:
            img = src.convert("RGB")

        # Le montage_prev est déjà au bon ratio, on le redimensionne juste pour l'écran
        img_fit = img.resize(size_target, Image.Resampling.LANCZOS)

        mode = img_fit.mode
        size = img_fit.size
        data = img_fit.tobytes()
        return pygame.image.fromstring(data, size, mode)
    except Exception as e:
        log_error(f"Erreur affichage : {e}")
        return None


def get_pygame_surf(path_or_img, size):
    if isinstance(path_or_img, str):
        if not os.path.exists(path_or_img): return None
        img = charger_et_corriger(path_or_img)
    else:
        img = path_or_img
    img = img.resize(size, Image.Resampling.LANCZOS)
    return pygame.image.fromstring(img.tobytes(), img.size, img.mode)

def inserer_background(screen, fond_image):
    """Dessine le fond d'écran (Image ou Bleu de secours)"""
    if fond_image:
        screen.blit(fond_image, (0, 0))
    else:
        # Le fameux bleu de secours de l'accueil
        screen.fill((155, 211, 242))
        
# ========================================================================================================
# --- 5. FONCTIONS IMPRESSION--- ##########################################################
# ========================================================================================================


# --- CLASSE POUR LA ROUE DE CHARGEMENT PENDANT IMPRESSION
class LoaderAnimation:
    def __init__(self):
        self.reset() # On utilise reset pour l'initialisation aussi

    def reset(self):
        """ Remet l'animation à son état initial 'calme' """
        self.angle_tete = 0
        self.longueur_actuelle = 30 # Longueur minimale de départ
        self.dernier_temps = time.time()

    def interpoler_couleur(self, c1, c2, facteur):
        return tuple(int(c1[j] + (c2[j] - c1[j]) * (1 - facteur)) for j in range(3))

    def update_and_draw(self, screen):
        maintenant = time.time()
        dt = maintenant - self.dernier_temps
        self.dernier_temps = maintenant

        # Utilisation directe des variables de ton config.py (via l'import *)
        cycle = (math.sin(maintenant * ANIM_FREQ) + 1) / 2
        boost = math.pow(cycle, 4)
        
        vitesse_actuelle = ANIM_V_BASE + (boost * ANIM_V_MAX_ADD)
        self.angle_tete += vitesse_actuelle * dt * 50 

        longueur_cible = 30 + (boost * 210)
        self.longueur_actuelle += (longueur_cible - self.longueur_actuelle) * ANIM_V_ELASTIQUE * dt

        # Sprint 3.3 : une seule Surface réutilisée (buffer) au lieu d'en allouer 300/frame.
        # Elle vit sur l'instance : alloc une seule fois pour toute la durée de vie du loader.
        if not hasattr(self, '_point_buffer'):
            diametre = ANIM_RAYON_POINT * 2
            self._point_buffer = pygame.Surface((diametre, diametre), pygame.SRCALPHA)

        buf = self._point_buffer
        for i in reversed(range(ANIM_NB_POINTS)):
            progression = i / (ANIM_NB_POINTS - 1)
            fading = 1.0 - progression
            angle_point = math.radians(self.angle_tete - (progression * self.longueur_actuelle))

            x = WIDTH // 2 + math.cos(angle_point) * ANIM_TAILLE_ROUE
            y = HEIGHT // 2 + math.sin(angle_point) * ANIM_TAILLE_ROUE

            couleur = self.interpoler_couleur(ANIM_COULEUR_TETE, ANIM_COULEUR_QUEUE, fading)
            alpha = int(255 * (fading ** 0.6))

            buf.fill((0, 0, 0, 0))  # clear (la Surface SRCALPHA se vide proprement)
            pygame.draw.circle(buf, (*couleur, alpha), (ANIM_RAYON_POINT, ANIM_RAYON_POINT), ANIM_RAYON_POINT)
            screen.blit(buf, (x - ANIM_RAYON_POINT, y - ANIM_RAYON_POINT))

# --- INITIALISATION DE L'OBJET ---
# On le crée une seule fois ici
mon_loader = LoaderAnimation()


# --- PrinterManager (Sprint 4.3) : extrait dans printer.py (Sprint 4.6) ---
from printer import PrinterManager  # noqa: E402

# Singleton global utilisé par les wrappers et — pour du nouveau code — à appeler directement.
printer_mgr = PrinterManager(NOM_IMPRIMANTE_10X15, NOM_IMPRIMANTE_STRIP)


# --- Wrappers de compat ---
def imprimante_prete(nom):
    """Wrapper historique — prend un nom de file. Préserver pour code externe éventuel."""
    for mode, n in printer_mgr._noms.items():
        if n == nom:
            return printer_mgr.is_ready(mode)
    return False


def imprimer_fichier_auto(chemin, mode):
    return printer_mgr.send(chemin, mode)


def ecran_attente_impression():
    """ Affiche la roue magique selon la durée définie dans config.py """
    # On force Python à utiliser les objets créés dans le script principal
    global screen, mon_loader, clock, font_bandeau
    
    temps_debut = time.time()
    
    # Boucle de verrouillage pendant l'impression
    while time.time() - temps_debut < TEMPS_ATTENTE_IMP:
        
        # 1. On écoute quand même le système (pour pouvoir quitter avec Echap ou la croix)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        # 2. Rendu de l'animation
        screen.fill(COULEUR_FOND_LOADER) # Fond bleu nuit
        
        # On appelle l'objet loader
        mon_loader.update_and_draw(screen)
        
        # 3. Affichage du texte
        try:
            # On utilise les variables de config.py (WIDTH, HEIGHT)
            txt = font_bandeau.render("Impression en cours...", True, (255, 255, 255))
            tx = (WIDTH // 2) - (txt.get_width() // 2)
            ty = HEIGHT - 120
            screen.blit(txt, (tx, ty))
        except Exception as e:
            # Si la police n'est pas chargée, on ne bloque pas le programme
            pass

        # 4. Mise à jour de l'écran
        pygame.display.flip()
        
        # 5. On bride à 60 FPS (config.FPS) pour ne pas faire chauffer le processeur
        clock.tick(FPS)




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
except Exception as e:
    # Fallback Arial
    font_titre       = pygame.font.SysFont("Arial", TAILLE_TITRE_ACCUEIL, bold=True)
    font_boutons    = pygame.font.SysFont("Arial", TAILLE_TEXTE_BOUTON)
    font_bandeau    = pygame.font.SysFont("Arial", TAILLE_TEXTE_BANDEAU, bold=True)
    font_decompte   = pygame.font.SysFont("Arial", TAILLE_DECOMPTE, bold=True)


# ========================================================================================================
# --- SONS & HELPERS UI --- ##############################################################################
# ========================================================================================================

# --- Initialisation du mixer audio (fallback silencieux si pas de carte son) ---
try:
    pygame.mixer.init()
    _mixer_ok = True
except Exception as e:
    log_error(f"⚠️ pygame.mixer non disponible : {e}")
    _mixer_ok = False

SONS = {}
if _mixer_ok:
    for _nom, _path in [("beep", SON_BEEP), ("shutter", SON_SHUTTER), ("success", SON_SUCCESS)]:
        if os.path.exists(_path):
            try:
                SONS[_nom] = pygame.mixer.Sound(_path)
            except Exception as e:
                log_error(f"⚠️ Son {_nom} non chargé ({_path}) : {e}")
        else:
            log_error(f"ℹ️ Son {_nom} absent (optionnel) : {_path}")


def jouer_son(nom):
    """Joue un son si disponible, sinon ne fait rien (fallback silencieux)."""
    s = SONS.get(nom)
    if s is not None:
        try:
            s.play()
        except Exception as e:
            log_error(f"⚠️ Lecture son {nom} échouée : {e}")


def afficher_message_plein_ecran(message, couleur=(255, 215, 0), fond=COULEUR_FOND_LOADER):
    """Affiche un message centré plein écran et flip. Utilisé pour les transitions courtes."""
    screen.fill(fond)
    try:
        txt = font_bandeau.render(message, True, couleur)
        screen.blit(
            txt,
            (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - txt.get_height() // 2),
        )
    except Exception as e:
        log_error(f"Affichage message échoué : {e}")
    pygame.display.flip()


_dernier_check_disque_ts = 0.0
_disque_critique = False
_disque_libre_mb = None


def verifier_disque_periodiquement():
    """Sprint 5.6 : check périodique (INTERVALLE_CHECK_DISQUE_S) de l'espace disque libre.
    Met à jour les flags globaux pour que le rendu ACCUEIL puisse afficher un bandeau
    rouge si on descend sous SEUIL_DISQUE_CRITIQUE_MB. Non-bloquant, silencieux sauf
    transition OK→critique où on log un warning."""
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


def terminer_session_et_revenir_accueil(issue):
    """Sprint 4.4 : centralise la fin de session (5 sites historiques).
    Écrit la metadata + reset tous les globals de session + repasse à ACCUEIL.
    Le caller reste responsable de `dernier_clic_time = maintenant`."""
    global photos_validees, id_session_timestamp, mode_actuel
    global img_preview_cache, path_montage, etat

    ecrire_metadata_session(issue, len(photos_validees), time.time() - session_start_ts)

    photos_validees = []
    id_session_timestamp = ""
    mode_actuel = None
    img_preview_cache = None
    path_montage = ""
    etat = Etat.ACCUEIL


def ecrire_metadata_session(issue, nb_photos, duree_s):
    """Sprint 5.4 : ajoute une ligne JSON dans data/sessions.jsonl pour chaque session
    terminée. Format append-only : facile à scanner post-événement pour stats."""
    try:
        entry = {
            "session_id": id_session_timestamp or None,
            "mode": mode_actuel,
            "issue": issue,          # "printed" | "retake" | "abandoned" | "capture_failed"
            "nb_photos": nb_photos,
            "duree_s": round(duree_s, 1),
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        chemin = os.path.join(PATH_DATA, "sessions.jsonl")
        with open(chemin, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log_error(f"⚠️ Écriture metadata session échouée : {e}")


def executer_avec_spinner(fonction_longue, message):
    """Sprint 3.2 : exécute une fonction bloquante (génération montage PIL)
    dans un thread, tout en animant le loader + message pendant l'attente.
    Retourne la valeur de retour, ou re-lève l'exception capturée dans le thread.
    L'UI reste fluide au lieu de figer 1-2 s sur un écran statique."""
    resultat = {}

    def _wrapper():
        try:
            resultat["value"] = fonction_longue()
        except BaseException as exc:
            resultat["error"] = exc

    t = threading.Thread(target=_wrapper, daemon=True)
    t.start()

    local_loader = LoaderAnimation()
    while t.is_alive():
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        screen.fill(COULEUR_FOND_LOADER)
        local_loader.update_and_draw(screen)
        try:
            txt = font_bandeau.render(message, True, (255, 255, 255))
            screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT - 120))
        except Exception as e:
            log_error(f"Rendu message spinner : {e}")
        pygame.display.flip()
        clock.tick(30)

    t.join(timeout=1.0)
    if "error" in resultat:
        raise resultat["error"]
    return resultat.get("value")


def ecran_erreur(message, timeout=None):
    """Écran d'erreur explicite visible par l'utilisateur, avec timeout auto.
    Une touche clavier permet aussi de skipper."""
    if timeout is None:
        timeout = DUREE_ECRAN_ERREUR
    t_start = time.time()
    while time.time() - t_start < timeout:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                return  # l'utilisateur skippe

        screen.fill((40, 10, 10))
        try:
            titre = font_titre.render("ERREUR", True, (255, 100, 100))
            screen.blit(titre, (WIDTH // 2 - titre.get_width() // 2, HEIGHT // 2 - 220))
            msg = font_bandeau.render(message, True, (255, 255, 255))
            screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2))
            hint = font_bandeau.render(
                "Appuyez sur une touche ou patientez...", True, (170, 170, 170)
            )
            screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 100))
        except Exception as e:
            log_error(f"Rendu écran erreur échoué : {e}")
        pygame.display.flip()
        clock.tick(30)


def splash_connexion_camera(timeout=None):
    """Tente de connecter la caméra avec un écran visible + retry jusqu'à timeout.
    Retourne True si connecté, False sinon (on laisse tourner en mode dégradé).
    Sprint 4.1 : délègue au CameraManager (plus de global `camera` à gérer)."""
    if timeout is None:
        timeout = TIMEOUT_SPLASH_CAMERA
    t_start = time.time()
    frame_count = 0
    while time.time() - t_start < timeout:
        # On écoute QUIT pour ne pas figer l'app
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        # Si la caméra est absente, on tente une reconnexion (1× / seconde)
        if not camera_mgr.is_connected and frame_count % 30 == 0:
            if camera_mgr.init():
                camera_mgr.set_liveview(1)

        if camera_mgr.is_connected:
            afficher_message_plein_ecran(TXT_SPLASH_CAMERA_OK, couleur=(100, 255, 100))
            time.sleep(0.6)
            return True

        # Animation simple : 3 points qui défilent
        dots = "." * (1 + (frame_count // 15) % 3)
        afficher_message_plein_ecran(
            f"{TXT_SPLASH_CAMERA}{dots}", couleur=(255, 215, 0)
        )
        clock.tick(30)
        frame_count += 1

    # Timeout : on montre un avertissement et on continue en mode dégradé
    afficher_message_plein_ecran(TXT_SPLASH_CAMERA_FAIL, couleur=(255, 150, 150))
    time.sleep(1.5)
    return False


# --- CACHE DES SURFACES STATIQUES (Sprint 3.4) ---
# Le bandeau noir semi-transparent est identique dans 3 états (ACCUEIL, VALIDATION, FIN).
# Le construire une seule fois évite 30 allocations pygame.Surface / sec.
BANDEAU_CACHE = pygame.Surface((WIDTH, BANDEAU_HAUTEUR))
BANDEAU_CACHE.set_alpha(BANDEAU_ALPHA)
BANDEAU_CACHE.fill(BANDEAU_COULEUR)


def lister_images_slideshow():
    """Sprint 6.2 : scan les dossiers d'impression pour alimenter le slideshow.
    Retourne les NB_MAX_IMAGES_SLIDESHOW fichiers les plus récents, tous formats confondus."""
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


# --- VARIABLES DE SESSION ---
etat = Etat.ACCUEIL
photos_validees = []
id_session_timestamp = ""
session_start_ts = 0.0  # Sprint 5.4 : mesure durée pour metadata
mode_actuel = None
path_montage = ""
path_montage_hd = ""
running = True
selection = None  # Peut être "10X15" ou "STRIP"
dernier_clic_time = 0
img_preview_cache = None

# --- Slideshow d'attente (Sprint 6.2) ---
last_activity_ts = time.time()        # reset à chaque appui touche
slideshow_images = []                 # liste de paths scannés à la demande
slideshow_index = 0
slideshow_last_refresh = 0.0          # dernier scan disque (évite de scanner chaque frame)
slideshow_cached_surface = None       # surface pygame de l'image courante
slideshow_cached_for_idx = -1         # l'index pour lequel la surface est valide


# --- CHARGEMENT DES SURFACES ---
fond_accueil = None
icon_10x15 = None
icon_strip = None

try:
    # 1. Chargement du fond d'écran
    if os.path.exists(FILE_BG_ACCUEIL):
        fond_accueil = pygame.image.load(FILE_BG_ACCUEIL).convert()
        fond_accueil = pygame.transform.scale(fond_accueil, (WIDTH, HEIGHT))
    else:
        log_error(f"Fond d'accueil manquant : {FILE_BG_ACCUEIL}")

    # 2. Chargement 10x15 (Utilise LARGEUR_ICONE_10X15 du config)
    if os.path.exists(PATH_IMG_10X15):
        img_10x15_raw = pygame.image.load(PATH_IMG_10X15).convert_alpha()
        ratio_10x15 = img_10x15_raw.get_height() / img_10x15_raw.get_width()
        h_10x15 = int(LARGEUR_ICONE_10X15 * ratio_10x15)
        
        icon_10x15_norm = pygame.transform.smoothscale(img_10x15_raw, (LARGEUR_ICONE_10X15, h_10x15))
        icon_10x15_select = pygame.transform.smoothscale(img_10x15_raw, (int(LARGEUR_ICONE_10X15 * ZOOM_FACTOR), int(h_10x15 * ZOOM_FACTOR)))
    else:
        log_error(f"Image 10x15 manquante : {PATH_IMG_10X15}")

    # 3. Chargement Strip (Utilise LARGEUR_ICONE_STRIP du config)
    if os.path.exists(PATH_IMG_STRIP):
        img_strip_raw = pygame.image.load(PATH_IMG_STRIP).convert_alpha()
        ratio_strip = img_strip_raw.get_height() / img_strip_raw.get_width()
        h_strip = int(LARGEUR_ICONE_STRIP * ratio_strip)
        
        icon_strip_norm = pygame.transform.smoothscale(img_strip_raw, (LARGEUR_ICONE_STRIP, h_strip))
        icon_strip_select = pygame.transform.smoothscale(img_strip_raw, (int(LARGEUR_ICONE_STRIP * ZOOM_FACTOR), int(h_strip * ZOOM_FACTOR)))
    else:
        log_error(f"Image Strip manquante : {PATH_IMG_STRIP}")

    print("✅ Toutes les images de l'interface sont chargées.")

except Exception as e:
    msg = f"Erreur critique lors du chargement des surfaces : {e}"
    print(f"⚠️ {msg}")
    log_error(msg)

# --- Splash de connexion caméra (Sprint 2.1) ---
# Si `camera` a été obtenue à l'init top du fichier, le splash se ferme immédiatement.
# Sinon on montre un écran visible avec retry jusqu'à TIMEOUT_SPLASH_CAMERA.
splash_connexion_camera()

# Flag de fenêtre de confirmation d'abandon en état FIN (Sprint 2.8)
abandon_confirm_until = 0.0

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
            ecoule = maintenant - dernier_clic_time

            # Sprint 6.2 : si le slideshow était actif (idle > seuil en ACCUEIL), la 1re
            # touche ne déclenche aucune action — elle réveille juste l'interface.
            slideshow_etait_actif = (
                etat is Etat.ACCUEIL
                and mode_actuel is None
                and (maintenant - last_activity_ts) > DUREE_IDLE_SLIDESHOW
            )
            last_activity_ts = maintenant
            if slideshow_etait_actif:
                continue

            # --- 1. ÉTAT ACCUEIL ---
            if etat is Etat.ACCUEIL:
                if ecoule >= DELAI_SECURITE:
                    if event.key == TOUCHE_GAUCHE:
                        print("Mode 10x15 sélectionné")
                        mode_actuel = "10x15"
                    elif event.key == TOUCHE_DROITE:
                        print("Mode Bandelettes sélectionné")
                        mode_actuel = "strips"
                    elif event.key == TOUCHE_MILIEU:
                        if mode_actuel:
                            print(f"🚀 {mode_actuel} Validé !")
                            photos_validees = []
                            dernier_clic_time = maintenant
                            etat = Etat.DECOMPTE

            # --- 2. ÉTAT VALIDATION ---
            elif etat is Etat.VALIDATION:
                if ecoule >= 0.5:

                    # ==================================================================
                    # CAS DU MODE : 10X15 (Direct, une seule photo)
                    # ==================================================================
                    if mode_actuel == "10x15":
                        
                        # --- GAUCHE : REFAIRE (Archivage SKIPPED + Relance) ---
                        if event.key == TOUCHE_GAUCHE:
                            print("LOG: [10x15] -> Refaire : Archivage RETAKE et relance")
                            try:
                                # Sprint 3.2 : génération dans un thread avec spinner animé
                                p = executer_avec_spinner(
                                    lambda: generer_montage_final_10x15(photos_validees, id_session_timestamp),
                                    TXT_PREPARATION_IMP,
                                )
                                dest = os.path.join(PATH_SKIPPED_RETAKE, f"{PREFIXE_RETAKE}_{id_session_timestamp}.jpg")
                                shutil.move(p, dest)
                            except Exception as e: log_error(f"Erreur 10x15 Retake: {e}")

                            photos_validees = []
                            etat = Etat.DECOMPTE
                            dernier_clic_time = maintenant

                        # --- MILIEU : IMPRIMER DIRECTEMENT ---
                        elif event.key == TOUCHE_MILIEU:
                            print("LOG: [10x15] -> Impression directe et Accueil")
                            try:
                                # Sprint 3.2 : génération threadée avec spinner animé (remplace le fig\xe9)
                                p = executer_avec_spinner(
                                    lambda: generer_montage_final_10x15(photos_validees, id_session_timestamp),
                                    TXT_PREPARATION_IMP,
                                )
                                dest = os.path.join(PATH_PRINT_10X15, f"{PREFIXE_PRINT_10X15}_{id_session_timestamp}.jpg")
                                shutil.copy(p, dest)

                                # 2. On lance l'impression PHYSIQUE (seulement si le fichier est OK)
                                if imprimer_fichier_auto(dest, "10x15"):
                                    jouer_son("success")  # Sprint 2.3
                                    # 3. On affiche l'écran de chargement pour l'utilisateur
                                    ecran_attente_impression()
                                else:
                                    ecran_erreur(TXT_ERREUR_IMPRIMANTE)  # Sprint 2.5/2.6

                            except Exception as e:
                                log_error(f"Erreur 10x15 Print/Impression: {e}")
                                ecran_erreur(TXT_ERREUR_IMPRIMANTE)

                            # 4. Cooldown : on vide les événements en attente (Sprint 2.7)
                            pygame.event.clear()

                            # Sprint 4.4 : metadata + reset session + retour accueil
                            terminer_session_et_revenir_accueil("printed")
                            dernier_clic_time = maintenant

                        # --- DROITE : ABANDONNER ---
                        elif event.key == TOUCHE_DROITE:
                            print("LOG: [10x15] -> Abandon : Archivage DELETED et Accueil")
                            try:
                                # Sprint 3.2 : génération threadée avec spinner
                                p = executer_avec_spinner(
                                    lambda: generer_montage_final_10x15(photos_validees, id_session_timestamp),
                                    TXT_PREPARATION_IMP,
                                )
                                dest = os.path.join(PATH_SKIPPED_DELETED, f"{PREFIXE_DELETED}_{id_session_timestamp}.jpg")
                                shutil.move(p, dest)
                            except Exception as e: log_error(f"Erreur 10x15 Deleted: {e}")

                            terminer_session_et_revenir_accueil("abandoned")  # Sprint 4.4
                            dernier_clic_time = maintenant


                    # ==================================================================
                    # CAS DU MODE : STRIPS (Série de 3 photos)
                    # ==================================================================
                    elif mode_actuel == "strips":
                        
                        # --- GAUCHE : REFAIRE LA DERNIÈRE PHOTO ---
                        if event.key == TOUCHE_GAUCHE:
                            print("LOG: [Strips] -> Refaire la dernière photo")
                            if len(photos_validees) > 0:
                                photos_validees.pop()
                            img_preview_cache = None # Crucial pour forcer la mise à jour au prochain tour
                            etat = Etat.DECOMPTE
                            dernier_clic_time = maintenant

                        # --- MILIEU : VALIDER ET CONTINUER / FINIR ---
                        elif event.key == TOUCHE_MILIEU:
                            img_preview_cache = None # On vide le cache car on change de photo
                            if len(photos_validees) < 3:
                                print(f"LOG: [Strips] -> Photo {len(photos_validees)} validée")
                                etat = Etat.DECOMPTE
                            else:
                                print("LOG: [Strips] -> 3 photos OK, passage à l'écran FIN")
                                path_montage = generer_preview_ecran_strip(photos_validees)
                                etat = Etat.FIN
                            dernier_clic_time = maintenant

                        # --- DROITE : TOUT ANNULER ---
                        elif event.key == TOUCHE_DROITE:
                            terminer_session_et_revenir_accueil("abandoned")  # Sprint 4.4
                            dernier_clic_time = maintenant

                    continue # Sortie propre du bloc validation

            # --- 3. ÉTAT FIN (Aperçu final du montage) ---
            elif etat is Etat.FIN:
                if ecoule >= 1.0:
                    # --- BOUTON GAUCHE : RECOMMENCER ---
                    if event.key == TOUCHE_GAUCHE:
                        print("LOG: [FIN] -> Recommencer : Archivage et relance")
                        abandon_confirm_until = 0.0  # Sprint 2.8 : toute autre touche annule la confirmation
                        try:
                            # Sprint 3.2 : archive final threadée avec spinner
                            if mode_actuel == "strips":
                                p = executer_avec_spinner(
                                    lambda: generer_montage_impression_strip(photos_validees, id_session_timestamp),
                                    TXT_PREPARATION_IMP,
                                )
                            else:
                                p = executer_avec_spinner(
                                    lambda: generer_montage_final_10x15(photos_validees, id_session_timestamp),
                                    TXT_PREPARATION_IMP,
                                )

                            if os.path.exists(p):
                                nom_dest = f"{PREFIXE_RETAKE}_{id_session_timestamp}.jpg"
                                dest = os.path.join(PATH_SKIPPED_RETAKE, nom_dest)
                                shutil.move(p, dest)
                        except Exception as e:
                            log_error(f"Erreur archivage Recommencer : {e}")

                        # On vide les photos et on repart directement au décompte
                        photos_validees = []; img_preview_cache = None; path_montage = ""; etat = Etat.DECOMPTE
                        dernier_clic_time = maintenant
                        pygame.event.clear()
                        continue

                    # --- BOUTON MILIEU : IMPRIMER ---
                    elif event.key == TOUCHE_MILIEU:
                        print(f"LOG: [FIN] -> Impression ({mode_actuel})")
                        abandon_confirm_until = 0.0  # Sprint 2.8
                        try:
                            # Sprint 3.2 : génération threadée avec spinner animé
                            if mode_actuel == "strips":
                                p = executer_avec_spinner(
                                    lambda: generer_montage_impression_strip(photos_validees, id_session_timestamp),
                                    TXT_PREPARATION_IMP,
                                )
                                nom_final = f"{PREFIXE_PRINT_STRIP}_{id_session_timestamp}.jpg"
                                destination = os.path.join(PATH_PRINT_STRIP, nom_final)
                            else:
                                p = executer_avec_spinner(
                                    lambda: generer_montage_final_10x15(photos_validees, id_session_timestamp),
                                    TXT_PREPARATION_IMP,
                                )
                                nom_final = f"{PREFIXE_PRINT_10X15}_{id_session_timestamp}.jpg"
                                destination = os.path.join(PATH_PRINT_10X15, nom_final)

                            # 2. Sauvegarde dans le dossier PRINT
                            shutil.copy(p, destination)

                            # 3. IMPRESSION PHYSIQUE avec vérification (Sprint 2.6)
                            if imprimer_fichier_auto(destination, mode_actuel):
                                jouer_son("success")  # Sprint 2.3
                                ecran_attente_impression()
                            else:
                                ecran_erreur(TXT_ERREUR_IMPRIMANTE)  # Sprint 2.5

                        except Exception as e:
                            log_error(f"❌ Erreur Impression finale : {e}")
                            ecran_erreur(TXT_ERREUR_IMPRIMANTE)

                        # Cooldown anti double-envoi (Sprint 2.7)
                        pygame.event.clear()

                        # Sprint 4.4 : metadata + reset + retour accueil
                        terminer_session_et_revenir_accueil("printed")
                        dernier_clic_time = maintenant
                        continue

                    # --- BOUTON DROITE : SUPPRIMER / ABANDON (Sprint 2.8 : double-press confirm) ---
                    elif event.key == TOUCHE_DROITE:
                        if abandon_confirm_until and time.time() < abandon_confirm_until:
                            # 2e appui dans la fenêtre → on confirme l'abandon
                            print("LOG: [FIN] -> Abandon confirmé (deleted_)")
                            abandon_confirm_until = 0.0
                            try:
                                # Sprint 3.2 : archive threadée avec spinner
                                if mode_actuel == "strips":
                                    p = executer_avec_spinner(
                                        lambda: generer_montage_impression_strip(photos_validees, id_session_timestamp),
                                        TXT_PREPARATION_IMP,
                                    )
                                else:
                                    p = executer_avec_spinner(
                                        lambda: generer_montage_final_10x15(photos_validees, id_session_timestamp),
                                        TXT_PREPARATION_IMP,
                                    )

                                if os.path.exists(p):
                                    nom_deleted = f"{PREFIXE_DELETED}_{id_session_timestamp}.jpg"
                                    dest = os.path.join(PATH_SKIPPED_DELETED, nom_deleted)
                                    shutil.move(p, dest)
                            except Exception as e:
                                log_error(f"Erreur archivage Supprimer : {e}")

                            terminer_session_et_revenir_accueil("abandoned")  # Sprint 4.4
                            dernier_clic_time = maintenant
                            continue
                        else:
                            # 1er appui → on arme la confirmation, pas d'abandon immédiat
                            print("LOG: [FIN] -> Demande de confirmation abandon")
                            abandon_confirm_until = time.time() + DUREE_CONFIRM_ABANDON
                            dernier_clic_time = maintenant
                            continue


    # ----------------------------------------------------------------------------------------------------
    # ----------------------------------------------------------------------------------------------------
    # ----------------------------------------------------------------------------------------------------
    # ----------------------------------------------------------------------------------------------------
    # --- 2 ------ DESSIN A L'ECRAN --- ##################################################################
    # ----------------------------------------------------------------------------------------------------

    if etat is Etat.ACCUEIL:
        # Sprint 5.6 : check espace disque à chaque passage sur l'accueil (rate-limité)
        verifier_disque_periodiquement()

        # --- SLIDESHOW D'ATTENTE (Sprint 6.2) ---
        # Si plus de DUREE_IDLE_SLIDESHOW secondes sans activité et aucun mode sélectionné,
        # on fait défiler les montages précédents en plein écran pour attirer les invités.
        idle_seconds = time.time() - last_activity_ts
        if idle_seconds > DUREE_IDLE_SLIDESHOW and mode_actuel is None:
            # Rafraîchit la liste périodiquement (pour inclure les impressions récentes)
            if time.time() - slideshow_last_refresh > 30.0 or not slideshow_images:
                slideshow_images = lister_images_slideshow()
                slideshow_last_refresh = time.time()
                slideshow_cached_for_idx = -1  # invalide le cache (liste a pu changer)

            screen.fill((0, 0, 0))
            if slideshow_images:
                # Index basé sur le temps écoulé en slideshow
                temps_slideshow = idle_seconds - DUREE_IDLE_SLIDESHOW
                idx = int(temps_slideshow / DUREE_PAR_IMAGE_SLIDESHOW) % len(slideshow_images)
                if idx != slideshow_cached_for_idx:
                    try:
                        raw = pygame.image.load(slideshow_images[idx]).convert()
                        iw, ih = raw.get_size()
                        scale = min(WIDTH / iw, HEIGHT / ih)
                        new_size = (int(iw * scale), int(ih * scale))
                        slideshow_cached_surface = pygame.transform.smoothscale(raw, new_size)
                        slideshow_cached_for_idx = idx
                    except Exception as e:
                        log_error(f"⚠️ Slideshow load échoué : {e}")
                        slideshow_cached_surface = None

                if slideshow_cached_surface:
                    sx = (WIDTH - slideshow_cached_surface.get_width()) // 2
                    sy = (HEIGHT - slideshow_cached_surface.get_height()) // 2
                    screen.blit(slideshow_cached_surface, (sx, sy))
            else:
                # Pas d'images passées : on garde le fond d'accueil
                inserer_background(screen, fond_accueil)

            # Invitation pulsée en bas
            alpha_inv = 150 + int(80 * math.sin(time.time() * 2))
            inv_surf = font_titre.render(TXT_SLIDESHOW_INVITATION, True, (255, 255, 255))
            inv_surf.set_alpha(alpha_inv)
            inv_x = WIDTH // 2 - inv_surf.get_width() // 2
            # Bandeau noir derrière le texte pour lisibilité sur toute image
            inv_bg = pygame.Surface((WIDTH, inv_surf.get_height() + 30), pygame.SRCALPHA)
            inv_bg.fill((0, 0, 0, 130))
            screen.blit(inv_bg, (0, HEIGHT - inv_surf.get_height() - 60))
            screen.blit(inv_surf, (inv_x, HEIGHT - inv_surf.get_height() - 45))

            pygame.display.flip()
            clock.tick(30)
            continue  # on ne rend pas l'accueil normal

        # --- ACCUEIL NORMAL ---
        inserer_background(screen, fond_accueil)
        marge_centrale = MARGE_ACCUEIL
        axe_y_centre = (HEIGHT // 2) - 60
        
        # --- Effet de clignotement doux (pulsation) ---
        amplitude = (PULSE_MAX - PULSE_MIN) // 2
        moyenne = PULSE_MIN + amplitude
        pulse = moyenne + int(amplitude * math.sin(time.time() * PULSE_VITESSE))
        
        amp_lente = (PULSE_LENT_MAX - PULSE_LENT_MIN) // 2
        moy_lente = PULSE_LENT_MIN + amp_lente
        pulse_lent = moy_lente + int(amp_lente * math.sin(time.time() * PULSE_LENT_VITESSE))

        # On calcule le mélange de couleur entre OFF et ON
        facteur_pulse = (pulse - PULSE_MIN) / (PULSE_MAX - PULSE_MIN) if (PULSE_MAX - PULSE_MIN) != 0 else 0

        # Calcul de la couleur mélangée
        r = int(COULEUR_TEXTE_OFF[0] + (COULEUR_TEXTE_ON[0] - COULEUR_TEXTE_OFF[0]) * facteur_pulse)
        g = int(COULEUR_TEXTE_OFF[1] + (COULEUR_TEXTE_ON[1] - COULEUR_TEXTE_OFF[1]) * facteur_pulse)
        b = int(COULEUR_TEXTE_OFF[2] + (COULEUR_TEXTE_ON[2] - COULEUR_TEXTE_OFF[2]) * facteur_pulse)
        couleur_choisie = (r, g, b)

        # --- BLOC GAUCHE : 10x15 ---
        if icon_10x15_norm:
            is_sel = (mode_actuel == "10x15")
            img_draw = icon_10x15_select if is_sel else icon_10x15_norm
            
            # Calcul de base + ton OFFSET (vers la droite si positif)
            x_10 = (WIDTH // 2) - img_draw.get_width() - (marge_centrale // 2) + OFFSET_DROITE_10X15
            
            y_10 = axe_y_centre - (img_draw.get_height() // 2)
            img_draw.set_alpha(pulse if is_sel else 130)
            screen.blit(img_draw, (x_10, y_10))
            
            color_txt_10 = couleur_choisie if (mode_actuel == "10x15") else COULEUR_TEXTE_REPOS
            txt_10 = font_boutons.render(MODE_10x15, True, color_txt_10)
            if not is_sel:   # --- TRANSPARENCE AU REPOS ---
                txt_10.set_alpha(ALPHA_TEXTE_REPOS)

            screen.blit(txt_10, (x_10 + img_draw.get_width()//2 - txt_10.get_width()//2, y_10 + img_draw.get_height() + 20))

        # --- BLOC DROIT : STRIPS ---
        if icon_strip_norm:
            is_sel = (mode_actuel == "strips")
            img_draw = icon_strip_select if is_sel else icon_strip_norm
            
            # Calcul de base + ton OFFSET (vers la droite si positif)
            x_s = (WIDTH // 2) + (marge_centrale // 2) + OFFSET_DROITE_STRIP
            
            y_s = axe_y_centre - (img_draw.get_height() // 2)
            img_draw.set_alpha(pulse if is_sel else 130)
            screen.blit(img_draw, (x_s, y_s))
            
            color_txt_s = couleur_choisie if (mode_actuel == "strips") else COULEUR_TEXTE_REPOS
            txt_s = font_boutons.render(MODE_STRIP, True, color_txt_s)
            if not is_sel:  # --- TRANSPARENCE AU REPOS ---
                txt_s.set_alpha(ALPHA_TEXTE_REPOS)
            screen.blit(txt_s, (x_s + img_draw.get_width()//2 - txt_s.get_width()//2, y_s + img_draw.get_height() + 20))

        # --- BANDEAU NAVIGATION (Sprint 3.4 : surface cachée) ---
        screen.blit(BANDEAU_CACHE, (0, HEIGHT - BANDEAU_HAUTEUR))

        # Choix du texte selon le mode
        if mode_actuel == "10x15":
            msg_txt = BANDEAU_10X15
        elif mode_actuel == "strips":
            msg_txt = BANDEAU_STRIP
        else:
            msg_txt = BANDEAU_ACCUEIL

        # Gestion de la couleur de pulsation (Blanc/Gris)
        couleur_txt_bandeau = (pulse, pulse, pulse) if mode_actuel else (pulse_lent, pulse_lent, pulse_lent)
        
        msg_rendu = font_bandeau.render(msg_txt, True, couleur_txt_bandeau)

        # Centrage automatique basé sur la hauteur configurée
        pos_x = WIDTH // 2 - msg_rendu.get_width() // 2
        pos_y = (HEIGHT - BANDEAU_HAUTEUR // 2) - (msg_rendu.get_height() // 2)

        screen.blit(msg_rendu, (pos_x, pos_y))

        # --- INDICATEUR DISQUE CRITIQUE (Sprint 5.6) ---
        # Seulement visible de l'accueil : bandeau rouge semi-transparent en haut avec
        # l'espace restant, pour que l'admin puisse réagir avant que ça bloque.
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

    elif etat is Etat.DECOMPTE:
        # --- LOGIQUE DE RATIO ET MASQUE SELON LE MODE ---
        if mode_actuel == "strips":
            p_ratio = config.STRIP_PHOTO_RATIO
            alpha_masque = config.MASQUE 
        else:
            p_ratio = 0.66  
            alpha_masque = 0 

        # --- INITIALISATION DE L'ID DE SESSION (Si première photo) ---
        if len(photos_validees) == 0:
            id_session_timestamp = datetime.now().strftime(FORMAT_TIMESTAMP)
            session_start_ts = time.time()  # Sprint 5.4 : durée de session
            log_info(f"🚀 NOUVELLE SESSION : {id_session_timestamp}")

        # Boucle du décompte visuel
        for i in range(TEMPS_DECOMPTE, 0, -1):
            jouer_son("beep")  # Sprint 2.3 : tick audio à chaque seconde
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

                    if mode_actuel == "strips":
                        # Sprint 6.3 : compteur grand + shadow pour être lisible par dessus le preview
                        txt_label = f"{TEXTE_PHOTO_COUNT} {len(photos_validees) + 1} / 3"
                        label_surf = font_boutons.render(txt_label, True, COULEUR_DECOMPTE)
                        label_x = WIDTH // 2 - label_surf.get_width() // 2
                        draw_text_shadow_soft(
                            screen, txt_label, font_boutons, COULEUR_DECOMPTE,
                            label_x, 30, shadow_alpha=180, offset=3,
                        )

                    num_surf = font_decompte.render(str(i), True, COULEUR_DECOMPTE)
                    screen.blit(num_surf, (WIDTH//2 - num_surf.get_width()//2, HEIGHT//2 - num_surf.get_height()//2))
                
                pygame.display.flip()
                pygame.event.pump()
                
        # --- CAPTURE HQ ---
        # On calcule l'index de la photo (1, 2 ou 3)
        index_photo = len(photos_validees) + 1

        # On appelle la fonction HQ qui utilise maintenant le config.py
        chemin_photo = capturer_hq(id_session_timestamp, index_photo)

        if chemin_photo:
            photos_validees.append(chemin_photo)
            etat = Etat.VALIDATION
        else:
            log_error("Erreur capture : retour à l'accueil")
            ecran_erreur(TXT_ERREUR_CAPTURE)  # Sprint 2.5
            terminer_session_et_revenir_accueil("capture_failed")  # Sprint 4.4

        dernier_clic_time = time.time()
        continue


    elif etat is Etat.VALIDATION:
        inserer_background(screen, fond_accueil)

        # 1. Gestion de l'aperçu (Image seule)
        if not img_preview_cache and len(photos_validees) > 0:
            derniere_photo = photos_validees[-1]

            # --- SELECTION DE LA HAUTEUR SELON LE MODE ---
            if mode_actuel == "strips":
                hauteur_cible = getattr(config, 'PREVISU_H_STRIP', 600)
                r_v = float(getattr(config, 'STRIP_PHOTO_RATIO', 1.0))
            else:
                hauteur_cible = getattr(config, 'PREVISU_H', 533)
                r_v = 0.66  # Ratio standard 2:3 (3:2 couché)

            # Calcul de la largeur automatique pour respecter le ratio
            largeur_cible = int(hauteur_cible / r_v)

            # --- TRAITEMENT IMAGE ---
            # `with` garantit la fermeture du handle fichier (sinon fuite mémoire 30 FPS)
            with Image.open(derniere_photo) as raw_img:
                oriented = ImageOps.exif_transpose(raw_img)

            # fit() découpe proprement sans étirer
            pil_img = ImageOps.fit(oriented, (largeur_cible, hauteur_cible), Image.Resampling.LANCZOS)

            # Conversion vers Pygame
            img_preview_cache = pygame.image.fromstring(
                pil_img.tobytes(), pil_img.size, pil_img.mode
            ).convert()

        # 2. AFFICHAGE (Centrage automatique)
        if img_preview_cache:
            m_t = str(mode_actuel).lower().strip()
            dec = getattr(config, 'DECALAGE_Y_PREVISU_10X15', 0) if m_t == "10x15" else getattr(config, 'DECALAGE_Y_PREVISU_STRIPS', 0)
            
            # On centre par rapport à la largeur réelle de l'image générée
            x_p = (WIDTH // 2) - (img_preview_cache.get_width() // 2)
            y_p = (HEIGHT // 2) - (img_preview_cache.get_height() // 2) + dec
            
            # Cadre blanc
            pygame.draw.rect(screen, (255, 255, 255), (x_p - 10, y_p - 10, img_preview_cache.get_width() + 20, img_preview_cache.get_height() + 20))
            screen.blit(img_preview_cache, (x_p, y_p))

        # 3. Bandeau et Boutons (Sprint 3.4 : surface cachée)
        y_b = HEIGHT - BANDEAU_HAUTEUR
        screen.blit(BANDEAU_CACHE, (0, y_b))
        y_t = y_b + (BANDEAU_HAUTEUR // 2) - (font_bandeau.get_height() // 2)

        # --- SÉLECTION DES TEXTES SELON LE MODE ---
        if mode_actuel == "strips":
            txt_g = config.TXT_VALID_REPRENDRE_STRIP
            txt_m = config.TXT_VALID_VALIDER_STRIP
            txt_d = config.TXT_VALID_ACCUEIL_STRIP
        else:
            # Mode 10x15
            txt_g = config.TXT_VALID_REPRENDRE_10X15
            txt_m = config.TXT_VALID_VALIDER_10X15
            txt_d = config.TXT_VALID_ACCUEIL_10X15

        # --- AFFICHAGE DES TEXTES ---
        # Bouton Gauche
        screen.blit(font_bandeau.render(txt_g, True, config.COULEUR_TEXTE_G), (80, y_t))
        
        # Bouton Milieu (Centré)
        t_m = font_bandeau.render(txt_m, True, config.COULEUR_TEXTE_M)
        screen.blit(t_m, (WIDTH // 2 - t_m.get_width() // 2, y_t))
        
        # Bouton Droit
        t_d = font_bandeau.render(txt_d, True, config.COULEUR_TEXTE_D)
        screen.blit(t_d, (WIDTH - 80 - t_d.get_width(), y_t))

        # Compteur (Uniquement pour le mode strips)
        if mode_actuel == "strips":
            txt_c = f"{config.TEXTE_PHOTO_COUNT} {len(photos_validees)} / 3"
            draw_text_shadow_soft(screen, txt_c, font_bandeau, (255, 215, 0), WIDTH//2 - font_bandeau.size(txt_c)[0]//2, 10)

    elif etat is Etat.FIN:
        inserer_background(screen, fond_accueil)

        # 1. Récupération de l'image
        p_prev = path_montage if path_montage else os.path.join(getattr(config, 'PATH_TEMP', 'temp'), "montage_prev.jpg")

        if img_preview_cache is None:
            if os.path.exists(p_prev):
                try:
                    raw_m = pygame.image.load(p_prev).convert_alpha()
                    h_max_fin = 600 if mode_actuel == "strips" else 520
                    ratio_m = raw_m.get_width() / raw_m.get_height()
                    img_preview_cache = pygame.transform.smoothscale(raw_m, (int(h_max_fin * ratio_m), h_max_fin))
                except Exception as e:
                    log_error(f"Erreur chargement aperçu FIN : {e}")

        # 2. APPLICATION DES DÉCALAGES SPÉCIFIQUES
        if img_preview_cache:
            if mode_actuel == "strips":
                # On utilise ta variable exacte :
                dec_y = getattr(config, 'DECALAGE_Y_MONTAGE_FINAL_STRIP', 0)
            else:
                # Pour le 10x15, on utilise ta variable de prévisu (comme tu l'avais fait au début)
                dec_y = getattr(config, 'DECALAGE_Y_PREVISU_10X15', 0)
            
            x_m = (WIDTH - img_preview_cache.get_width()) // 2
            y_m = (HEIGHT // 2 - img_preview_cache.get_height() // 2) + dec_y
            
            # Cadre blanc + Image
            pygame.draw.rect(screen, (255, 255, 255), (x_m - 10, y_m - 10, img_preview_cache.get_width() + 20, img_preview_cache.get_height() + 20))
            screen.blit(img_preview_cache, (x_m, y_m))
            
        # 3. Bandeau de boutons (Sprint 3.4 : surface cachée)
        y_b = HEIGHT - BANDEAU_HAUTEUR
        screen.blit(BANDEAU_CACHE, (0, y_b))

        y_t = y_b + (BANDEAU_HAUTEUR // 2) - (font_bandeau.get_height() // 2)
        txt_g = config.TXT_BOUTON_REPRENDRE if mode_actuel == "10x15" else config.TXT_BOUTON_ACCUEIL
        screen.blit(font_bandeau.render(txt_g, True, config.COULEUR_TEXTE_G), (80, y_t))
        t_m = font_bandeau.render(config.TXT_BOUTON_IMPRIMER, True, config.COULEUR_TEXTE_M)
        screen.blit(t_m, (WIDTH // 2 - t_m.get_width() // 2, y_t))
        t_d = font_bandeau.render(config.TXT_BOUTON_SUPPRIMER, True, config.COULEUR_TEXTE_D)
        screen.blit(t_d, (WIDTH - 80 - t_d.get_width(), y_t))

        # --- OVERLAY CONFIRMATION ABANDON (Sprint 2.8) ---
        # Si le flag est armé et encore dans la fenêtre, on montre un avertissement visible.
        # Passée la fenêtre, on l'efface silencieusement pour revenir à l'affichage normal.
        if abandon_confirm_until:
            if time.time() < abandon_confirm_until:
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 170))
                screen.blit(overlay, (0, 0))
                t1 = font_titre.render(TXT_CONFIRM_ABANDON_1, True, (255, 120, 120))
                screen.blit(t1, (WIDTH // 2 - t1.get_width() // 2, HEIGHT // 2 - 120))
                t2 = font_bandeau.render(TXT_CONFIRM_ABANDON_2, True, (255, 255, 255))
                screen.blit(t2, (WIDTH // 2 - t2.get_width() // 2, HEIGHT // 2 + 20))
            else:
                abandon_confirm_until = 0.0
    pygame.display.flip()
    clock.tick(30)

pygame.quit()

