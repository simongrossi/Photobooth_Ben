"""ui — contexte pygame partagé + helpers de rendu.

Re-exporte tout depuis helpers.py pour permettre `from ui import X` dans le code
appelant (sans avoir à connaître la structure interne).
"""
from ui.helpers import (
    UIContext, AccueilAssets, setup_sounds, jouer_son,
    draw_text_shadow_soft, inserer_background, obtenir_couleur_pulse,
    get_pygame_surf, get_pygame_surf_cropped,
    LoaderAnimation,
    afficher_message_plein_ecran, executer_avec_spinner,
    ecran_erreur, ecran_attente_impression,
    splash_connexion_camera,
)

__all__ = [
    "UIContext", "AccueilAssets", "setup_sounds", "jouer_son",
    "draw_text_shadow_soft", "inserer_background", "obtenir_couleur_pulse",
    "get_pygame_surf", "get_pygame_surf_cropped",
    "LoaderAnimation",
    "afficher_message_plein_ecran", "executer_avec_spinner",
    "ecran_erreur", "ecran_attente_impression",
    "splash_connexion_camera",
]
