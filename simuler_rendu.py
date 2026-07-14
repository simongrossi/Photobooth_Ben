#!/usr/bin/env python3
"""simuler_rendu.py — simulation locale des rendus 10x15 + strip (sans matériel).

Place 3 photos de test nommées photo1.jpg, photo2.jpg et photo3.jpg à la
racine du projet, puis lance :

    python3 simuler_rendu.py

Génère le montage 10x15, le strip simple, puis une version « double strip »
côte à côte au format d'impression (fichier *_DOUBLE_IMPRESSION.jpg).
Pratique pour calibrer les templates/géométries sans caméra ni imprimante.
"""
import os
import sys

from PIL import Image

from core.montage import MontageGenerator10x15, MontageGeneratorStrip

# Photos sources attendues à la racine du projet
PHOTOS_TEST = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
ID_SESSION_TEST = "simulation"


def verifier_images_sources() -> bool:
    """Vérifie que les 3 photos de test sont présentes à la racine."""
    return all(os.path.isfile(p) for p in PHOTOS_TEST)


def simuler_montages():
    if not verifier_images_sources():
        print("\n⚠️ Erreur : Place d'abord 3 photos de test nommées photo1.jpg, photo2.jpg et photo3.jpg dans ce dossier.")
        sys.exit(1)

    print("\n🚀 Lancement de la génération des rendus miroirs (avec duplication du Strip)...\n")

    # ----------------------------------------------------
    # GENERATION DU MODE 10X15
    # ----------------------------------------------------
    try:
        print("📸 Simulation du rendu 10x15...")
        chemin_10x15 = MontageGenerator10x15.final(PHOTOS_TEST, ID_SESSION_TEST)
        print(f"➡️  [OK] Rendu 10x15 généré ici : {chemin_10x15}")
    except Exception as e:
        print(f"💥 Échec de la génération 10x15 : {e}")

    print("-" * 50)

    # ----------------------------------------------------
    # GENERATION DU MODE STRIP (DUPLIQUÉ CÔTE À CÔTE)
    # ----------------------------------------------------
    try:
        print("🎞️  Simulation du rendu Strip unique...")
        # 1. On génère d'abord le strip simple via ton module
        chemin_strip_unique = MontageGeneratorStrip.final(PHOTOS_TEST, ID_SESSION_TEST)
        
        print("👯 Duplication des bandelettes sur format 10x15 pour impression...")
        # 2. On ouvre le strip unique qui vient d'être créé
        strip_img = Image.open(chemin_strip_unique)
        
        # 3. On crée une image blanche au format d'impression 10x15 (1800 x 1200 pixels)
        # Note : Si tes strips sont verticaux (600x1800), on crée un canevas vertical (1200x1800)
        largeur_strip, hauteur_strip = strip_img.size
        
        # Création du canevas pour accueillir les 2 bandes
        canevas_impression = Image.new("RGB", (largeur_strip * 2, hauteur_strip), "white")
        
        # 4. On colle la bandelette à gauche (X=0, Y=0) et à droite (X=largeur_strip, Y=0)
        canevas_impression.paste(strip_img, (0, 0))
        canevas_impression.paste(strip_img, (largeur_strip, 0))
        
        # 5. On écrase le fichier pour avoir le rendu prêt à imprimer
        chemin_strip_double = chemin_strip_unique.replace(".jpg", "_DOUBLE_IMPRESSION.jpg")
        canevas_impression.save(chemin_strip_double, "JPEG", quality=95)
        
        print(f"➡️  [OK] Double Strip généré ici : {chemin_strip_double}")
        
    except Exception as e:
        print(f"💥 Échec de la génération Strip : {e}")

    print("\n🎉 Simulation terminée ! Vérifie le fichier _DOUBLE_IMPRESSION.jpg.")

if __name__ == "__main__":
    simuler_montages()
