import os
import pygame 

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


MASQUE = 130   # Transparance des bande latérale noire si ratio image modifié (valeur : 0 invisble à 255 opaque)



TEMPS_DECOMPTE = 1

# --- Contrôles Clavier ---
TOUCHE_GAUCHE = pygame.K_g 
TOUCHE_MILIEU = pygame.K_m 
TOUCHE_DROITE = pygame.K_d 

# --- Délais et Sécurité ---
DELAI_SECURITE = 2.0  # Temps d'attente (anti-rebond) entre deux pressions



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
ANIM_NB_POINTS     = 300           
ANIM_RAYON_POINT   = 28            
ANIM_V_ELASTIQUE   = 5.0

FPS = 60