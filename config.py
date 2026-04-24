import os
# Import tolérant : permet à status.py (diagnostic) de charger config.py sans pygame
try:
    import pygame
except ImportError:
    pygame = None

# ==========================================
# 1. INITIALISATION SYSTÈME & DOSSIERS
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Dossiers Photos (Stockage) ---
PATH_DATA       = os.path.join(BASE_DIR, "data")
PATH_RAW        = os.path.join(PATH_DATA, "raw")
PATH_TEMP       = os.path.join(PATH_DATA, "temp")
PATH_PRINT      = os.path.join(PATH_DATA, "print")
PATH_PRINT_10X15 = os.path.join(PATH_PRINT, "print_10x15")
PATH_PRINT_STRIP = os.path.join(PATH_PRINT, "print_strip")
PATH_SKIPPED    = os.path.join(PATH_DATA, "skipped")
# Ajout des sous-dossiers pour le tri du skipped
PATH_SKIPPED_RETAKE  = os.path.join(PATH_SKIPPED, "skipped_retake")
PATH_SKIPPED_DELETED = os.path.join(PATH_SKIPPED, "skipped_deleted")

# --- Dossiers Racines des Assets ---
PATH_ASSETS     = os.path.join(BASE_DIR, "assets")

# --- Sous-dossiers spécifiques ---
PATH_INTERFACE  = os.path.join(PATH_ASSETS, "interface")
PATH_FONDS      = os.path.join(PATH_ASSETS, "backgrounds")
PATH_OVERLAYS   = os.path.join(PATH_ASSETS, "overlays")
PATH_SOUNDS     = os.path.join(PATH_ASSETS, "sounds")

# --- Fichiers sons (chargés si présents, sinon ignorés silencieusement) ---
SON_BEEP        = os.path.join(PATH_SOUNDS, "beep.wav")      # Tick décompte (sauf dernière seconde)
SON_BEEP_FINAL  = os.path.join(PATH_SOUNDS, "beep_final.wav") # Tick dernière seconde (tension) - fallback sur SON_BEEP si absent
SON_SHUTTER     = os.path.join(PATH_SOUNDS, "shutter.wav")   # Déclenchement photo
SON_SUCCESS     = os.path.join(PATH_SOUNDS, "success.wav")   # Impression lancée


# --- Chemins des fichiers d'interface (L'ÉCRAN) ---
PATH_IMG_10X15  = os.path.join(PATH_INTERFACE, "img_10x15.png")
PATH_IMG_STRIP  = os.path.join(PATH_INTERFACE, "img_strip.png")
FILE_BG_ACCUEIL = os.path.join(PATH_INTERFACE, "background.jpg")

# --- Chemins des fichiers de montage (L'IMPRESSION) ---
BG_10X15_FILE   = os.path.join(PATH_FONDS, "10x15_background.jpg")
BG_STRIPS_FILE  = os.path.join(PATH_FONDS, "strips_background.jpg")
OVERLAY_10X15   = os.path.join(PATH_OVERLAYS, "10x15_overlay.png")
OVERLAY_STRIPS  = os.path.join(PATH_OVERLAYS, "strips_overlay.png")

# --- RÉGLAGES DES NOMS DE FICHIERS ---
PREFIXE_RAW           = "photo"
PREFIXE_PRINT_10X15   = "montage_10x15" 
PREFIXE_PRINT_STRIP   = "montage_strip"
PREFIXE_RETAKE        = "retake"
PREFIXE_DELETED       = "deleted"

# --- FORMAT DU TIMESTAMP (DATE/HEURE) ---
# %Y: Année, %m: Mois, %d: Jour, %H: Heure, %M: Minute, %S: Seconde
# Exemple actuel : 2026-04-14_21h45_30
FORMAT_TIMESTAMP = "%Y-%m-%d_%Hh%M_%S"


# ==========================================
# 2. RÉGLAGES ÉCRAN & INTERFACE
# ==========================================
WIDTH, HEIGHT = 1280, 800       # Résolution de la fenêtre Pygame
LIVE_W, LIVE_H = 800, 600       # Taille du flux vidéo en direct (Preview)

# Mode kiosque : pygame passe en FULLSCREEN + NOFRAME si la variable
# d'environnement PHOTOBOOTH_KIOSK=1 est posée (par deploy/kiosk.sh en prod).
# En dev (env vide), reste en fenêtré standard pour faciliter le debug.
KIOSK_FULLSCREEN = os.environ.get("PHOTOBOOTH_KIOSK", "0") == "1"


MASQUE = 130   # Transparance des bande latérale noire si ratio image modifié (valeur : 0 invisble à 255 opaque)



TEMPS_DECOMPTE = 1

# --- Contrôles Clavier ---
# Les K_* de pygame pour les lettres minuscules correspondent à leur code ASCII.
# Fallback ord() permet à config.py de se charger sans pygame (pour status.py).
TOUCHE_GAUCHE = pygame.K_g if pygame else ord('g')
TOUCHE_MILIEU = pygame.K_m if pygame else ord('m')
TOUCHE_DROITE = pygame.K_d if pygame else ord('d')

# --- Délais et Sécurité ---
DELAI_SECURITE = 2.0  # Temps d'attente (anti-rebond) entre deux pressions


# --- Arduino Nano (3 boutons-poussoirs à LED intégrée) ---
# Voir docs/ARDUINO.md pour le câblage, le flash du firmware et le protocole.
# Désactivé si `ARDUINO_ENABLED = False` ou si pyserial n'est pas installé :
# le photobooth reste 100 % utilisable au clavier (touches G/M/D).
ARDUINO_ENABLED   = True
# Port série — adapter selon l'OS :
#   Linux/Raspberry : "/dev/ttyUSB0" (CH340) ou "/dev/ttyACM0" (FTDI/ATmega16U2)
#   macOS           : "/dev/tty.usbserial-XXXX" ou "/dev/tty.usbmodemXXXX"
#   Windows         : "COM3", "COM4", ...
# Mettre à None pour désactiver sans toucher à ARDUINO_ENABLED.
ARDUINO_PORT      = "/dev/ttyUSB0"
ARDUINO_BAUDRATE  = 115200



# ----DESIGN DU BANDEAU HORIZONTALE DE NAVIGATION EN BAS----
BANDEAU_HAUTEUR = 60      # Hauteur en pixels 60 par défaut
BANDEAU_ALPHA   = 150     # Transparence (0 à 255)
BANDEAU_COULEUR = (0, 0, 0) # Couleur du fond (Noir par défaut)


# Décalage vertical des images de prévisualisation (pixels)
# Une valeur positive descend l'image, une valeur négative la monte
DECALAGE_Y_PREVISU_10X15 = -30
DECALAGE_Y_PREVISU_STRIPS = -20
DECALAGE_Y_MONTAGE_FINAL_STRIP = -30  # Ajuste cette valeur (ex: -50 pour monter, 50 pour descendre)



# ==========================================
# 3. CHARTE GRAPHIQUE & POLICES
# ==========================================
# --- Couleurs (R, G, B) ---
WHITE    = (255, 255, 255)
BLACK    = (0, 0, 0)
GOLD     = (255, 215, 0)
GREEN    = (0, 255, 0)
RED      = (255, 0, 0)
BLUE     = (154, 222, 245)
GREY_OFF = (130, 130, 130)
DARK_SHADOW = (20, 20, 20)

COULEUR_FLASH      = WHITE
COULEUR_SOURIEZ    = GOLD
COULEUR_DECOMPTE   = GOLD
COULEUR_TEXTE_REPOS = (255, 255, 255)  # Blanc (par exemple) quand rien n'est sélectionné
ALPHA_TEXTE_REPOS = 100  # Transparence texte repos Entre 0 (invisible) et 255 (opaque). 100 est un bon compromis.
COULEUR_TEXTE_OFF = (207, 136, 6)   
COULEUR_TEXTE_ON  = (242, 183, 5)  

# Couleurs des textes de navigation
COULEUR_TEXTE_G = (255, 255, 255) # Blanc (Reprendre / Accueil)
COULEUR_TEXTE_M = (0, 255, 0)     # Vert (Valider / Imprimer)
COULEUR_TEXTE_D = (255, 0, 0)     # Rouge (Accueil / Supprimer)


# --- Polices ---
POLICE_FICHIER  = os.path.join(BASE_DIR, "assets/fonts/WesternBangBang-Regular.ttf")
TAILLE_DECOMPTE      = 300  # Chiffre 3, 2, 1...
TAILLE_TITRE_ACCUEIL = 180  # Le nom du Photobooth ou gros messages
TAILLE_TEXTE_BOUTON  = 60   # "GRAND FORMAT" / "BANDELETTES" (ecran choix du mode)
TAILLE_TEXTE_BANDEAU = 40

# --- Effets de Clignotement (Pulse) ---
PULSE_MIN, PULSE_MAX, PULSE_VITESSE = 150, 255, 5      # Pulse rapide (sélection)
PULSE_LENT_MIN, PULSE_LENT_MAX, PULSE_LENT_VITESSE = 130, 230, 2 # Pulse lent (respiration)

# ==========================================
# 4. RÉGLAGES DU MENU ACCUEIL
# ==========================================
LARGEUR_ICONE_10X15 = 400 
LARGEUR_ICONE_STRIP = 200
OFFSET_DROITE_10X15 = 50   # Décale le 10x15 vers la droite
OFFSET_DROITE_STRIP = 110   # Décale le Strip vers la droite
ZOOM_FACTOR   = 1.15  # +15% de taille quand sélectionné
MARGE_ACCUEIL = 200   # Espace entre les deux icônes

# ==========================================
# 5. CONFIGURATION DES MONTAGES (IMPRESSION)
# ==========================================

# --- Mode STRIPS (Bandelettes) ---
STRIP_MARGE_HAUT     = 40    # Espace tout en haut de la bande
STRIP_MARGE_LATERALE = 30   # Espace vide à gauche et à droite de chaque photo
STRIP_ESPACE_PHOTOS  = 40    # Espace entre les photos

# --- REGLAGES DYNAMIQUES ---
# Ratio de la photo (Hauteur / Largeur)
# 0.66 pour le format standard 3:2 (Canon natif, rectangulaire)
# 0.80 pour le format 5:4 (Un peu plus carré)
# 1.00 pour le format 1:1 (Parfaitement carré)
STRIP_PHOTO_RATIO = 0.80


# --- Mode 10x15 (Photo Unique) ---
PHOTO_10x15_LARGEUR  = 1600
PHOTO_10x15_HAUTEUR  = 1000
PHOTO_10x15_OFFSET_X = -100 # Décalage gauche/droite
PHOTO_10x15_OFFSET_Y = -50  # Décalage haut/bas

# --- Dimensions finales d'impression (Sprint 4.8) ---
# 10x15 à 300 DPI : 6" × 4" = 1800 × 1200 px
MONTAGE_10X15_SIZE = (1800, 1200)
# Bandelette à 300 DPI : 2" × 6" = 600 × 1800 px
MONTAGE_STRIP_SIZE = (600, 1800)
# Rotation appliquée au fond + overlay en mode strip (imprimante orientée tête-bêche)
STRIP_ROTATION_DEGREES = 180

# --- Dimensions de preview écran (mode 10x15) ---
# Canvas + zone photo + offset = cadre blanc fin autour de la photo
MONTAGE_10X15_PREVIEW_SIZE         = (900, 600)
MONTAGE_10X15_PREVIEW_PHOTO_FIT    = (840, 540)
MONTAGE_10X15_PREVIEW_PHOTO_OFFSET = (30, 30)
MONTAGE_10X15_PREVIEW_QUALITY      = 80

# --- Dimensions finales de montage (mode 10x15) ---
# Photo + offset dans le canvas 1800×1200
MONTAGE_10X15_FINAL_PHOTO_FIT      = (1640, 1040)
MONTAGE_10X15_FINAL_PHOTO_OFFSET   = (80, 80)
MONTAGE_10X15_FINAL_QUALITY        = 98

# --- Dimensions de preview écran (mode strip) ---
STRIP_PREVIEW_PHOTO_LARGEUR = 520
STRIP_PREVIEW_ESPACEMENT    = 40
STRIP_PREVIEW_MARGE_HB      = 20     # marge haut/bas de la bande
STRIP_PREVIEW_CANVAS_LARGEUR = 600
STRIP_PREVIEW_THUMBNAIL_MAX = (400, 800)
STRIP_PREVIEW_QUALITY       = 90

# --- Qualité JPEG des montages finaux strip ---
STRIP_FINAL_QUALITY = 98

# --- Couleur de fond des écrans transitoires (loader, spinner, attente) ---
COULEUR_FOND_LOADER = (10, 10, 18)

# ==========================================
# 6. RÉGLAGES PRÉVISUALISATION (ÉCRAN)
# ==========================================
PREVISU_L = 800
PREVISU_H = int(PREVISU_L / 1.5)  # Ne pas modifier /calcule la hauteur pour garder un ratio 3:2
FIN_H     = 600 # Hauteur du montage final sur l'écran de fin

PREVISU_H_STRIP = 600



# ==========================================
# 7. TEXTE MODIFICATION
# ==========================================
# Page Accueil => Textes du bandeau noir en bas
BANDEAU_ACCUEIL = "<-- Choisissez le format pour commencer -->"
BANDEAU_10X15   = "Format 10x15 . . . Bouton vert pour démarrer"
BANDEAU_STRIP   = "Format bandelettes . . . Bouton vert pour démarrer"

# Textes sous les icônes
MODE_10x15     = "Grand Format"
MODE_STRIP      = "Bandelettes"


# --- ÉCRAN DE VALIDATION (Juste après la prise de vue) ---
# Mode 10x15
TXT_VALID_REPRENDRE_10X15 = "Reprendre la photo"
TXT_VALID_VALIDER_10X15   = "IMPRIMER"
TXT_VALID_ACCUEIL_10X15   = "Accueil"
# Mode Bandelettes (Strips)
TXT_VALID_REPRENDRE_STRIP = "Reprendre la Photo"
TXT_VALID_VALIDER_STRIP   = "Valider la photo"
TXT_VALID_ACCUEIL_STRIP   = "Accueil"

# Texte compteur photo en mode strip (Photo 1/3 etc)
TEXTE_PHOTO_COUNT = "PHOTO"


# Textes de l'écran de FIN (Validation finale / Impression)
TXT_BOUTON_REPRENDRE   = "Recommencer"
TXT_BOUTON_ACCUEIL     = "Accueil"
TXT_BOUTON_IMPRIMER    = "IMPRIMER"
TXT_BOUTON_SUPPRIMER   = "Accueil"

# --- Messages écran splash / erreur / préparation ---
TXT_SPLASH_CAMERA       = "Connexion à l'appareil photo..."
TXT_SPLASH_CAMERA_OK    = "Appareil photo connecté !"
TXT_SPLASH_CAMERA_FAIL  = "Appareil photo non détecté - mode dégradé"
TXT_PREPARATION_IMP     = "Préparation de votre impression..."
TXT_ERREUR_CAPTURE      = "Erreur de capture - réessayez"
TXT_ERREUR_IMPRIMANTE   = "Imprimante indisponible"
TXT_CONFIRM_ABANDON_1   = "Abandonner votre session ?"
TXT_CONFIRM_ABANDON_2   = "Appuyez encore sur le bouton rouge pour confirmer"

DUREE_FLASH_BLANC  = 0.08  # Secondes de flash blanc pur avant la capture
DUREE_ECRAN_ERREUR = 4.0   # Timeout auto des écrans d'erreur (secondes)
DUREE_CONFIRM_ABANDON = 3.0  # Fenêtre de confirmation abandon (secondes)
TIMEOUT_SPLASH_CAMERA = 10.0  # Timeout max splash connexion caméra (secondes)

# --- Filigrane "photos restantes" en mode strip ---
# Grand chiffre semi-transparent en fond pendant le décompte : indique combien
# de photos restent à prendre (3 → 2 → 1). Utile aux invités pour situer leur
# position dans la bandelette. Désactivable.
STRIP_FILIGRANE_ENABLED = True
STRIP_FILIGRANE_ALPHA   = 50    # Transparence 0–255 (50 = très discret)
STRIP_FILIGRANE_TAILLE  = 600   # Taille de la police (gros caractère fond)

# --- Mode burst strip : auto-validation entre photos en mode bandelettes ---
# Si activé, les photos 1 et 2 d'un strip s'auto-valident après STRIP_BURST_DELAI_S
# secondes d'aperçu (pas besoin d'appuyer sur valider entre chaque). La 3e photo reste
# validable manuellement car elle envoie à l'écran FIN.
STRIP_MODE_BURST     = False  # False = comportement historique (validation manuelle)
STRIP_BURST_DELAI_S  = 2.5    # durée d'aperçu avant auto-advance (secondes)
TXT_BURST_COUNTDOWN  = "Photo suivante dans"

# --- Monitoring espace disque continu (Sprint 5.6) ---
SEUIL_DISQUE_CRITIQUE_MB   = 500    # alerte si < 500 Mo libres pendant un événement
INTERVALLE_CHECK_DISQUE_S  = 30.0   # fréquence de check (en secondes) pendant l'accueil

# --- Monitoring température CPU (Raspberry Pi) ---
# Lit /sys/class/thermal/thermal_zone0/temp (standard Pi / Linux). Sur
# macOS/Windows ou fichier absent, le monitor est inerte silencieusement.
# Le Pi throttle à ~80 °C ; 75 °C est un bon signal précoce à l'utilisateur.
SEUIL_TEMP_CRITIQUE_C      = 75.0
INTERVALLE_CHECK_TEMP_S    = 30.0
TEMP_PATH                  = "/sys/class/thermal/thermal_zone0/temp"

# --- Slideshow d'attente sur l'accueil (Sprint 6.2) ---
# Après N secondes sans activité sur l'accueil, les montages passés défilent en plein écran
# pour attirer les invités.
DUREE_IDLE_SLIDESHOW      = 30.0   # Secondes d'inactivité avant démarrage
DUREE_PAR_IMAGE_SLIDESHOW = 3.5    # Durée d'affichage de chaque image
NB_MAX_IMAGES_SLIDESHOW   = 40     # Plus récentes uniquement, pour éviter de scanner trop
TXT_SLIDESHOW_INVITATION  = "Approchez pour commencer !"



# --- Watermark événement sur montages finaux ---
# Petit texte discret ajouté en bas à droite des impressions (10x15 et strip).
# Désactivé par défaut : laisser à False si pas d'événement ciblé.
# Note strip : la bande est pré-rotée 180° pour l'imprimante tête-bêche,
# donc le "bas-droite" du canvas = "haut-gauche" de l'impression. Ajuster
# WATERMARK_POSITION_STRIP si besoin (voir docs/CONFIG.md).
WATERMARK_ENABLED          = False
WATERMARK_TEXT             = "Événement — 20/04/2026"
WATERMARK_COULEUR          = (255, 255, 255)   # Blanc
WATERMARK_ALPHA            = 180               # 0–255 (180 = lisible mais discret)
WATERMARK_TAILLE_10X15     = 28
WATERMARK_TAILLE_STRIP     = 20
WATERMARK_POSITION_10X15   = "bottom-right"    # "bottom-right" / "bottom-left" / "bottom-center"
WATERMARK_POSITION_STRIP   = "bottom-right"
WATERMARK_MARGE_PX         = 20                # Distance en px depuis le bord


# --- Grain de pellicule (film grain) sur montages finaux ---
# Bruit gaussien superposé à l'image finale pour un effet argentique discret.
# Ne s'applique qu'au rendu FINAL (pas aux previews écran) : le grain n'est
# pertinent qu'à la résolution d'impression, et économise le CPU en kiosque.
# Désactivé par défaut — à activer pour les événements à ambiance rétro.
GRAIN_ENABLED      = False
GRAIN_INTENSITE    = 8       # Force du mélange en % (0–100). 5–15 reste subtil.
GRAIN_SIGMA        = 30.0    # Écart-type du bruit gaussien (bas = uniforme, haut = tacheté)


# ==========================================
# 8. CONFIGURATION IMPRESSION
# ==========================================
ACTIVER_IMPRESSION = True          # Permet de tester sans gâcher de papier
NOM_IMPRIMANTE_10X15 = "DNP_10x15"
NOM_IMPRIMANTE_STRIP = "DNP_STRIP"
TEMPS_ATTENTE_IMP    = 20  # Secondes d'affichage de la roue avant retour accueil



# --- CONFIGURATION ANIMATION ROUE DE CHARGEMENT ---
ANIM_COULEUR_TETE  = (255, 0, 150) # Magenta
ANIM_COULEUR_QUEUE = (0, 200, 255) # Cyan
ANIM_TAILLE_ROUE   = 100           

# Physique
ANIM_V_BASE        = 4.0           
ANIM_V_MAX_ADD     = 8             
ANIM_FREQ          = 1.5           

# Structure
ANIM_NB_POINTS     = 120           # Nombre de points composant la roue (baissé de 300 : overkill visuel pour le CPU Pi)
ANIM_RAYON_POINT   = 28
ANIM_V_ELASTIQUE   = 5.0

# Framerate de rafraîchissement du spinner (écrans loader / attente impression).
# Distinct de FPS (boucle principale) pour réduire la charge CPU sur Pi.
SPINNER_FPS        = 30

FPS = 60


# ==========================================
# 9. VALIDATION AU CHARGEMENT (Sprint 4.7)
# ==========================================
# On vérifie au premier import que la config est cohérente. Un AssertionError
# au démarrage est bien plus clair qu'un bug visuel à mi-événement.
def _valider_config():
    # Dimensions
    assert WIDTH > 0 and HEIGHT > 0, f"Dimensions écran invalides : {WIDTH}x{HEIGHT}"
    assert LIVE_W > 0 and LIVE_H > 0, f"Dimensions live invalides : {LIVE_W}x{LIVE_H}"
    assert PHOTO_10x15_LARGEUR > 0 and PHOTO_10x15_HAUTEUR > 0

    # Timings
    assert TEMPS_DECOMPTE >= 1, f"TEMPS_DECOMPTE doit être >= 1 (actuel : {TEMPS_DECOMPTE})"
    assert DELAI_SECURITE >= 0.5, f"DELAI_SECURITE trop court : {DELAI_SECURITE}"
    assert FPS > 0, f"FPS invalide : {FPS}"
    assert SPINNER_FPS > 0, f"SPINNER_FPS invalide : {SPINNER_FPS}"
    assert ANIM_NB_POINTS >= 1, f"ANIM_NB_POINTS invalide : {ANIM_NB_POINTS}"
    assert TEMPS_ATTENTE_IMP > 0, f"TEMPS_ATTENTE_IMP invalide : {TEMPS_ATTENTE_IMP}"

    # Alpha channels
    assert 0 <= MASQUE <= 255, f"MASQUE hors [0,255] : {MASQUE}"
    assert 0 <= BANDEAU_ALPHA <= 255, f"BANDEAU_ALPHA hors [0,255] : {BANDEAU_ALPHA}"
    assert 0 <= ALPHA_TEXTE_REPOS <= 255

    # Sprint 2 params
    assert DUREE_FLASH_BLANC >= 0, f"DUREE_FLASH_BLANC négatif : {DUREE_FLASH_BLANC}"
    assert DUREE_ECRAN_ERREUR > 0, f"DUREE_ECRAN_ERREUR invalide : {DUREE_ECRAN_ERREUR}"
    assert DUREE_CONFIRM_ABANDON > 0
    assert TIMEOUT_SPLASH_CAMERA > 0

    # Sprint 6.2 slideshow
    assert DUREE_IDLE_SLIDESHOW > 0, f"DUREE_IDLE_SLIDESHOW invalide : {DUREE_IDLE_SLIDESHOW}"
    assert DUREE_PAR_IMAGE_SLIDESHOW > 0
    assert NB_MAX_IMAGES_SLIDESHOW > 0

    # Monitoring température
    assert SEUIL_TEMP_CRITIQUE_C > 0, f"SEUIL_TEMP_CRITIQUE_C invalide : {SEUIL_TEMP_CRITIQUE_C}"
    assert INTERVALLE_CHECK_TEMP_S > 0

    # Grain de pellicule
    assert 0 <= GRAIN_INTENSITE <= 100, f"GRAIN_INTENSITE hors [0,100] : {GRAIN_INTENSITE}"
    assert GRAIN_SIGMA > 0, f"GRAIN_SIGMA invalide : {GRAIN_SIGMA}"

    # Strip dimensions cohérentes
    assert 0.3 <= STRIP_PHOTO_RATIO <= 1.2, f"STRIP_PHOTO_RATIO suspect : {STRIP_PHOTO_RATIO}"
    assert STRIP_MARGE_HAUT >= 0 and STRIP_MARGE_LATERALE >= 0 and STRIP_ESPACE_PHOTOS >= 0

    # Tailles de montage
    assert MONTAGE_10X15_SIZE[0] > 0 and MONTAGE_10X15_SIZE[1] > 0
    assert MONTAGE_STRIP_SIZE[0] > 0 and MONTAGE_STRIP_SIZE[1] > 0

    # Noms d'imprimantes
    assert NOM_IMPRIMANTE_10X15 and isinstance(NOM_IMPRIMANTE_10X15, str)
    assert NOM_IMPRIMANTE_STRIP and isinstance(NOM_IMPRIMANTE_STRIP, str)


_valider_config()