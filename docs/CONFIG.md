# Configuration — `config.py`

Référence des ~100 constantes exposées par [`config.py`](../config.py).
Regroupées par section (les numéros correspondent aux blocs `# =====` du fichier).

Pour la structure du projet voir [ARCHITECTURE.md](ARCHITECTURE.md).
Pour les modifier en production voir [RUNBOOK.md](RUNBOOK.md).

---

## Principe

- **Toutes les constantes du projet sont dans `config.py`**, pas de `.env` ni
  de fichier YAML. C'est un module Python pur, donc on peut y mettre des
  calculs et valider au chargement (voir `_valider_config()` en bas de fichier).
- L'import est **tolérant** : `config.py` se charge sans `pygame` (pour
  `status.py`), grâce au `try/except ImportError` en haut.
- La validation au chargement lève `AssertionError` en cas d'incohérence —
  bien plus clair qu'un bug visuel à mi-événement.

---

## 1. Chemins & fichiers

### Dossiers de données (générés à l'exécution)

| Constante | Valeur | Usage |
|---|---|---|
| `BASE_DIR` | auto | Racine du projet |
| `PATH_DATA` | `data/` | Dossier racine photos/logs |
| `PATH_RAW` | `data/raw/` | Photos brutes gphoto2 |
| `PATH_TEMP` | `data/temp/` | Montages intermédiaires (purgés) |
| `PATH_PRINT` | `data/print/` | Montages finaux envoyés à l'imprimante |
| `PATH_PRINT_10X15` | `data/print/print_10x15/` | Archive 10×15 |
| `PATH_PRINT_STRIP` | `data/print/print_strip/` | Archive strips |
| `PATH_SKIPPED` | `data/skipped/` | Photos rejetées |
| `PATH_SKIPPED_RETAKE` | `data/skipped/skipped_retake/` | Rejetées via "Reprendre" |
| `PATH_SKIPPED_DELETED` | `data/skipped/skipped_deleted/` | Rejetées via "Supprimer" |

### Dossiers d'assets (fournis, pas générés)

| Constante | Valeur | Usage |
|---|---|---|
| `PATH_ASSETS` | `assets/` | Racine assets |
| `PATH_INTERFACE` | `assets/interface/` | Éléments UI (background, icônes) |
| `PATH_FONDS` | `assets/backgrounds/` | Fonds d'impression |
| `PATH_OVERLAYS` | `assets/overlays/` | Overlays RGBA d'impression |
| `PATH_SOUNDS` | `assets/sounds/` | Sons (optionnel) |

### Fichiers individuels

| Constante | Rôle |
|---|---|
| `SON_BEEP`, `SON_SHUTTER`, `SON_SUCCESS` | WAV pour tick, shutter, impression — absents = silencieux |
| `PATH_IMG_10X15`, `PATH_IMG_STRIP` | Icônes du menu accueil |
| `FILE_BG_ACCUEIL` | Fond de l'accueil |
| `BG_10X15_FILE`, `BG_STRIPS_FILE` | Fonds des impressions |
| `OVERLAY_10X15`, `OVERLAY_STRIPS` | Overlays RGBA |
| `POLICE_FICHIER` | Police WesternBangBang-Regular |

### Préfixes & format timestamp

| Constante | Valeur | Usage |
|---|---|---|
| `PREFIXE_RAW` | `"photo"` | Préfixe photos brutes |
| `PREFIXE_PRINT_10X15` | `"montage_10x15"` | Préfixe montages 10×15 |
| `PREFIXE_PRINT_STRIP` | `"montage_strip"` | Préfixe montages strip |
| `PREFIXE_RETAKE` | `"retake"` | Préfixe archives retake |
| `PREFIXE_DELETED` | `"deleted"` | Préfixe archives deleted |
| `FORMAT_TIMESTAMP` | `%Y-%m-%d_%Hh%M_%S` | Format des suffixes datés |

---

## 2. Écran & interface

| Constante | Défaut | Effet |
|---|---|---|
| `WIDTH, HEIGHT` | `1280, 800` | Résolution de la fenêtre pygame |
| `LIVE_W, LIVE_H` | `800, 600` | Taille du flux vidéo live (preview) |
| `MASQUE` | `130` | Alpha des bandes latérales noires (si ratio modifié). 0 = invisible, 255 = opaque |
| `TEMPS_DECOMPTE` | `1` | Durée d'un tick de décompte (s). `1` = décompte rapide |
| `TOUCHE_GAUCHE/MILIEU/DROITE` | `K_g/K_m/K_d` | Bindings clavier (lettres minuscules) |
| `DELAI_SECURITE` | `2.0` | Anti-rebond entre deux pressions (s) |

### Arduino

| Constante | Défaut | Effet |
|---|---|---|
| `ARDUINO_ENABLED` | `True` | Désactive le contrôleur si `False` |
| `ARDUINO_PORT` | `/dev/ttyUSB0` | Port série (voir [ARDUINO.md](ARDUINO.md) pour autres OS) |
| `ARDUINO_BAUDRATE` | `115200` | Baudrate — doit matcher le firmware |

### Bandeau navigation bas

| Constante | Défaut | Effet |
|---|---|---|
| `BANDEAU_HAUTEUR` | `60` | Hauteur en pixels |
| `BANDEAU_ALPHA` | `150` | Transparence 0–255 |
| `BANDEAU_COULEUR` | `(0, 0, 0)` | Couleur du fond |

### Décalages vertical des previews

| Constante | Défaut | Effet |
|---|---|---|
| `DECALAGE_Y_PREVISU_10X15` | `-30` | Décale preview 10×15 (négatif = vers le haut) |
| `DECALAGE_Y_PREVISU_STRIPS` | `-20` | Idem pour strip |
| `DECALAGE_Y_MONTAGE_FINAL_STRIP` | `-30` | Décale le montage final strip à l'écran |

---

## 3. Charte graphique & polices

### Couleurs de base

`WHITE`, `BLACK`, `GOLD`, `GREEN`, `RED`, `BLUE`, `GREY_OFF`, `DARK_SHADOW`.

### Couleurs thématiques

| Constante | Couleur | Usage |
|---|---|---|
| `COULEUR_FLASH` | blanc | Flash avant capture |
| `COULEUR_SOURIEZ` | or | Texte "Souriez !" |
| `COULEUR_DECOMPTE` | or | Chiffres du décompte |
| `COULEUR_TEXTE_REPOS` | blanc | Texte non sélectionné |
| `ALPHA_TEXTE_REPOS` | `100` | Transparence du texte non sélectionné |
| `COULEUR_TEXTE_OFF/ON` | orangé | Gradient sélection |
| `COULEUR_TEXTE_G` | blanc | Bouton gauche (Reprendre / Accueil) |
| `COULEUR_TEXTE_M` | vert | Bouton milieu (Valider / Imprimer) |
| `COULEUR_TEXTE_D` | rouge | Bouton droit (Supprimer / Accueil) |

### Tailles de police

| Constante | Défaut | Usage |
|---|---|---|
| `TAILLE_DECOMPTE` | `300` | Chiffres 3, 2, 1 |
| `TAILLE_TITRE_ACCUEIL` | `180` | Gros messages accueil |
| `TAILLE_TEXTE_BOUTON` | `60` | "GRAND FORMAT" / "BANDELETTES" |
| `TAILLE_TEXTE_BANDEAU` | `40` | Texte du bandeau bas |

### Effets pulse

| Constante | Valeur | Usage |
|---|---|---|
| `PULSE_MIN, PULSE_MAX, PULSE_VITESSE` | `150, 255, 5` | Pulse rapide (sélection) |
| `PULSE_LENT_MIN, PULSE_LENT_MAX, PULSE_LENT_VITESSE` | `130, 230, 2` | Pulse lent (respiration) |

---

## 4. Menu accueil

| Constante | Défaut | Effet |
|---|---|---|
| `LARGEUR_ICONE_10X15` | `400` | Largeur icône 10×15 |
| `LARGEUR_ICONE_STRIP` | `200` | Largeur icône strip |
| `OFFSET_DROITE_10X15` | `50` | Décalage horizontal icône 10×15 |
| `OFFSET_DROITE_STRIP` | `110` | Décalage horizontal icône strip |
| `ZOOM_FACTOR` | `1.15` | +15 % de taille si sélectionnée |
| `MARGE_ACCUEIL` | `200` | Espace entre les deux icônes |

---

## 5. Montages (impression)

### Strip (bandelettes)

| Constante | Défaut | Effet |
|---|---|---|
| `STRIP_MARGE_HAUT` | `40` | Marge en haut de la bande |
| `STRIP_MARGE_LATERALE` | `30` | Marge gauche/droite des photos |
| `STRIP_ESPACE_PHOTOS` | `40` | Espace vertical entre photos |
| `STRIP_PHOTO_RATIO` | `0.80` | Ratio H/L : `0.66` = 3:2 natif, `1.0` = carré |

### 10×15

| Constante | Défaut | Effet |
|---|---|---|
| `PHOTO_10x15_LARGEUR/HAUTEUR` | `1600×1000` | Taille de la photo dans le canvas |
| `PHOTO_10x15_OFFSET_X/Y` | `-100, -50` | Décalage dans le canvas |

### Dimensions finales d'impression (300 DPI)

| Constante | Défaut | Calcul |
|---|---|---|
| `MONTAGE_10X15_SIZE` | `(1800, 1200)` | 6″ × 4″ @ 300 DPI |
| `MONTAGE_STRIP_SIZE` | `(600, 1800)` | 2″ × 6″ @ 300 DPI |
| `STRIP_ROTATION_DEGREES` | `180` | Rotation fond+overlay (imprimante tête-bêche) |

### Preview écran 10×15

| Constante | Défaut | Effet |
|---|---|---|
| `MONTAGE_10X15_PREVIEW_SIZE` | `(900, 600)` | Canvas preview |
| `MONTAGE_10X15_PREVIEW_PHOTO_FIT` | `(840, 540)` | Zone photo |
| `MONTAGE_10X15_PREVIEW_PHOTO_OFFSET` | `(30, 30)` | Position photo |
| `MONTAGE_10X15_PREVIEW_QUALITY` | `80` | JPEG quality preview |

### Montage final 10×15

| Constante | Défaut | Effet |
|---|---|---|
| `MONTAGE_10X15_FINAL_PHOTO_FIT` | `(1640, 1040)` | Zone photo finale |
| `MONTAGE_10X15_FINAL_PHOTO_OFFSET` | `(80, 80)` | Position photo finale |
| `MONTAGE_10X15_FINAL_QUALITY` | `98` | JPEG quality impression |

### Preview écran strip

| Constante | Défaut | Effet |
|---|---|---|
| `STRIP_PREVIEW_PHOTO_LARGEUR` | `520` | Largeur photo preview |
| `STRIP_PREVIEW_ESPACEMENT` | `40` | Espace entre previews |
| `STRIP_PREVIEW_MARGE_HB` | `20` | Marge haut/bas |
| `STRIP_PREVIEW_CANVAS_LARGEUR` | `600` | Largeur canvas |
| `STRIP_PREVIEW_THUMBNAIL_MAX` | `(400, 800)` | Taille max thumbnail |
| `STRIP_PREVIEW_QUALITY` | `90` | JPEG quality preview |
| `STRIP_FINAL_QUALITY` | `98` | JPEG quality impression |

| `COULEUR_FOND_LOADER` | `(10, 10, 18)` | Couleur fond écrans transitoires |

---

## 6. Preview live (écran)

| Constante | Défaut | Effet |
|---|---|---|
| `PREVISU_L` | `800` | Largeur preview live |
| `PREVISU_H` | `PREVISU_L / 1.5` | Hauteur calculée (ratio 3:2) |
| `FIN_H` | `600` | Hauteur du montage final à l'écran de fin |
| `PREVISU_H_STRIP` | `600` | Hauteur preview en mode strip |

---

## 7. Textes (localisation)

Tous les textes affichés à l'écran sont ici — candidats idéaux à l'extraction
en i18n/FR.json si on ajoute le multi-langue (voir ROADMAP.md).

### Accueil
`BANDEAU_ACCUEIL`, `BANDEAU_10X15`, `BANDEAU_STRIP`, `MODE_10x15`, `MODE_STRIP`.

### Validation (après prise de vue)
`TXT_VALID_REPRENDRE_10X15/STRIP`, `TXT_VALID_VALIDER_10X15/STRIP`,
`TXT_VALID_ACCUEIL_10X15/STRIP`, `TEXTE_PHOTO_COUNT`.

### Fin (validation finale)
`TXT_BOUTON_REPRENDRE`, `TXT_BOUTON_ACCUEIL`, `TXT_BOUTON_IMPRIMER`,
`TXT_BOUTON_SUPPRIMER`.

### Splash / erreur / abandon
`TXT_SPLASH_CAMERA`, `TXT_SPLASH_CAMERA_OK`, `TXT_SPLASH_CAMERA_FAIL`,
`TXT_PREPARATION_IMP`, `TXT_ERREUR_CAPTURE`, `TXT_ERREUR_IMPRIMANTE`,
`TXT_CONFIRM_ABANDON_1`, `TXT_CONFIRM_ABANDON_2`.

### Durées associées

| Constante | Défaut | Effet |
|---|---|---|
| `DUREE_FLASH_BLANC` | `0.08` | Durée du flash blanc avant capture (s) |
| `DUREE_ECRAN_ERREUR` | `4.0` | Timeout auto des écrans d'erreur (s) |
| `DUREE_CONFIRM_ABANDON` | `3.0` | Fenêtre confirmation abandon (s) |
| `TIMEOUT_SPLASH_CAMERA` | `10.0` | Timeout max connexion caméra (s) |

### Mode burst strip

| Constante | Défaut | Effet |
|---|---|---|
| `STRIP_MODE_BURST` | `False` | `True` = auto-valide photos 1 et 2 d'un strip |
| `STRIP_BURST_DELAI_S` | `2.5` | Délai d'aperçu avant auto-advance (s) |
| `TXT_BURST_COUNTDOWN` | `"Photo suivante dans"` | Texte du compte à rebours |

### Monitoring disque

| Constante | Défaut | Effet |
|---|---|---|
| `SEUIL_DISQUE_CRITIQUE_MB` | `500` | Alerte bandeau rouge si < 500 Mo libres |
| `INTERVALLE_CHECK_DISQUE_S` | `30.0` | Fréquence check disque pendant l'accueil |

### Slideshow d'attente

| Constante | Défaut | Effet |
|---|---|---|
| `DUREE_IDLE_SLIDESHOW` | `30.0` | Secondes d'inactivité avant démarrage |
| `DUREE_PAR_IMAGE_SLIDESHOW` | `3.5` | Durée d'affichage de chaque image |
| `NB_MAX_IMAGES_SLIDESHOW` | `40` | Nombre max d'images scannées |
| `TXT_SLIDESHOW_INVITATION` | `"Approchez pour commencer !"` | Texte invitation |

---

## 8. Impression

| Constante | Défaut | Effet |
|---|---|---|
| `ACTIVER_IMPRESSION` | `True` | `False` pour tester sans gâcher de papier |
| `NOM_IMPRIMANTE_10X15` | `DNP_10x15` | Nom CUPS de la file 10×15 |
| `NOM_IMPRIMANTE_STRIP` | `DNP_STRIP` | Nom CUPS de la file strip |
| `TEMPS_ATTENTE_IMP` | `20` | Affichage roue avant retour accueil (s) |

### Animation roue de chargement

`ANIM_COULEUR_TETE`, `ANIM_COULEUR_QUEUE`, `ANIM_TAILLE_ROUE`,
`ANIM_V_BASE`, `ANIM_V_MAX_ADD`, `ANIM_FREQ`, `ANIM_NB_POINTS`,
`ANIM_RAYON_POINT`, `ANIM_V_ELASTIQUE`.

| `FPS` | `60` | Framerate boucle pygame |

---

## 9. Validation au chargement

Fonction `_valider_config()` en fin de fichier — appelée à l'import. Vérifie :

- Dimensions > 0 (écran, live, photo)
- Timings cohérents (`TEMPS_DECOMPTE >= 1`, `DELAI_SECURITE >= 0.5`, `FPS > 0`)
- Alpha channels dans `[0, 255]`
- Durées positives (`DUREE_FLASH_BLANC`, `DUREE_ECRAN_ERREUR`, etc.)
- Slideshow cohérent (`DUREE_IDLE_SLIDESHOW > 0`, …)
- Ratio photo strip dans `[0.3, 1.2]`
- Marges strip >= 0
- Tailles de montage positives
- Noms d'imprimantes non vides et str

**Un `AssertionError` au démarrage = bug de config, pas de code**. Lire le
message pour savoir quelle assertion a sauté.
