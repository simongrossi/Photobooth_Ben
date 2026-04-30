import os
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION DES CHEMINS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MIRE_CLEAN = os.path.join(BASE_DIR, "assets", "backgrounds", "mire_test_cut_DNP.jpg")
TEST_DIR = os.path.join(BASE_DIR, "test")
OUTPUT_PATH = os.path.join(TEST_DIR, "RESULTAT_TEST_CUT_DNP.jpg")

# --- VARIABLES D'AJUSTEMENT (Pixels) ---
# Grâce à la modification du paste plus bas, ces variables 
# pilotent désormais le bord indiqué par l'étiquette sur la photo.
TOP_MARGIN    = 18
BOTTOM_MARGIN = 12
LEFT_MARGIN   = 3
RIGHT_MARGIN  = 17

# --- REGLAGES DU TEXTE ---
TEXT_CENTRE_X = 600  
TEXT_CENTRE_Y_OFFSET = -2
TAILLE_POLICE_CENTRE = 80
TAILLE_POLICE_MARGINS = 40 

TEXT_LEFT_X_OFFSET  = 50  
TEXT_RIGHT_X_OFFSET = 50  

TEXT_TOP_X_OFFSET = 30       
TEXT_TOP_Y_OFFSET = -30       
TEXT_BOTTOM_X_OFFSET = 0    
TEXT_BOTTOM_Y_OFFSET = 40 

MONTAGE_10X15_SIZE = (1800, 1200)

def draw_rotated_text(image, position, text, font, fill, rotation=180):
    """Dessine un texte pivoté avec une marge de sécurité"""
    bbox = font.getbbox(text)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    padding = 40
    txt_layer = Image.new('RGBA', (tw + padding, th + padding), (0,0,0,0))
    d = ImageDraw.Draw(txt_layer)
    d.text((padding // 2, padding // 2), text, font=font, fill=fill)
    rotated_txt = txt_layer.rotate(rotation, expand=True)
    image.paste(rotated_txt, (int(position[0]), int(position[1])), rotated_txt)

def generer_test_dnp_cut():
    if not os.path.exists(MIRE_CLEAN):
        print(f"ERREUR : Fichier {MIRE_CLEAN} introuvable.")
        return

    strip = Image.open(MIRE_CLEAN).convert("RGB")
    
    # Calcul de la zone utile (le bloc interne)
    utile_w = MONTAGE_10X15_SIZE[0] - LEFT_MARGIN - RIGHT_MARGIN
    utile_h = MONTAGE_10X15_SIZE[1] - TOP_MARGIN - BOTTOM_MARGIN
    
    bloc_photos = Image.new("RGB", (utile_w, utile_h), "white")
    h_par_bande = utile_h // 2
    
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
        font_centre = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", TAILLE_POLICE_CENTRE)
        font_margins = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", TAILLE_POLICE_MARGINS)
    except Exception:
        font_large = ImageFont.load_default()
        font_centre = ImageFont.load_default()
        font_margins = ImageFont.load_default()

    for i in range(2):
        strip_resized = strip.resize((utile_w, h_par_bande), Image.Resampling.LANCZOS)
        strip_rgba = strip_resized.convert("RGBA")
        
        # 1. TEXTE BANDE
        draw_rotated_text(strip_rgba, (utile_w // 2 - 200, h_par_bande // 2 - 40), f"BANDE {i + 1}", font_large, "black")
        
        # 2. MARGES LATÉRALES (Inversion RIGHT à gauche du fichier, LEFT à droite du fichier)
        draw_rotated_text(strip_rgba, (TEXT_RIGHT_X_OFFSET, h_par_bande // 2), f"RIGHT: {RIGHT_MARGIN}px", font_margins, "blue")
        
        txt_left = f"LEFT: {LEFT_MARGIN}px"
        tw_l = font_margins.getbbox(txt_left)[2] - font_margins.getbbox(txt_left)[0]
        draw_rotated_text(strip_rgba, (utile_w - tw_l - TEXT_LEFT_X_OFFSET, h_par_bande // 2), txt_left, font_margins, "blue")
        
        # 3. MARGES HAUT/BAS (Inversion demandée pour sortie imprimante)
        if i == 0: # BANDE DU HAUT du fichier (BOTTOM)
            txt_label = f"BOTTOM : {BOTTOM_MARGIN}px (Sortie imprimante)"
            tw_b = font_margins.getbbox(txt_label)[2] - font_margins.getbbox(txt_label)[0]
            pos_x = (utile_w // 2 - tw_b // 2) + TEXT_BOTTOM_X_OFFSET
            draw_rotated_text(strip_rgba, (pos_x, 20 + TEXT_BOTTOM_Y_OFFSET), txt_label, font_margins, "green")
        else: # BANDE DU BAS du fichier (TOP)
            txt_label = f"TOP: {TOP_MARGIN}px"
            tw_t = font_margins.getbbox(txt_label)[2] - font_margins.getbbox(txt_label)[0]
            pos_x = (utile_w // 2 - tw_t // 2) + TEXT_TOP_X_OFFSET
            draw_rotated_text(strip_rgba, (pos_x, h_par_bande - 60 + TEXT_TOP_Y_OFFSET), txt_label, font_margins, "green")
        
        bloc_photos.paste(strip_rgba.convert("RGB"), (0, i * h_par_bande))

    # --- CENTRE ---
    temp_bloc = bloc_photos.convert("RGBA")
    txt_c = "------ CENTRE / COUPE ---"
    th_c = font_centre.getbbox(txt_c)[3] - font_centre.getbbox(txt_c)[1]
    pos_y_centre = h_par_bande - (th_c // 2) + TEXT_CENTRE_Y_OFFSET
    draw_rotated_text(temp_bloc, (TEXT_CENTRE_X, pos_y_centre), txt_c, font_centre, (148, 0, 211))
    bloc_photos = temp_bloc.convert("RGB")

    # --- FINALISATION (LOGIQUE D'INVERSION DES MARGES) ---
    canvas_final = Image.new("RGB", MONTAGE_10X15_SIZE, "white")
    
    # On paste le bloc en utilisant RIGHT_MARGIN pour le X et BOTTOM_MARGIN pour le Y
    # car ce qui est à gauche/haut sur l'écran sera à droite/bas sur la sortie physique.
    canvas_final.paste(bloc_photos, (RIGHT_MARGIN, BOTTOM_MARGIN))
    
    canvas_final.save(OUTPUT_PATH, "JPEG", quality=100, subsampling=0)
    
    print("\n[OK] Mire générée avec logique de variables synchronisée.")
    print("Les variables TOP/BOTTOM/LEFT/RIGHT pilotent maintenant leurs bords respectifs sur la photo.")

if __name__ == "__main__":
    generer_test_dnp_cut()