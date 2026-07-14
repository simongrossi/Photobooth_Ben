# Architecture — Photobooth Ben

Vue technique des modules, de leurs dépendances, de la machine d'état et du flow
de données. Document à mettre à jour lors des refactors structurels majeurs.

---

## Graphe de dépendances

```
┌─────────────────────┐
│  Photobooth_start   │ ◄── entrée + boucle principale + state
└─────┬────────┬──────┘
      │        │
      ▼        ▼
   ┌────┐   ┌────────────────────────┐
   │ ui │   │ core/                  │
   └─┬──┘   │                        │
     │      │  ┌─────────────────┐   │
     ├──────┼─►│ logger          │ ◄─┼── utilisé par tous
     │      │  └─────────────────┘   │
     │      │                        │
     │      │  ┌─────────────────┐   │
     │      │  │ session         │   │  ◄── Etat enum + SessionState + metadata JSONL
     │      │  └─────────────────┘   │
     │      │                        │
     │      │  ┌─────────────────┐   │
     │      │  │ evenements      │   │  ◄── lecture tolérante de l'instantané actif
     │      │  └─────────────────┘   │
     │      │                        │
     │      │  ┌─────────────────┐   │
     │      │  │ monitoring      │   │  ◄── DiskMonitor + lister_images_slideshow
     │      │  └─────────────────┘   │
     │      │                        │
     │      │  ┌─────────────────┐   │
     │      │  │ camera          │   │
     │      │  │ (gphoto2 + lock)│   │
     │      │  └─────────────────┘   │
     │      │                        │
     │      │  ┌─────────────────┐   │
     │ ◄────┼──│ montage (PIL)   │   │  ◄── lazy import dans ui.get_pygame_surf
     │      │  └─────────────────┘   │
     │      │          ▲             │
     │      │  ┌───────┴─────────┐   │
     │      │  │ mise_en_page    │   │  ◄── géométries 10×15/strip JSON tolérantes
     │      │  └─────────────────┘   │
     │      │                        │
     │      │  ┌─────────────────┐   │
     │      │  │ printer (CUPS)  │   │
     │      │  └─────────────────┘   │
     │      │                        │
     │      │  ┌─────────────────┐   │
     │      │  │ arduino         │   │  ◄── pyserial + thread → injecte des KEYDOWN
     │      │  │ (3 btns + LEDs) │   │       pilote les LEDs selon Etat
     │      │  └─────────────────┘   │
     │      └────────────────────────┘
     │
     │  (pygame: screen, clock, fontes)
     ▼
  ┌────────┐
  │ pygame │
  └────────┘
```

### Règles d'importation

- `core/*.py` n'importe **jamais** `ui.*` ni `Photobooth_start` (pas de pygame display).
- `ui/helpers.py` peut importer depuis `core.*` mais **pas** depuis `Photobooth_start`.
- `Photobooth_start.py` peut importer **tout** le reste.
- `Photobooth_start.py` est importable sans lancer le kiosque : les singletons
  hardware/UI sont initialisés uniquement dans `main()`.
- `config.py` n'importe rien (sauf `pygame` en tolérant pour `status.py`).
- Scripts standalone (`status.py`, `stats.py`) n'importent que `config`.
- `web/*` (admin web optionnelle) importe `core/*`, `config`, `stats` — mais
  **jamais** `Photobooth_start` ni `ui/*`. Tourne dans un process systemd
  séparé ; la communication avec le kiosque passe uniquement par le
  filesystem (`data/sessions.jsonl` en lecture, `assets/overlays/`,
  `data/evenement_actif.json`, `data/mise_en_page_10x15.json`,
  `data/mise_en_page_strip.json` et `data/config_overrides.json` en écriture).
  Voir `docs/ADMIN.md`.

---

## Machine d'état

```
         ┌──────────────────────────────────────────┐
         │                                          │
         ▼                                          │
┌────────────────┐                                  │
│    ACCUEIL     │ ◄────────────────────────────────┤
│ (choix mode)   │                                  │
└───────┬────────┘                                  │
        │ TOUCHE_MILIEU (après sélection mode)      │
        ▼                                           │
┌────────────────┐                                  │
│   DECOMPTE     │ ──(erreur capture)───────────────┤
│ (N...3 2 1 📸) │                                  │
└───────┬────────┘                                  │
        │ capture OK                                │
        ▼                                           │
┌────────────────┐                                  │
│   VALIDATION   │                                  │
│ (aperçu + ←●→) │                                  │
└───┬────┬───┬───┘                                  │
    │    │   │                                      │
    │    │   └──(TOUCHE_DROITE = abandon)───────────┤
    │    │                                          │
    │    └──(TOUCHE_GAUCHE = retake) ──┐            │
    │                                  ▼            │
    │                            (DECOMPTE)         │
    │                                               │
    │ TOUCHE_MILIEU                                 │
    ├─► mode 10x15 : imprimer → retour accueil ─────┤
    │                                               │
    └─► mode strips :                               │
        ├─ < 3 photos : retour DECOMPTE             │
        └─ = 3 photos :                             │
                  ▼                                 │
         ┌────────────────┐                         │
         │      FIN       │                         │
         │ (montage +     │                         │
         │  reprendre/    │                         │
         │   imprimer/    │                         │
         │   abandon)     │                         │
         └───┬────┬───┬───┘                         │
             │    │   │                             │
             │    │   └─(TOUCHE_DROITE double)──────┤
             │    └──(TOUCHE_MILIEU = impression)───┤
             └──(TOUCHE_GAUCHE = recommencer)───(DECOMPTE)
```

### Slideshow overlay (sur ACCUEIL uniquement)

Déclenché si `ACTIVER_DIAPORAMA_VEILLE`,
`time.time() - session.last_activity_ts > DUREE_IDLE_SLIDESHOW` et
`session.mode_actuel is None`. Première touche réveille sans déclencher d'action.
Si l'option est désactivée, l'accueil reste visible et la première touche agit
normalement, quelle que soit la durée d'inactivité.

---

## Flow d'une session

```
 1. USER presse TOUCHE_MILIEU en ACCUEIL (mode sélectionné)
           │
 2.        ▼  Etat.DECOMPTE
    • session.id_session_timestamp = timestamp
    • session.session_start_ts = time.time()
    • lecture data/evenement_actif.json puis copie id/nom/tags dans SessionState
    • LiveView caméra affiché (30 FPS via camera_mgr.get_preview_frame())
    • Décompte N → 1 avec beep
    • camera_mgr.capture_hq() :
        - set_liveview(0), cam.exit()
        - subprocess.run gphoto2 capture-image-and-download → PATH_RAW
        - retry 3× avec backoff 0.5 s / 1 s / 2 s
        - set_liveview(1), re-init
    • Fichier RAW ajouté à session.photos_validees
           │
 3.        ▼  Etat.VALIDATION
    • Aperçu dernière photo chargé via PIL + ImageOps.exif_transpose → Surface
    • Mode 10x15 : 3 boutons = retake / imprimer / abandon
    • Mode strips < 3 : retake / valider (next photo) / annuler
    • Mode strips = 3 : transition vers FIN avec preview générée
           │
 4.        ▼  Etat.FIN (strip uniquement)
    • Preview strip généré via MontageGeneratorStrip.preview()
    • 3 boutons : recommencer / imprimer / abandon (double-press)
           │
 5.        ▼  Impression
    • MontageGenerator*.final() dans thread avec spinner animé
    • ACTIVER_IMPRESSION ?
        - non → montage archivé, metadata issue=print_disabled
        - oui → choix des copies si ACTIVER_IMPRESSIONS_MULTIPLES, sinon une feuille
          → printer_mgr.is_ready(mode) ?
            - oui → lp -d nom -o fit-to-page chemin, issue=printed
            - non → ecran_erreur(TXT_ERREUR_IMPRIMANTE), issue=print_failed
    • ecran_attente_impression() (TEMPS_ATTENTE_IMP secondes)
           │
 6.        ▼
    • ecrire_metadata_session(issue=<résultat impression>, nb_photos, duree_s)
    • session.reset_pour_accueil()
    • Retour ACCUEIL
```

### Artifacts produits

| Fichier | Quand | Par |
|---------|-------|-----|
| `PATH_RAW/photo_<id>_<n>.jpg` | capture HQ | `camera_mgr.capture_hq()` |
| `PATH_TEMP/montage_prev.jpg` | entrée VALIDATION/FIN | `MontageGenerator*.preview()` |
| `PATH_TEMP/montage_<mode>_<id>.jpg` | avant impression | `MontageGenerator*.final()` |
| `PATH_PRINT_<mode>/<prefix>_<id>.jpg` | si imprimé | `shutil.copy` |
| `PATH_SKIPPED_RETAKE/retake_<id>.jpg` | si recommencer | `shutil.move` |
| `PATH_SKIPPED_DELETED/deleted_<id>.jpg` | si abandon | `shutil.move` |
| `data/sessions.jsonl` (append, avec instantané événement) | fin de session | `ecrire_metadata_session()` |
| `data/evenement_actif.json` (remplacement atomique) | activation/modification/fin d'événement | admin web |
| `data/admin.db:evenement_template` | quatre choix fond/overlay 10×15/strip par événement | admin web |
| `logs/photobooth.log` (rotation 2 Mo × 5) | continu | `core.logger` |

---

## Threading

Un seul thread de travail : `executer_avec_spinner()` lance la fonction PIL
(`MontageGenerator*.final()`) dans un thread daemon pour ne pas bloquer l'UI
pendant 1-2 s. Le thread principal anime le spinner pendant que le thread worker
fait les opérations PIL. La main thread pygame reste la seule à toucher les
surfaces pygame.

`CameraManager` utilise un `threading.Lock` en prévision d'un futur multi-thread
(capture async non implémentée). Actuellement toutes les opérations caméra sont
sur le thread principal.

---

## Décisions architecturales notables

**`from config import *` conservé pour certains contextes** : toutes les
constantes de config sont importées explicitement dans `Photobooth_start.py`
(96 noms). Le double `import config` permet l'accès qualifié `config.X` dans
les render functions pour lisibilité.

**Singletons module-level (`camera_mgr`, `printer_mgr`, `session`, `UIContext`)**
plutôt que dependency injection. Convient à une app kiosque mono-processus.
Pour les tests unitaires, `monkeypatch` suffit (voir `tests/test_montage.py`).

**Wrappers de compat conservés quand utile** : `get_canon_frame()` reste un
wrapper vers `camera_mgr.get_preview_frame()` car lisible et massivement
utilisé dans `render_decompte`. Les autres wrappers ont été inlinés.

**Sous-systèmes indépendants dans `core/monitoring.py`** : `DiskMonitor` et
`lister_images_slideshow` ne dépendent pas de `SessionState`. Rate-limit interne
à DiskMonitor, slideshow listing sans state. Testables en isolation.

**Mises en page partagées par fichiers atomiques** : l'admin stocke la zone
10×15 ou les trois zones strip de chaque template dans SQLite puis publie le
réglage actif dans `data/mise_en_page_10x15.json` ou
`data/mise_en_page_strip.json`. `core/mise_en_page.py` valide ces géométries ;
`core/montage.py` les relit à chaque aperçu et impression, avec repli sur
`config.py` si un fichier manque ou est invalide. Le kiosque ne dépend donc pas
de Flask ni de SQLite.

**Templates par événement** : `evenement_template` contient un emplacement
explicite pour chaque couple couche×format, avec `NULL` pour « Aucun ». Activer
un événement valide toutes les sources, copie ou retire les quatre cibles fixes,
met à jour les flags `template.actif`, puis republie les géométries. Le kiosque
continue ainsi à ne lire que les fichiers actifs, sans accès à SQLite.
L'association peut être modifiée depuis la fiche événement ou directement
depuis une carte de `/templates/` ; les deux chemins écrivent la même table.

**Horloge serveur du dashboard** : le HTML reçoit l'heure locale, l'époque Unix
et l'offset UTC du serveur. Le navigateur incrémente l'affichage chaque seconde
et se resynchronise toutes les 60 secondes via `/dashboard/heure`, ce qui évite
d'afficher par erreur l'heure ou le fuseau de l'appareil d'administration.

**Entrée runtime explicite** : importer `Photobooth_start.py` ne crée plus de
fenêtre pygame et ne démarre ni caméra ni Arduino. `main()` initialise les
singletons, installe les handlers SIGTERM/SIGINT, lance la boucle, puis ferme
caméra/Arduino/Pygame dans un `finally`.

**SessionState ne contient pas les globals slideshow** : `slideshow_images` et
cie restent en module-level de `Photobooth_start.py` car ce sont des subsystèmes
indépendants du cycle de session.

**Render functions ne sont pas toutes extraites** : `render_accueil` et les
event handlers par état restent inline car leur extraction demanderait de
gérer les nombreux `continue` par retour de signal — gain de lisibilité faible
vs risque de régression. Voir item 9/11 dans [ROADMAP.md](ROADMAP.md).

---

## Diagramme de classes principales

```
┌──────────────────────┐
│ SessionState         │  (dataclass)
├──────────────────────┤
│ etat: Etat           │
│ mode_actuel: str|None│
│ photos_validees:list │
│ id_session_timestamp │
│ session_start_ts     │
│ path_montage         │
│ img_preview_cache    │
│ dernier_clic_time    │
│ abandon_confirm_until│
│ last_activity_ts     │
├──────────────────────┤
│ reset_pour_accueil() │
└──────────────────────┘


┌──────────────────────┐       ┌──────────────────────┐
│ CameraManager        │       │ PrinterManager       │
├──────────────────────┤       ├──────────────────────┤
│ _lock: Lock          │       │ _noms: dict          │
│ _cam: gp.Camera|None │       │                      │
│ _last_init_attempt   │       │                      │
├──────────────────────┤       ├──────────────────────┤
│ is_connected: bool   │       │ nom(mode)            │
│ init() -> bool       │       │ is_ready(mode) -> bool│
│ set_liveview(state)  │       │ send(chemin, mode)   │
│ get_preview_frame()  │       └──────────────────────┘
│ capture_hq(chemin)   │
└──────────────────────┘


┌──────────────────────┐       ┌──────────────────────┐
│ MontageBase (mixin)  │ ◄─────│ MontageGenerator10x15│
├──────────────────────┤       ├──────────────────────┤
│ _canvas_depuis_bg_.. │       │ PREVIEW_SIZE         │
│ _coller_overlay()    │       │ FINAL_SIZE           │
│ _chemin_prev()       │       │ preview(photos)      │
└──────────▲───────────┘       │ final(photos, id)    │
           │                   └──────────────────────┘
           │                   ┌──────────────────────┐
           └───────────────────│ MontageGeneratorStrip│
                               └──────────────────────┘


┌──────────────────────┐
│ UIContext (class singleton)
├──────────────────────┤
│ screen, clock        │
│ font_titre/boutons/  │
│   bandeau/decompte   │
├──────────────────────┤
│ setup(screen, clock, │
│       fonts...)      │
└──────────────────────┘
```
