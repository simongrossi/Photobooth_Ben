from config import * # Cela importe TOUTES les variables de ton fichier config
import pygame
import cv2
import os
import time
import subprocess
import numpy as np
import gphoto2 as gp
import shutil
import math
from PIL import Image, ImageOps, ImageDraw
from datetime import datetime




# ========================================================================================================
# --- PRÉPARATION DES DOSSIERS & LOGS --- ############################################################
# ========================================================================================================

# On centralise TOUS les dossiers définis dans config.py
dossiers_requis = [
    PATH_RAW, PATH_TEMP, PATH_PRINT, PATH_SKIPPED,
    PATH_PRINT_10X15, PATH_PRINT_STRIP, 
    PATH_SKIPPED_RETAKE, PATH_SKIPPED_DELETED,
    "logs"
]

for d in dossiers_requis:
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
        print(f"📁 Dossier créé : {d}")

# Configuration du fichier de log
log_file = os.path.join("logs", f"log_{datetime.now().strftime('%Y-%m-%d')}.txt")

def log_error(message):
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        msg_complet = f"[{timestamp}] {message}"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(msg_complet + "\n")
        print(f"📝 {msg_complet}")
    except:
        print(f"❌ Erreur critique LOG : {message}")

log_error("====================================================")
log_error("DÉMARRAGE DU PHOTOBOOTH (Dossiers OK)")
log_error("====================================================")


# ========================================================================================================
# --- GESTION CANON --- ##################################################################################
# ========================================================================================================

def init_camera():
    # Nettoyage des processus système qui bloquent souvent l'USB sur Linux
    subprocess.run(["pkill", "-f", "gvfs-gphoto2-volume-monitor"], capture_output=True)
    subprocess.run(["pkill", "-f", "gphoto2"], capture_output=True)
    
    try:
        cam = gp.Camera()
        cam.init()
        log_error("📸 Canon initialisée avec succès !")
        return cam
    except Exception as e:
        # On ne log pas l'erreur en boucle ici pour ne pas saturer le fichier texte
        return None

def set_liveview(cam, state):
    if not cam: return
    try:
        cfg = cam.get_config()
        vf = cfg.get_child_by_name('viewfinder')
        vf.set_value(state)
        cam.set_config(cfg)
    except Exception as e:
        log_error(f"⚠️ Impossible de régler le LiveView : {e}")

# Initialisation globale
camera = init_camera()
if camera:
    set_liveview(camera, 1)

def get_canon_frame():
    global camera
    try:
        # Si la caméra n'est pas là, on tente une reconnexion discrète
        if camera is None:
            camera = init_camera()
            if camera: set_liveview(camera, 1)
            return None

        # Capture du flux direct
        capture = camera.capture_preview()
        file_bits = capture.get_data_and_size()
        image_data = np.frombuffer(memoryview(file_bits), dtype=np.uint8)
        frame = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        
        if frame is not None:
            # Conversion et rotation pour Pygame
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.flip(frame, 1)
            frame = np.rot90(frame)
            return pygame.surfarray.make_surface(frame)
            
    except gp.GPhoto2Error:
        # Si gphoto2 perd la main, on met camera à None pour forcer la reconnexion au prochain tour
        camera = None
        return None
    except Exception as e:
        return None

# ========================================================================================================
# --- 2. FONCTIONS TECHNIQUES --- ########################################################################
# ========================================================================================================

def capturer_hq(id_session, index_photo):
    """ Procédure de capture sécurisée pour Canon 500D avec Flash et Préfixes Config """
    global camera
    
    # --- NOUVEAU : Construction automatique du nom avec tes réglages ---
    # Utilise PREFIXE_RAW ("photo") et PATH_RAW ("data/raw") de ton config.py
    nom_final = f"{PREFIXE_RAW}_{id_session}_{index_photo}.jpg"
    chemin_complet = os.path.join(PATH_RAW, nom_final)

    # 1. Sécurité : On vérifie si la caméra existe avant de couper le LiveView
    if camera:
        try:
            log_error("Fermeture LiveView pour capture...")
            set_liveview(camera, 0)
            time.sleep(0.5)
            camera.exit()
            print("Session gphoto2 fermée proprement.")
        except Exception as e:
            log_error(f"⚠️ Warning lors de la fermeture caméra : {e}")
    else:
        log_error("⚠️ Camera non initialisée (None), tentative de capture directe...")

    # 2. Flash blanc (Interface) avec message "SOURIEZ !"
    screen.fill(COULEUR_FLASH)
    try:
        # On utilise font_titre et COULEUR_SOURIEZ de ton config.py
        txt_flash = font_titre.render("SOURIEZ !", True, COULEUR_SOURIEZ)
        text_x = (WIDTH // 2) - (txt_flash.get_width() // 2)
        text_y = (HEIGHT // 2) - (txt_flash.get_height() // 2)
        screen.blit(txt_flash, (text_x, text_y))
    except:
        pass
        
    pygame.display.flip()
    
    # 3. Capture réelle via Subprocess
    log_error(f"📸 Capture HQ en cours : {nom_final}")
    try:
        subprocess.run([
            "gphoto2", 
            "--capture-image-and-download", 
            "--filename", chemin_complet, # On utilise le chemin complet vers data/raw
            "--force-overwrite"
        ], check=True)
    except subprocess.CalledProcessError as e:
        log_error(f"❌ Erreur gphoto2 : {e}")

    # 4. Réinitialisation de la session pour le LiveView suivant
    log_error("Relancement du LiveView...")
    camera = init_camera()
    if camera:
        try:
            set_liveview(camera, 1)
        except Exception as e:
            log_error(f"⚠️ Impossible de relancer le LiveView : {e}")
    
    # 5. Vérification finale
    success = os.path.exists(chemin_complet)
    if success:
        log_error(f"✅ Photo sauvegardée : {nom_final}")
    else:
        log_error(f"❌ ÉCHEC : Le fichier {nom_final} est introuvable.")
        
    return chemin_complet if success else None


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
# --- 3. TRAITEMENT IMAGE --- ############################################################################
# ========================================================================================================

def charger_et_corriger(chemin, rotation_forcee=0):
    img = Image.open(chemin).convert("RGB")
    
    # Si on demande une rotation manuelle, on l'applique
    if rotation_forcee != 0:
        img = img.rotate(rotation_forcee, expand=True)
    return img

def generer_preview_10x15(photos):
    """ GÉNÈRE L'APERÇU ÉCRAN : Photo seule + Cadre blanc """
    from PIL import Image, ImageOps
    import os, config
    p_temp = getattr(config, 'PATH_TEMP', 'temp')
    path_prev = os.path.join(p_temp, "montage_prev.jpg")

    # On crée un cadre blanc simple
    canvas = Image.new('RGB', (900, 600), 'white') 
    img_brute = charger_et_corriger(photos[0])
    # On centre la photo avec une petite marge
    photo_fit = ImageOps.fit(img_brute, (840, 540), Image.Resampling.LANCZOS)
    canvas.paste(photo_fit, (30, 30))
    
    canvas.save(path_prev, quality=80)
    return path_prev

def generer_montage_final_10x15(photos, id_session): # <--- Ajout id_session
    """ GÉNÈRE LE MONTAGE HD : Avec Fond + Overlay et le BON NOM """
    from PIL import Image, ImageOps
    import os, config
    p_temp = getattr(config, 'PATH_TEMP', 'temp')
    # On utilise l'ID pour nommer le fichier de sortie
    path_hd = os.path.join(p_temp, f"{PREFIXE_PRINT_10X15}_{id_session}.jpg")

    if os.path.exists(BG_10X15_FILE):
        canvas = Image.open(BG_10X15_FILE).convert("RGB").resize((1800, 1200))
    else:
        canvas = Image.new('RGB', (1800, 1200), 'white')

    img_brute = charger_et_corriger(photos[0])
    photo_fit = ImageOps.fit(img_brute, (1640, 1040), Image.Resampling.LANCZOS)
    canvas.paste(photo_fit, (80, 80))
    
    if os.path.exists(OVERLAY_10X15):
        ov = Image.open(OVERLAY_10X15).convert("RGBA").resize((1800, 1200))
        canvas.paste(ov, (0, 0), ov)
    
    canvas.save(path_hd, quality=98)
    return path_hd

def generer_preview_ecran_strip(photos):
    """Génère une bandelette verticale ajustée aux photos pour l'écran"""
    from PIL import Image, ImageOps
    import os, config
    
    p_temp = getattr(config, 'PATH_TEMP', 'temp')
    path_prev = os.path.join(p_temp, "montage_prev.jpg")

    # 1. Calcul des dimensions
    l_p = 520
    ratio = float(getattr(config, 'STRIP_PHOTO_RATIO', 1.0))
    h_p = int(l_p * ratio)
    espacement = 40
    marge_haut_bas = 20 # Petite marge pour ne pas coller au bord
    
    # Hauteur totale dynamique : (3 photos * hauteur) + (2 espaces) + marges
    hauteur_totale = (h_p * 3) + (espacement * 2) + (marge_haut_bas * 2)

    # 2. Création du canevas sur mesure (plus de 1800 fixe !)
    bande_v = Image.new('RGB', (600, hauteur_totale), 'white')
    
    # 3. Placement des photos
    for i in range(min(len(photos), 3)):
        img = charger_et_corriger(photos[i], rotation_forcee=0)
        img_fit = ImageOps.fit(img, (l_p, h_p), Image.Resampling.LANCZOS)
        
        pos_y = marge_haut_bas + i * (h_p + espacement)
        # On centre horizontalement (600 - 520) / 2 = 40
        bande_v.paste(img_fit, (40, pos_y))
    
    # 4. Redimensionnement final pour Pygame (Thumbnail)
    # On garde le ratio, mais on limite la hauteur pour ton écran
    bande_v.thumbnail((400, 800), Image.Resampling.LANCZOS)
    bande_v.save(path_prev, "JPEG", quality=90)
    
    print(f"DEBUG: Preview générée avec hauteur {hauteur_totale}px")
    return path_prev

def generer_montage_impression_strip(photos, id_session): # <--- Ajout id_session
    """Génère la bandelette avec le nom de session synchronisé"""
    from PIL import Image, ImageOps
    import os, config
    
    p_print = os.path.join(getattr(config, 'PATH_PRINT', 'print')) 
    # On utilise l'ID ici aussi pour le nom final
    path_hd = os.path.join(PATH_TEMP, f"{PREFIXE_PRINT_STRIP}_{id_session}.jpg")

    # 1. Chargement et REDRESSEMENT du fond
    bg_path = getattr(config, 'BG_STRIPS_FILE', "")
    if os.path.exists(bg_path) and os.path.isfile(bg_path):
        bg = Image.open(bg_path).convert("RGB")
        # Si le fond est horizontal (1800x600), on le met debout
        if bg.width > bg.height:
            bg = bg.rotate(90, expand=True)
        # --- AJOUT DE LA ROTATION 180° ICI ---
        final = bg.rotate(180).resize((600, 1800))
    else:
        final = Image.new('RGB', (600, 1800), 'white')

    # 2. Variables de config
    marge_haut = getattr(config, 'STRIP_MARGE_HAUT', 30)
    marge_lat  = getattr(config, 'STRIP_MARGE_LATERALE', 30)
    espace_entre = getattr(config, 'STRIP_ESPACE_PHOTOS', 30)
    
    # 3. Calcul dynamique de la taille des photos
    photo_w = 600 - (2 * marge_lat)
    ratio = float(getattr(config, 'STRIP_PHOTO_RATIO', 1.0))
    photo_h = int(photo_w * ratio)

    # 4. Collage des 3 photos
    for i in range(min(len(photos), 3)):
        img = charger_et_corriger(photos[i], rotation_forcee=0)
        img_fit = ImageOps.fit(img, (photo_w, photo_h), Image.Resampling.LANCZOS)
        
        # Calcul de la position Y
        pos_y = marge_haut + i * (photo_h + espace_entre)
        
        # Collage (centré horizontalement par marge_lat)
        final.paste(img_fit, (marge_lat, pos_y))

    # 5. Gestion de l'Overlay (avec la même logique de rotation)
    overlay_path = getattr(config, 'OVERLAY_STRIPS', "")
    if os.path.exists(overlay_path):
        ov = Image.open(overlay_path).convert("RGBA")
        if ov.width > ov.height:
            ov = ov.rotate(90, expand=True)
        # --- AJOUT DE LA ROTATION 180° ICI ---
        ov = ov.rotate(180).resize((600, 1800))
        final.paste(ov, (0, 0), ov)

    # 6. Sauvegarde finale
    final.save(path_hd, "JPEG", quality=98)
    return path_hd


def get_pygame_surf_cropped(path, size_target, ratio_voulu):
    if not os.path.exists(path): 
        return None
    try:
        # On ouvre l'image brute, sans laisser PIL décider du sens via l'EXIF
        img = Image.open(path).convert("RGB")
        
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

        for i in reversed(range(ANIM_NB_POINTS)):
            progression = i / (ANIM_NB_POINTS - 1)
            fading = 1.0 - progression
            angle_point = math.radians(self.angle_tete - (progression * self.longueur_actuelle))
            
            x = WIDTH // 2 + math.cos(angle_point) * ANIM_TAILLE_ROUE
            y = HEIGHT // 2 + math.sin(angle_point) * ANIM_TAILLE_ROUE
            
            couleur = self.interpoler_couleur(ANIM_COULEUR_TETE, ANIM_COULEUR_QUEUE, fading)
            alpha = int(255 * (fading ** 0.6))
            
            s = pygame.Surface((ANIM_RAYON_POINT * 2, ANIM_RAYON_POINT * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*couleur, alpha), (ANIM_RAYON_POINT, ANIM_RAYON_POINT), ANIM_RAYON_POINT)
            screen.blit(s, (x - ANIM_RAYON_POINT, y - ANIM_RAYON_POINT))

# --- INITIALISATION DE L'OBJET ---
# On le crée une seule fois ici
mon_loader = LoaderAnimation()


def imprimer_fichier_auto(chemin, mode):
    """Envoie à la file d'attente correspondante selon le mode"""
    imprimante = NOM_IMPRIMANTE_10X15 if mode == "10x15" else NOM_IMPRIMANTE_STRIP
    
    try:
        # On lance l'impression en arrière-plan
        subprocess.Popen([
            "lp", "-d", imprimante, 
            "-o", "fit-to-page", 
            chemin
        ])
        log_error(f"🖨️ Impression lancée sur {imprimante}")
    except Exception as e:
        log_error(f"❌ Erreur impression : {e}")


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
        screen.fill((10, 10, 18)) # Fond bleu nuit
        
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

# --- VARIABLES DE SESSION ---
etat = "ACCUEIL"
photos_validees = []
id_session_timestamp = ""
mode_actuel = None
path_montage = ""
path_montage_hd = ""
running = True
selection = None  # Peut être "10X15" ou "STRIP"
dernier_clic_time = 0
img_preview_cache = None


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
            
            # --- 1. ÉTAT ACCUEIL ---
            if etat == "ACCUEIL":
                if ecoule > DELAI_SECURITE:
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
                            etat = "DECOMPTE"

            # --- 2. ÉTAT VALIDATION ---
            elif etat == "VALIDATION":
                if ecoule > 0.5: 

                    # ==================================================================
                    # CAS DU MODE : 10X15 (Direct, une seule photo)
                    # ==================================================================
                    if mode_actuel == "10x15":
                        
                        # --- GAUCHE : REFAIRE (Archivage SKIPPED + Relance) ---
                        if event.key == TOUCHE_GAUCHE:
                            print("LOG: [10x15] -> Refaire : Archivage RETAKE et relance")
                            try:
                                p = generer_montage_final_10x15(photos_validees, id_session_timestamp)
                                dest = os.path.join(PATH_SKIPPED_RETAKE, f"{PREFIXE_RETAKE}_{id_session_timestamp}.jpg")
                                shutil.move(p, dest)
                            except Exception as e: log_error(f"Erreur 10x15 Retake: {e}")
                            
                            photos_validees = [] 
                            etat = "DECOMPTE"
                            dernier_clic_time = maintenant

                        # --- MILIEU : IMPRIMER DIRECTEMENT ---
                        elif event.key == TOUCHE_MILIEU:
                            print("LOG: [10x15] -> Impression directe et Accueil")
                            try:
                                # 1. On prépare le fichier
                                p = generer_montage_final_10x15(photos_validees, id_session_timestamp)
                                dest = os.path.join(PATH_PRINT_10X15, f"{PREFIXE_PRINT_10X15}_{id_session_timestamp}.jpg")
                                shutil.copy(p, dest)
                                
                                # 2. On lance l'impression PHYSIQUE (seulement si le fichier est OK)
                                imprimer_fichier_auto(dest, "10x15")
                                
                                # 3. On affiche l'écran de chargement pour l'utilisateur
                                ecran_attente_impression()
                                
                            except Exception as e: 
                                log_error(f"Erreur 10x15 Print/Impression: {e}")

                            # 4. Dans tous les cas (succès ou erreur loggée), on reset pour le suivant
                            photos_validees = []; id_session_timestamp = ""; mode_actuel = None; img_preview_cache = None; etat = "ACCUEIL"
                            dernier_clic_time = maintenant

                        # --- DROITE : ABANDONNER ---
                        elif event.key == TOUCHE_DROITE:
                            print("LOG: [10x15] -> Abandon : Archivage DELETED et Accueil")
                            try:
                                p = generer_montage_final_10x15(photos_validees, id_session_timestamp)
                                dest = os.path.join(PATH_SKIPPED_DELETED, f"{PREFIXE_DELETED}_{id_session_timestamp}.jpg")
                                shutil.move(p, dest)
                            except Exception as e: log_error(f"Erreur 10x15 Deleted: {e}")

                            photos_validees = []; id_session_timestamp = ""; mode_actuel = None; etat = "ACCUEIL"
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
                            etat = "DECOMPTE"
                            dernier_clic_time = maintenant

                        # --- MILIEU : VALIDER ET CONTINUER / FINIR ---
                        elif event.key == TOUCHE_MILIEU:
                            img_preview_cache = None # On vide le cache car on change de photo
                            if len(photos_validees) < 3:
                                print(f"LOG: [Strips] -> Photo {len(photos_validees)} validée")
                                etat = "DECOMPTE"
                            else:
                                print("LOG: [Strips] -> 3 photos OK, passage à l'écran FIN")
                                path_montage = generer_preview_ecran_strip(photos_validees)
                                etat = "FIN"
                            dernier_clic_time = maintenant

                        # --- DROITE : TOUT ANNULER ---
                        elif event.key == TOUCHE_DROITE:
                            photos_validees = []; id_session_timestamp = ""; mode_actuel = None; img_preview_cache = None; etat = "ACCUEIL"
                            dernier_clic_time = maintenant

                    continue # Sortie propre du bloc validation

            # --- 3. ÉTAT FIN (Aperçu final du montage) --- 
            elif etat == "FIN":
                if ecoule > 1.0:
                    # --- BOUTON GAUCHE : RECOMMENCER ---
                    if event.key == TOUCHE_GAUCHE:
                        print("LOG: [FIN] -> Recommencer : Archivage et relance")
                        try:
                            # On génère le montage final pour l'archive
                            if mode_actuel == "strips":
                                p = generer_montage_impression_strip(photos_validees, id_session_timestamp)
                            else:
                                p = generer_montage_final_10x15(photos_validees, id_session_timestamp)

                            if os.path.exists(p):
                                nom_dest = f"{PREFIXE_RETAKE}_{id_session_timestamp}.jpg"
                                dest = os.path.join(PATH_SKIPPED_RETAKE, nom_dest)
                                shutil.move(p, dest)
                        except Exception as e:
                            log_error(f"Erreur archivage Recommencer : {e}")

                        # On vide les photos et on repart directement au décompte
                        photos_validees = []; img_preview_cache = None; path_montage = ""; etat = "DECOMPTE" 
                        dernier_clic_time = maintenant
                        pygame.event.clear()
                        continue 

                    # --- BOUTON MILIEU : IMPRIMER ---
                    elif event.key == TOUCHE_MILIEU:
                        print(f"LOG: [FIN] -> Impression ({mode_actuel})")
                        try:
                            # 1. Préparation du fichier final
                            if mode_actuel == "strips":
                                p = generer_montage_impression_strip(photos_validees, id_session_timestamp)
                                nom_final = f"{PREFIXE_PRINT_STRIP}_{id_session_timestamp}.jpg"
                                destination = os.path.join(PATH_PRINT_STRIP, nom_final)
                            else:
                                p = generer_montage_final_10x15(photos_validees, id_session_timestamp)
                                nom_final = f"{PREFIXE_PRINT_10X15}_{id_session_timestamp}.jpg"
                                destination = os.path.join(PATH_PRINT_10X15, nom_final)
                            
                            # 2. Sauvegarde dans le dossier PRINT
                            shutil.copy(p, destination)
                            
                            # 3. IMPRESSION PHYSIQUE
                            # On utilise le mode_actuel pour choisir la bonne file (DNP_10x15 ou DNP_STRIP)
                            imprimer_fichier_auto(destination, mode_actuel)
                            
                            # 4. Écran de chargement (Roue pour l'utilisateur)
                            ecran_attente_impression()

                        except Exception as e:
                            log_error(f"❌ Erreur Impression finale : {e}")
                        
                        # Retour propre à l'accueil
                        photos_validees = []; id_session_timestamp = ""; mode_actuel = None; img_preview_cache = None; path_montage = ""; etat = "ACCUEIL"
                        dernier_clic_time = maintenant
                        continue

                    # --- BOUTON DROITE : SUPPRIMER / ABANDON ---
                    elif event.key == TOUCHE_DROITE:
                        print("LOG: [FIN] -> Abandon (deleted_)")
                        try:
                            if mode_actuel == "strips":
                                p = generer_montage_impression_strip(photos_validees, id_session_timestamp)
                            else:
                                p = generer_montage_final_10x15(photos_validees, id_session_timestamp)

                            if os.path.exists(p):
                                nom_deleted = f"{PREFIXE_DELETED}_{id_session_timestamp}.jpg"
                                dest = os.path.join(PATH_SKIPPED_DELETED, nom_deleted)
                                shutil.move(p, dest)
                        except Exception as e:
                            log_error(f"Erreur archivage Supprimer : {e}")

                        photos_validees = []; id_session_timestamp = ""; mode_actuel = None; img_preview_cache = None; path_montage = ""; etat = "ACCUEIL"
                        dernier_clic_time = maintenant
                        continue


    # ----------------------------------------------------------------------------------------------------
    # ----------------------------------------------------------------------------------------------------
    # ----------------------------------------------------------------------------------------------------
    # ----------------------------------------------------------------------------------------------------
    # --- 2 ------ DESSIN A L'ECRAN --- ##################################################################
    # ----------------------------------------------------------------------------------------------------

    if etat == "ACCUEIL":
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

        # --- BANDEAU NAVIGATION ---
        # Utilisation des réglages centralisés dans le fichier config
        bandeau = pygame.Surface((WIDTH, BANDEAU_HAUTEUR))
        bandeau.set_alpha(BANDEAU_ALPHA)
        bandeau.fill(BANDEAU_COULEUR)
        screen.blit(bandeau, (0, HEIGHT - BANDEAU_HAUTEUR))

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

    elif etat == "DECOMPTE":
        import config
        import importlib
        importlib.reload(config)
        
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
            log_error(f"🚀 NOUVELLE SESSION : {id_session_timestamp}")

        # Boucle du décompte visuel
        for i in range(TEMPS_DECOMPTE, 0, -1):
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
                        txt_label = f"{config.TEXTE_PHOTO_COUNT} {len(photos_validees) + 1} / 3"
                        label_surf = font_bandeau.render(txt_label, True, COULEUR_DECOMPTE)
                        screen.blit(label_surf, (WIDTH // 2 - label_surf.get_width() // 2, 40))

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
            etat = "VALIDATION"
        else:
            log_error("Erreur capture : retour à l'accueil")
            etat = "ACCUEIL"
        
        dernier_clic_time = time.time()
        continue


    elif etat == "VALIDATION":
        import config
        import importlib
        importlib.reload(config)
        inserer_background(screen, fond_accueil)

        # 1. Gestion de l'aperçu (Image seule)
        if not img_preview_cache and len(photos_validees) > 0:
            from PIL import Image, ImageOps
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
            pil_img = Image.open(derniere_photo)
            pil_img = ImageOps.exif_transpose(pil_img)
            
            # fit() découpe proprement sans étirer
            pil_img = ImageOps.fit(pil_img, (largeur_cible, hauteur_cible), Image.Resampling.LANCZOS)
            
            # Conversion vers Pygame
            mode = pil_img.mode
            size = pil_img.size
            data = pil_img.tobytes()
            img_preview_cache = pygame.image.fromstring(data, size, mode).convert()

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

        # 3. Bandeau et Boutons
        y_b = HEIGHT - config.BANDEAU_HAUTEUR
        bandeau_s = pygame.Surface((WIDTH, config.BANDEAU_HAUTEUR))
        bandeau_s.set_alpha(config.BANDEAU_ALPHA); bandeau_s.fill(config.BANDEAU_COULEUR)
        screen.blit(bandeau_s, (0, y_b))
        y_t = y_b + (config.BANDEAU_HAUTEUR // 2) - (font_bandeau.get_height() // 2)

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

    elif etat == "FIN":
        import config
        import importlib
        importlib.reload(config)
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
                except: pass

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
            
        # 3. Bandeau de boutons
        y_b = HEIGHT - config.BANDEAU_HAUTEUR
        bandeau_s = pygame.Surface((WIDTH, config.BANDEAU_HAUTEUR))
        bandeau_s.set_alpha(config.BANDEAU_ALPHA); bandeau_s.fill(config.BANDEAU_COULEUR)
        screen.blit(bandeau_s, (0, y_b))
        
        y_t = y_b + (config.BANDEAU_HAUTEUR // 2) - (font_bandeau.get_height() // 2)
        txt_g = config.TXT_BOUTON_REPRENDRE if mode_actuel == "10x15" else config.TXT_BOUTON_ACCUEIL
        screen.blit(font_bandeau.render(txt_g, True, config.COULEUR_TEXTE_G), (80, y_t))
        t_m = font_bandeau.render(config.TXT_BOUTON_IMPRIMER, True, config.COULEUR_TEXTE_M)
        screen.blit(t_m, (WIDTH // 2 - t_m.get_width() // 2, y_t))
        t_d = font_bandeau.render(config.TXT_BOUTON_SUPPRIMER, True, config.COULEUR_TEXTE_D)
        screen.blit(t_d, (WIDTH - 80 - t_d.get_width(), y_t))
    pygame.display.flip()
    clock.tick(30)

pygame.quit()

