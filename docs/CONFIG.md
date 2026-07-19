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
- `config.py` définit `PYGAME_HIDE_SUPPORT_PROMPT=1` par défaut avant l'import
  de Pygame afin que les sorties machine, notamment `stats.py --json`, ne
  soient jamais polluées par le message d'accueil de la bibliothèque.
- La validation au chargement lève `AssertionError` en cas d'incohérence —
  bien plus clair qu'un bug visuel à mi-événement.
- **Overrides optionnels** via `data/config_overrides.json` : un sous-ensemble
  de constantes peut être surchargé depuis l'interface admin web sans éditer
  le code. Seules les clés de la whitelist `_CONFIG_OVERRIDES_WHITELIST` sont
  prises en compte (voir `docs/ADMIN.md`) ; les résolutions, tailles de
  montage et autres invariants restent figés. Tout override est validé par
  `_valider_config()` après fusion.

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
| `PATH_ETAT_KIOSQUE` | `data/kiosque_etat.json` | Heartbeat atomique partagé entre le kiosque et l'administration |
| `PATH_MISE_EN_PAGE_10X15` | `data/mise_en_page_10x15.json` | Zone photo active publiée atomiquement par l'éditeur de templates |
| `PATH_MISE_EN_PAGE_STRIP` | `data/mise_en_page_strip.json` | Trois zones photo strip actives publiées atomiquement par l'éditeur |

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
| `SON_BEEP_FINAL` | WAV joué à la **dernière seconde** du décompte — fallback sur `SON_BEEP` si absent |
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
| `KIOSK_FULLSCREEN` | `False` | Auto-activé si `PHOTOBOOTH_KIOSK=1` dans l'env (posé par `deploy/kiosk.sh`). `True` → `FULLSCREEN\|NOFRAME` + curseur caché |
| `MASQUE` | `130` | Alpha des bandes latérales noires (si ratio modifié). 0 = invisible, 255 = opaque |
| `TEMPS_DECOMPTE` | `1` | Durée d'un tick de décompte (s). `1` = décompte rapide |
| `TOUCHE_GAUCHE/MILIEU/DROITE` | `K_g/K_m/K_d` | Bindings clavier (lettres minuscules) |
| `DELAI_SECURITE` | `2.0` | Anti-rebond entre deux pressions (s) |
| `INTERVALLE_HEARTBEAT_KIOSQUE_S` | `2.0` | Fréquence de publication de l'état vivant du kiosque (s) |
| `EXPIRATION_HEARTBEAT_KIOSQUE_S` | `8.0` | Délai au-delà duquel l'admin considère le heartbeat périmé (s) |

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

### Assets kiosque gérés par l'admin web (volet 2)

L'admin web peut activer un fond d'accueil, un fond de transition et une police
personnalisés. Le kiosque préfère le fichier « actif » s'il existe
(`resoudre_actif()`), sinon retombe sur le défaut. Effet au redémarrage du
kiosque (slides : à chaud).

| Constante | Défaut | Usage |
|---|---|---|
| `FILE_BG_ACCUEIL_ACTIF` | `assets/interface/accueil_actif.jpg` | Fond d'accueil activé par l'admin |
| `FILE_BG_TRANSITION_ACTIF` | `assets/interface/transition_actif.jpg` | Fond de transition activé par l'admin |
| `POLICE_FICHIER_ACTIF` | `assets/fonts/police_active.ttf` | Police activée par l'admin |
| `PATH_ACCUEIL_BIBLIO` | `assets/interface/accueil/` | Bibliothèque de fonds d'accueil |
| `PATH_TRANSITION_BIBLIO` | `assets/interface/transition/` | Bibliothèque de fonds de transition |
| `PATH_FONTS_BIBLIO` | `assets/fonts/bibliotheque/` | Bibliothèque de polices |
| `PATH_SLIDESHOW_PERSO` | `assets/slideshow/` | Visuels perso ajoutés à la rotation du slideshow |
| `PATH_CORBEILLE` | `data/corbeille/` | Photos retirées de la galerie/slideshow (restaurables) |
| `PATH_EVENEMENT_ACTIF` | `data/evenement_actif.json` | Instantané atomique de l'événement lu par le kiosque au début d'une session |
| `PATH_QUOTA_IMPRESSIONS` | `data/quota_impressions.json` | Compteur persistant de feuilles DNP + quota, partagé kiosque/web (voir `core/quota.py`) |
| `BG_ACCUEIL_EFFECTIF` | résolu à l'import | Actif si présent, sinon `FILE_BG_ACCUEIL` |
| `BG_TRANSITION_EFFECTIF` | résolu à l'import | Actif si présent, **sinon `BG_ACCUEIL_EFFECTIF`** |
| `POLICE_EFFECTIVE` | résolu à l'import | Active si présente, sinon `POLICE_FICHIER` |

**Fond de transition.** C'est le fond des écrans d'attente : annulation d'une
photo, reprise, préparation et attente d'impression. Sa résolution est une
chaîne à trois niveaux — fond de transition activé → fond d'accueil activé →
fond versionné — de sorte qu'un admin qui personnalise seulement l'accueil voit
tous les écrans suivre. Avant cette chaîne, l'écran de transition chargeait un
chemin codé en dur : l'invité qui annulait voyait l'ancien fond du dépôt alors
que l'accueil affichait le nouveau.

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
| `MONTAGE_10X15_PREVIEW_QUALITY` | `80` | JPEG quality preview |

L'aperçu est une réduction de la composition finale complète : il utilise donc
la même zone photo personnalisée, le même fond et le même overlay.

### Montage final 10×15

| Constante | Défaut | Effet |
|---|---|---|
| `MONTAGE_10X15_FINAL_PHOTO_FIT` | `(1300, 866)` | Zone photo finale par défaut |
| `MONTAGE_10X15_FINAL_PHOTO_OFFSET` | `(250, 175)` | Position photo finale par défaut |
| `MONTAGE_10X15_FINAL_QUALITY` | `98` | JPEG quality impression |

Ces valeurs restent le repli sûr. Lorsqu'un template 10×15 actif possède une
mise en page personnalisée, l'admin publie ses coordonnées dans
`data/mise_en_page_10x15.json` ; le moteur les relit à chaque aperçu et montage
final. L'overlay actif est prioritaire sur le fond actif si les deux définissent
une position.

### Preview écran strip

L'aperçu strip est une réduction de la composition finale complète : fond
orienté pour l'impression, trois zones photo personnalisables et overlay.

| Constante | Défaut | Effet |
|---|---|---|
| `STRIP_PREVIEW_PHOTO_LARGEUR` | `520` | Largeur photo preview |
| `STRIP_PREVIEW_ESPACEMENT` | `40` | Espace entre previews |
| `STRIP_PREVIEW_MARGE_HB` | `20` | Marge haut/bas |
| `STRIP_PREVIEW_CANVAS_LARGEUR` | `600` | Largeur canvas |
| `STRIP_PREVIEW_THUMBNAIL_MAX` | `(400, 800)` | Taille max thumbnail |
| `STRIP_PREVIEW_QUALITY` | `90` | JPEG quality preview |
| `STRIP_FINAL_QUALITY` | `98` | JPEG quality impression |

Le profil `STRIP_FORMAT_MODE` reste le repli sûr pour les trois zones. Lorsqu'un
template strip actif possède une mise en page personnalisée, l'admin publie les
coordonnées dans `data/mise_en_page_strip.json`. Chaque photo peut avoir une
position et une taille différentes ; l'overlay actif est prioritaire sur le
fond actif.

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
`TXT_BOUTON_SUPPRIMER`. Après un échec CUPS, les trois actions récupérables
utilisent `TXT_IMPRESSION_SANS`, `TXT_IMPRESSION_REESSAYER` et
`TXT_IMPRESSION_AIDE`, avec le titre `TXT_IMPRESSION_ECHEC` et le message
`TXT_IMPRESSION_AIDE_MESSAGE`.

### Splash / erreur / abandon
`TXT_SPLASH_CAMERA`, `TXT_SPLASH_CAMERA_OK`, `TXT_SPLASH_CAMERA_FAIL`,
`TXT_PREPARATION_IMP`, `TXT_ERREUR_CAPTURE`, `TXT_ERREUR_IMPRIMANTE`,
`TXT_CONFIRM_ABANDON_1`, `TXT_CONFIRM_ABANDON_2`. L'envoi réel à CUPS utilise
`TXT_ENVOI_IMPRIMANTE`, puis `TXT_IMPRESSION_ENVOYEE` uniquement lorsque toutes
les feuilles demandées ont été acceptées.

### Durées associées

| Constante | Défaut | Effet |
|---|---|---|
| `DUREE_FLASH_BLANC` | `0.08` | Durée du flash blanc avant capture (s) |
| `DUREE_ECRAN_ERREUR` | `4.0` | Timeout auto des écrans d'erreur (s) |
| `DUREE_CONFIRM_ABANDON` | `3.0` | Fenêtre confirmation abandon (s) |
| `TIMEOUT_SPLASH_CAMERA` | `10.0` | Timeout max connexion caméra (s) |

### Watermark événement (montages finaux)

Petit texte discret ajouté sur les impressions (10×15 et strip). Désactivé
par défaut.

| Constante | Défaut | Effet |
|---|---|---|
| `WATERMARK_ENABLED` | `False` | Activer/désactiver globalement |
| `WATERMARK_TEXT` | `"Événement — 20/04/2026"` | Texte affiché (vide = no-op) |
| `WATERMARK_COULEUR` | `(255, 255, 255)` | Couleur du texte (blanc) |
| `WATERMARK_ALPHA` | `180` | Transparence 0–255 (180 = discret mais lisible) |
| `WATERMARK_TAILLE_10X15` | `28` | Taille en px sur canvas 1800×1200 |
| `WATERMARK_TAILLE_STRIP` | `20` | Taille en px sur canvas 600×1800 |
| `WATERMARK_POSITION_10X15` | `"bottom-right"` | `"bottom-left"`, `"bottom-center"`, ou `"bottom-right"` |
| `WATERMARK_POSITION_STRIP` | `"bottom-right"` | Idem |
| `WATERMARK_MARGE_PX` | `20` | Distance depuis le bord du canvas |

> ⚠️ **Strip et rotation** : le canvas strip est pré-roté 180° pour compenser
> l'orientation tête-bêche de l'imprimante. Le "bottom-right" du canvas
> correspond donc au "top-left" de l'impression réelle. Faire un tirage test
> et ajuster `WATERMARK_POSITION_STRIP` si la position visible n'est pas celle
> voulue.

### Grain de pellicule (montages finaux)

Bruit gaussien superposé aux montages 10×15 et strip pour un effet argentique
discret. Appliqué uniquement au rendu FINAL (jamais aux previews écran) — le
grain ne se voit qu'à résolution d'impression et évite de charger le CPU en
kiosque. Désactivé par défaut.

| Constante | Défaut | Effet |
|---|---|---|
| `GRAIN_ENABLED` | `False` | Activer/désactiver globalement |
| `GRAIN_INTENSITE` | `8` | Force du mélange en % (0–100). 5–15 reste subtil, au-delà de 25 ça mange la photo |
| `GRAIN_SIGMA` | `30.0` | Écart-type du bruit gaussien (bas = uniforme, haut = tacheté) |

### Filigrane photos restantes (mode strip)

| Constante | Défaut | Effet |
|---|---|---|
| `STRIP_FILIGRANE_ENABLED` | `True` | Gros chiffre semi-transparent en fond pendant le décompte strip (photos restantes : 3 → 2 → 1) |
| `STRIP_FILIGRANE_ALPHA` | `50` | Transparence 0–255 (50 = très discret) |
| `STRIP_FILIGRANE_TAILLE` | `600` | Taille de la police du filigrane |

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

### Monitoring température CPU (Pi)

| Constante | Défaut | Effet |
|---|---|---|
| `SEUIL_TEMP_CRITIQUE_C` | `75.0` | Alerte bandeau orange si CPU ≥ 75 °C (Pi throttle à ~80 °C) |
| `INTERVALLE_CHECK_TEMP_S` | `30.0` | Fréquence check température pendant l'accueil |
| `TEMP_PATH` | `/sys/class/thermal/thermal_zone0/temp` | Fichier système lu. Sur macOS/Windows, le monitor est inerte silencieusement |

### Slideshow d'attente

| Constante | Défaut | Effet |
|---|---|---|
| `ACTIVER_DIAPORAMA_VEILLE` | `True` | `False` conserve l'écran d'accueil, même après une longue inactivité |
| `DUREE_IDLE_SLIDESHOW` | `30.0` | Secondes d'inactivité avant démarrage |
| `DUREE_PAR_IMAGE_SLIDESHOW` | `3.5` | Durée d'affichage de chaque image |
| `NB_MAX_IMAGES_SLIDESHOW` | `40` | Nombre max d'images scannées |
| `TXT_SLIDESHOW_INVITATION` | `"Approchez pour commencer !"` | Texte invitation |

---

## 8. Impression

| Constante | Défaut | Effet |
|---|---|---|
| `ACTIVER_IMPRESSION` | `True` | `False` pour tester sans gâcher de papier : le montage est archivé dans `data/print/`, aucun job CUPS n'est envoyé, et la session est comptée `print_disabled` |
| `ACTIVER_IMPRESSIONS_MULTIPLES` | `True` | `False` saute l'écran de sélection et lance une seule feuille (un 10×15 ou une feuille de deux bandelettes) |
| `NOM_IMPRIMANTE_10X15` | `DNP_10x15` | Nom CUPS de la file 10×15 |
| `NOM_IMPRIMANTE_STRIP` | `DNP_STRIP` | Nom CUPS de la file strip |
| `TEMPS_ATTENTE_IMP` | `20` | Affichage roue avant retour accueil (s) |

### Quota d'impressions (bridage)

Le compteur de feuilles DNP vit dans `data/quota_impressions.json` (jamais remis
à zéro, même après redémarrage — voir `core/quota.py`). Quand le quota est
atteint, l'appui sur IMPRIMER affiche un écran de déblocage : saisir la séquence
gauche→droite→milieu, puis la ressaisir pour confirmer.

| Constante | Défaut | Effet |
|---|---|---|
| `ACTIVER_QUOTA_IMPRESSIONS` | `True` | `False` désactive le bridage (les feuilles restent comptées) |
| `QUOTA_IMPRESSIONS_INITIAL` | `100` | Quota posé **à la création du fichier uniquement** ; ensuite le quota courant vit dans le JSON |
| `QUOTA_IMPRESSIONS_INCREMENT` | `100` | Feuilles ajoutées à chaque déblocage (code kiosque ou bouton admin) |
| `DELAI_DEBLOCAGE_QUOTA` | `30.0` | Inactivité (s) avant abandon de l'écran de saisie du code |

### Animation roue de chargement

`ANIM_COULEUR_TETE`, `ANIM_COULEUR_QUEUE`, `ANIM_TAILLE_ROUE`,
`ANIM_V_BASE`, `ANIM_V_MAX_ADD`, `ANIM_FREQ`,
`ANIM_RAYON_POINT`, `ANIM_V_ELASTIQUE`.

| Constante | Défaut | Effet |
|---|---|---|
| `ANIM_NB_POINTS` | `120` | Nombre de points composant la queue de la roue. Les sprites sont pré-rendus à l'init (couleur+alpha par index), donc seul le blit varie par frame. Baisser pour réduire CPU sur Pi, monter pour une queue plus dense |
| `SPINNER_FPS` | `30` | Framerate de rafraîchissement du spinner (`executer_avec_spinner`, `ecran_attente_impression`). Distinct de `FPS` pour soulager le CPU pendant les phases d'attente |
| `FPS` | `60` | Framerate boucle pygame principale |

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
- Quota d'impressions cohérent (`QUOTA_IMPRESSIONS_INITIAL >= 1`, `QUOTA_IMPRESSIONS_INCREMENT >= 1`, `DELAI_DEBLOCAGE_QUOTA > 0`)

**Un `AssertionError` au démarrage = bug de config, pas de code**. Lire le
message pour savoir quelle assertion a sauté.

---

## 10. Éditeur d'écrans (`data/ecrans_overrides.json`)

Second fichier de surcharges, **distinct** de `config_overrides.json` : la page
Réglages réécrit ce dernier intégralement à chaque sauvegarde et écraserait les
clés d'écran. Les deux périmètres sont disjoints — un test vérifie que leur
intersection est vide — et se réinitialisent indépendamment.

Alimenté par la page **Écrans** de l'admin web (voir `docs/ADMIN.md`), qui génère
son formulaire depuis `core/ecrans.py`. Appliqué par
`config._appliquer_overrides_ecrans()`, juste après les réglages généraux et
**avant** `_valider_config()`.

### Whitelist bornée

`_ECRANS_OVERRIDES_WHITELIST` associe à chaque clé un triplet
`(type, mini, maxi)`. Pour les `str`, les bornes portent sur la **longueur** : un
texte trop long ne fait pas planter le kiosque mais déborde de l'écran.

Les bornes sont volontairement **plus strictes** que les assertions de
`_valider_config()`, de sorte qu'aucune valeur saisie depuis l'admin ne puisse
rendre le kiosque non bootable — l'erreur n'apparaîtrait qu'au redémarrage,
typiquement en plein événement. Un test verrouille cette relation.

Toute valeur invalide (type, bornes, JSON corrompu, clé inconnue) est **ignorée
silencieusement** au chargement : un fichier bidouillé à la main ne peut jamais
empêcher un démarrage.

### Type `couleur`

Les couleurs sont des tuples RGB côté kiosque (ce dont pygame a besoin), mais
JSON n'a pas de tuple et un `[r, g, b]` serait pénible à saisir et à relire. Le
fichier stocke donc la notation **`#rrggbb`** — celle des sélecteurs HTML et des
chartes graphiques — convertie en tuple au chargement par `config.Couleur`. Un
`[r, g, b]` écrit à la main reste toléré en lecture.

### Couleurs par écran

| Écran | Constantes |
|---|---|
| Boutons (partagé) | `COULEUR_TEXTE_G` / `_M` / `_D` / `_INACTIF` |
| Accueil | `BANDEAU_COULEUR`, `COULEUR_TEXTE_REPOS`, `COULEUR_TEXTE_ON` / `_OFF`, `COULEUR_SLIDESHOW_INVITATION` |
| Décompte | `COULEUR_DECOMPTE`, `COULEUR_SOURIEZ`, `COULEUR_COMPTEUR_STRIP`, `COULEUR_BURST_TEXTE` |
| Validation | `COULEUR_ABANDON_TITRE`, `COULEUR_ABANDON_CONSIGNE` |
| Transition / impression | `COULEUR_FOND_LOADER`, `COULEUR_IMPRESSION_TEXTE` |
| Connexion caméra | `COULEUR_SPLASH_ATTENTE` / `_OK` / `_ECHEC` |
| Erreur | `COULEUR_ERREUR_FOND` / `_TEXTE` / `_INDICE` |

La palette **Boutons** est partagée par tous les écrans à boutons (validation,
fin, choix des copies, déblocage quota) : un bouton « annuler » doit avoir le
même rouge partout. Les écrans copies et quota définissaient auparavant leur
propre palette localement, d'où des nuances légèrement différentes sans raison
documentée.

Un test (`tests/test_config_assets.py`) échoue si une couleur littérale est
réintroduite dans `Photobooth_start.py` ou `ui/helpers.py` sans exemption
justifiée — ces fichiers ne sont pas couverts en CI, et une couleur codée en dur
échapperait silencieusement à l'éditeur.
