# Changelog — Photobooth Ben

Historique des commits par sprint, du plus récent au plus ancien.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr).

## `WIP` — Couleurs éditables par écran

### Added
- **Toutes les couleurs des écrans sont réglables depuis la page Écrans** :
  sélecteur natif pour choisir à l'œil, doublé du code `#rrggbb` pour coller une
  couleur de charte fournie par un client. L'aperçu de l'accueil suit en direct.
- Nouveau type `config.Couleur` : stocké en `#rrggbb` dans
  `data/ecrans_overrides.json` (lisible et corrigeable à la main), converti en
  tuple RGB au chargement pour pygame. Un `[r, g, b]` écrit à la main reste
  toléré en lecture.
- Écran **« Boutons et actions »** : la palette des trois boutons est partagée
  par la validation, la fin, le choix des copies et le déblocage du quota. Elle
  a son propre écran plutôt que d'être rangée sous l'un d'eux — la modifier
  change les quatre, et il fallait que ce soit visible.
- Couleurs promues en constantes depuis des littéraux du code de rendu :
  confirmation d'abandon, écran d'erreur, messages de connexion caméra, textes
  d'attente d'impression, compteur strip, rafale et invitation du diaporama.
- Garde-fou : un test échoue si une couleur littérale est réintroduite dans
  `Photobooth_start.py` ou `ui/helpers.py` sans exemption justifiée. Ces
  fichiers n'étant pas couverts en CI, une couleur codée en dur échapperait
  sinon à l'éditeur sans que rien ne le signale — l'admin réglerait une valeur
  sans effet. Un second test détecte les exemptions devenues obsolètes.

### Changed
- **Les écrans « nombre de copies » et « déblocage quota » changent légèrement
  d'aspect** : ils définissaient leur propre palette locale (vert `(0,200,0)`,
  rouge `(220,50,50)`) et utilisent désormais celle des autres écrans (vert
  `(0,255,0)`, rouge `(255,0,0)`). Cette divergence n'était pas documentée et
  ressemblait à un copier-coller ; les couleurs étant maintenant éditables, les
  teintes d'origine se rétablissent en deux saisies si besoin.

### Fixed
- Une nature de champ absente du regroupement du formulaire faisait disparaître
  ses champs **sans aucun message** — l'écran « Boutons » s'affichait vide à sa
  création. Le regroupement est devenu une constante, et deux tests vérifient
  désormais que toute nature du registre a un groupe et que chaque écran affiche
  bien l'intégralité de ses champs.

---

## `WIP` — Parcours invité : abandon et identité de session (P0)

### Fixed
- **Une reprise ouvrait une seconde session.** L'identifiant était généré quand
  `photos_validees` était vide — or une reprise vide cette liste sans terminer
  la session (retake 10×15, « Recommencer » depuis FIN, dépilement strip). Un
  seul invité produisait donc deux `session_start` et deux horodatages, faussant
  les statistiques et dispersant ses fichiers. La condition porte désormais sur
  l'absence d'identifiant. Le commentaire de `handle_fin_event` annonçait déjà
  « garde id_session » : le code ne le faisait pas.
- **L'abandon en mode bandelettes se déclenchait au premier appui**, contrairement
  au 10×15 et à l'écran de fin. C'est le bouton voisin de « valider », et le mode
  où l'invité a le plus à perdre — jusqu'à trois photos effacées sans recours.
  Double confirmation appliquée, avec la même fenêtre `DUREE_CONFIRM_ABANDON`.
- **Le mode rafale annulait l'abandon en cours.** L'auto-validation partait au
  bout de `STRIP_BURST_DELAI_S` même avec une confirmation armée : l'invité
  appuyait sur annuler, hésitait, et la borne enchaînait sur la photo suivante.
  L'auto-validation est suspendue tant qu'une confirmation est armée.
- **Les écrans d'abandon et de reprise annonçaient « Préparation de votre
  impression »**, laissant croire que l'annulation n'avait pas été prise en
  compte. Nouveau `TXT_ARCHIVAGE_EN_COURS` (« Un instant… »), éditable depuis la
  page Écrans. La vraie impression garde son message.

### Added
- `tests/test_parcours_session.py` : les handlers d'événements sont testables en
  CI (`Photobooth_start` s'importe sans pygame, les codes de touches sont des
  entiers). Couvre la parité d'abandon entre les trois écrans, la survie de
  l'identifiant à travers les trois chemins de reprise, et des gardes de
  non-régression sur les conditions elles-mêmes.

---

## `WIP` — Page Écrans : inventaire et éditeur

### Added
- Page admin **Écrans** (`/ecrans`) : pour chaque écran du kiosque, la vignette
  du fond *réellement résolu* avec son origine explicite — activé depuis
  l'admin, hérité du fond d'accueil, défaut versionné, introuvable, ou aucun
  fond par conception. Répond au problème d'origine : rien ne permettait de
  savoir quelle image un écran afficherait, et l'annulation d'une photo montrait
  un fond que l'admin croyait avoir remplacé.
- Éditeur par écran : textes, durées, tailles de police, positions et opacités,
  groupés par nature. Le formulaire est généré depuis `core/ecrans.py` — chaque
  champ porte son libellé, son aide et ses bornes, donc aucune table de
  métadonnées à maintenir en parallèle (contrairement à `_META_REGLAGES`).
- Bandeau **« redémarrage requis »** quand la config sur disque a divergé de
  celle chargée par le kiosque, avec bouton d'application. Le redémarrage est
  refusé si une session est en cours (garde de `web/systeme.py`).
- Écrit `data/ecrans_overrides.json`, distinct de `config_overrides.json` : les
  deux éditeurs ont des périmètres disjoints et se réinitialisent
  indépendamment (tests de non-régression dans les deux sens).
- `tests/test_web_ecrans.py` : inventaire, aperçus, validation des bornes,
  atomicité du formulaire, isolation des deux fichiers d'overrides et
  protection du rôle viewer.

- **Aperçu positionné** sur l'écran Accueil : rendu HTML à l'échelle du 1280×800
  avec le fond réel, les deux icônes et le bandeau. Les icônes se déplacent au
  glisser-déposer et le lien avec les champs est bilatéral. Les tailles de texte
  utilisent la police active du kiosque, servie en `@font-face`, et les unités
  `cqh` gardent tout à l'échelle quelle que soit la largeur d'affichage.
  Réservé aux écrans dont la géométrie est reproductible : un aperçu
  approximatif serait pire qu'aucun aperçu, puisqu'on réglerait des positions
  en se fiant à une image fausse.
- Tests de synchronisation entre l'aperçu et `_render_accueil_normal` : ils
  échouent si les formules de position du kiosque changent sans que l'aperçu
  suive (duplication assumée, mais qui ne peut plus diverger en silence).

### Security
- Une saisie hors bornes ou de mauvais type est refusée **avant** écriture, et
  une seule erreur annule tout le formulaire : le fichier sur disque reste
  toujours applicable tel quel, et une valeur ne peut pas rendre le kiosque non
  bootable en plein événement.

---

## `WIP` — Optimisation Performance & Fiabilité (Sprint 2026-07-19)

### Added
- Document de référence `docs/roadmap-performance.md` détaillant les étapes d'optimisation.
- Mode SQLite WAL (`journal_mode = WAL`) activé à l'ouverture de la base pour éviter les conflits de verrous concurrents.
- Nettoyage des processus USB bloquants (`pkill`) désormais sécurisé (exécuté sur Linux uniquement) et protégé contre les erreurs.
- État d'erreur d'impression récupérable : la photo et le montage restent à
  l'écran avec les actions « Terminer sans imprimer », « Réessayer » et
  « Appeler l'animateur ».
- Tests de régression du flux CUPS : succès réel, échec partiel, retry des seules
  feuilles restantes et conservation de la session.
- Heartbeat atomique du kiosque : écran courant, dernière activité, session en
  cours, caméra, Arduino et dernier tirage réellement accepté par CUPS.
- Dashboard enrichi avec l'âge du heartbeat, les périphériques, la profondeur
  des files CUPS, le dernier tirage réussi et l'espace disque.
- Verrou partagé `web/session_guard.py` et tests de contournement HTTP pour les
  événements, templates actifs et mises en page actives.

### Changed
- Utilisation de Pillow `.draft()` et de l'interpolation `BILINEAR` pour charger instantanément l'aperçu de validation des clichés.
- Scaling LiveView déporté en asynchrone (via OpenCV) dans le thread d'acquisition d'arrière-plan, soulageant le thread graphique Pygame.
- Mise en cache des calques d'habillage (fonds et overlays) déjà mis à l'échelle et orientés dans `MontageBase`.
- Choix intelligent d'interpolation selon le contexte : `BILINEAR` pour les previews et `LANCZOS` réservé à l'impression finale.
- Mise en cache des textures de texte ombré dans `draw_text_shadow_soft` (évite les rendus de polices et allocations de surfaces Pygame à 30 FPS).
- Libération de mémoire agressive via `.close()` sur les instances d'images PIL intermédiaires et appel explicite à `gc.collect()` après chaque montage final.
- L'écran d'attente d'impression suit désormais la durée réelle du worker CUPS
  au lieu d'un compte à rebours fixe. `printed` et le son de succès ne sont émis
  qu'après acceptation de toutes les feuilles par `lp` ; un retry réutilise le
  même montage et ne duplique pas les feuilles déjà soumises.
- Les commandes admin de redémarrage, arrêt du kiosque et reboot machine sont
  refusées pendant une session active ; un heartbeat périmé libère le verrou
  pour permettre une récupération après plantage.
- Activation/clôture d'événement et changements d'habillage ayant un effet sur
  la session courante sont désormais refusés côté serveur et désactivés dans
  l'interface. Uploads et préparation des brouillons restent disponibles.
- La purge CUPS globale n'est plus exécutée au démarrage : elle risquait
  d'annuler un tirage encore en cours de finalisation. La maintenance manuelle
  est désormais limitée aux deux files DNP configurées.

---

## `WIP` — Cohérence des assets d'écran (phases 0-1)

### Added
- Catégorie d'asset **« fond de transition »** dans la page Kiosque : le fond des
  écrans d'attente (annulation, reprise, impression) est désormais activable
  indépendamment du fond d'accueil, avec bibliothèque, activation et retour au
  défaut comme les autres catégories. `BG_TRANSITION_EFFECTIF` résout en chaîne
  — transition activée → accueil activé → fond versionné — pour qu'un admin qui
  ne personnalise que l'accueil voie malgré tout tous les écrans suivre.
- `tests/test_config_assets.py` : les quatre branches de la chaîne de fallback,
  dont l'indépendance entre fond de transition et fond d'accueil.

### Changed
- La page Kiosque itère sur `CATEGORIES` au lieu de deux listes codées en dur
  dans le gabarit : ajouter une catégorie ne demande plus de retoucher le HTML.
  Chaque section porte une aide décrivant son effet.

### Fixed
- L'écran de transition (annulation d'une photo, reprise, attente d'impression)
  chargeait son fond via le littéral `"assets/interface/background.jpg"` : il
  ignorait donc le fond activé depuis l'admin web et continuait d'afficher
  l'ancien fond versionné, alors que l'accueil, lui, suivait
  `BG_ACCUEIL_EFFECTIF`. L'invité qui annulait voyait une image inattendue.
  Le fond suit désormais `config.BG_ACCUEIL_EFFECTIF`.
- `ecran_erreur()` lisait `ctx.font_path`, un attribut qui n'a jamais existé sur
  `UIContext` : l'appel levait systématiquement et le `except` rechargeait la
  police versionnée en dur, ignorant la police activée par l'admin.
  `UIContext.font_path` existe maintenant et porte `POLICE_EFFECTIVE`.
- Chemins d'assets relatifs (fond de transition, police de secours, chevrons du
  décompte) remplacés par des chemins absolus dérivés de `config.PATH_*` : lancé
  par systemd depuis un autre répertoire, le kiosque tombait silencieusement en
  mode dégradé.

### Changed
- L'écran d'erreur utilise `TAILLE_TEXTE_ALERTE` (80) au lieu d'un `65` codé en
  dur, s'alignant sur la police d'alerte déjà employée ailleurs.

### Added
- `tests/test_config_assets.py` : toute constante de chemin de `config` doit être
  absolue, et un garde-fou anti-récidive échoue si `ui/`, `core/` ou
  `Photobooth_start.py` réintroduit un littéral `"assets/…"` relatif.

---

## `WIP` — Quota d'impressions (idée de Benjamin)

### Added
- `core/quota.py` : compteur persistant de feuilles DNP dans
  `data/quota_impressions.json` (écriture atomique, jamais remis à zéro même
  après redémarrage ; fichier corrompu conservé en `.corrompu-<ts>`), plafond
  cumulé (`quota`) et machine pure `SaisieSequence` pour le code 3 boutons.
- Bridage à l'impression : quand le quota est atteint, l'appui sur IMPRIMER
  affiche un écran de déblocage — saisir gauche→droite→milieu, puis ressaisir
  la même séquence pour confirmer (anti-fausses détections). Succès :
  `+QUOTA_IMPRESSIONS_INCREMENT` feuilles et l'impression s'enchaîne.
- L'écran « nombre de copies » plafonne le choix au quota restant.
- Dashboard admin : carte Impressions DNP (consommées / quota / restant, jauge)
  et bouton POST protégé `+N impressions` ; réglages quota exposés dans la page
  Réglages (`ACTIVER_QUOTA_IMPRESSIONS`, `QUOTA_IMPRESSIONS_INITIAL`,
  `QUOTA_IMPRESSIONS_INCREMENT` via `config_overrides.json`).
- Événement de télémétrie `quota_deblocage` (source kiosque ou web).
- Tests : `tests/test_quota.py`, `tests/test_web_quota.py`, cas overrides quota.

---

## `WIP` — Optimisation globale des performances

### Changed
- Acquisition LiveView limitée aux sélections/décomptes, avec génération de
  frame et cache de Surface : une frame Canon identique n'est plus reconvertie,
  inversée et redimensionnée à chaque rafraîchissement Pygame.
- Connexion caméra du splash déplacée dans un worker pour afficher immédiatement
  l'état de démarrage au lieu de laisser un écran noir pendant l'initialisation USB.
- Diaporama vide rate-limité à un scan toutes les 30 secondes ; surfaces de
  texte, voile de confirmation et chevrons de capture mis en cache.
- Aperçus PIL composés directement à leur résolution cible, décodage JPEG réduit
  avec `draft()` et cache des fonds/overlays invalidé par modification de fichier.
- Le rendu strip retourne directement `READY_TO_PRINT` : suppression d'un second
  encodage JPEG et des copies temporaires par ticket avant envoi à CUPS.
- Galerie basée sur `os.scandir()` et miniatures persistantes avec cache HTTP ;
  service admin abaissé en priorité CPU/I/O par rapport au kiosque.
- Profilage CPU renommé `profile_app.py`, appels explicites à `main()` pour les
  profils CPU/mémoire et baselines alignées sur le cap réel de 30 FPS.

### Added
- Journal `logs/performance.jsonl` compact et rotatif : latence de première
  frame, FPS LiveView, acquisition/décodage, rendu décompte, phases de capture,
  aperçu, montage, CUPS, RAM, GC et température, corrélés par session et mode.
- Agrégation des frames en mémoire avant écriture afin de ne jamais effectuer
  d'I/O disque dans la boucle 30 FPS.
- `perf_report.py` : rapport texte/JSON avec p50/p95, comparaison 10×15/strip,
  rotations, évolution RSS et alertes actionnables.

### Performance
- JPEG source 6000×4000 sur macOS, cache chaud : aperçu 10×15 ≈ 215 → 52 ms,
  aperçu strip ≈ 337 → 72 ms, final strip ≈ 349 → 94 ms. Première génération
  10×15 mesurée à ≈ 100 ms ; validation Raspberry Pi requise.
- Sur macOS, coût de l'instrumentation mesuré à ≈ 8 µs pour résumer 150 frames
  et ≈ 0,06 ms par écriture JSONL ; la validation sur carte SD du Pi reste à faire.

## `WIP` — Éditeur visuel de mise en page 10×15 et strip

### Added
- Association de quatre templates par événement (fond/overlay 10×15 et strip,
  chacun facultatif). L'activation d'un événement publie automatiquement son
  habillage et sa mise en page ; l'événement actif est signalé avec un résumé
  de ses templates dans l'admin.
- Vue `/templates/` rangée par événement, avec affectation groupée des quatre
  emplacements depuis une seule carte et application immédiate si l'événement
  est actif. Chaque emplacement affiche la vignette sélectionnée sans
  rechargement ; la bibliothèque séparée utilise une grille de cartes responsive.
- Horloge locale du serveur dans la barre supérieure du dashboard, actualisée
  chaque seconde et resynchronisée avec le serveur toutes les 60 secondes.
- Deux interrupteurs admin : désactivation du diaporama de veille et des
  impressions multiples. Sans copies multiples, le kiosque imprime directement
  une seule feuille, y compris la feuille contenant deux bandelettes.
- Bouton « Enregistrer et appliquer » : redémarrage du seul service kiosque
  depuis l'admin, protégé par une règle sudoers limitée installée et validée
  automatiquement.
- Éditeur admin par template avec aperçu fond → photo → overlay, déplacement,
  redimensionnement, coordonnées précises, verrouillage 3:2 et préréglages.
- Géométrie mémorisée dans SQLite et publiée atomiquement dans
  `data/mise_en_page_10x15.json` pour le kiosque.
- `core/mise_en_page.py` : validation et lecture tolérante avec repli sur les
  coordonnées par défaut de `config.py`.
- Extension au strip avec trois zones photo indépendantes, mémorisées par
  template et publiées dans `data/mise_en_page_strip.json`.

### Changed
- L'aperçu de validation 10×15 réutilise désormais la composition du rendu
  final, incluant le fond, la position personnalisée et l'overlay.
- Si fond et overlay actifs ont chacun un réglage, l'overlay est prioritaire.
- L'aperçu strip réutilise la composition finale (fond orienté, trois photos et
  overlay), au lieu d'une prévisualisation simplifiée distincte.

## `WIP` — Rangement de la suite de tests

### Changed
- Les fichiers `test_*.py` sont regroupés dans `tests/` ; Pytest, la couverture,
  le pre-commit, les commandes ciblées et la documentation utilisent les
  nouveaux chemins.
- Le générateur manuel `tests/test_DNP_cut.py` conserve ses accès aux dossiers
  racine `assets/` et `test/` après son déplacement.
- La galerie et le diaporama ignorent les mires de calibration et les sorties
  historiques de tests (`test_session`, `strip_wm`, `strip_grain`,
  `cohérence`, timestamp fixture et `soakstrip_*`).
- Les tests de montage strip redirigent désormais `PATH_PRINT_STRIP` vers
  `tmp_path` et ne peuvent plus polluer `data/print/` sur le Raspberry Pi.
- `nettoyer_sorties_tests.py` inventorie puis déplace, sur demande et sans
  suppression, les fichiers techniques existants vers
  `data/corbeille/sorties_tests/`.
- Le message d'accueil de Pygame est masqué afin de préserver une sortie JSON
  valide pour `stats.py --json` sur les Raspberry Pi où Pygame est installé.

## `WIP` — Gestion complète des événements

### Added
- Registre SQLite des événements et tags avec statuts brouillon/actif/terminé/archive,
  dates, notes, activation exclusive et détection informative des chevauchements.
- Page admin `/evenements/` : création, modification, activation, fin,
  archivage et raccourcis stats/galerie.
- Passerelle atomique `data/evenement_actif.json`, réparée au démarrage de
  l'admin et lue par le kiosque au début de chaque nouvelle session.
- Instantané `event_id`, `event_name`, `event_tags` dans `sessions.jsonl` ; les
  anciennes lignes restent compatibles sous « Sans événement ».
- Filtres événement/tag sur le dashboard, la galerie et le CLI `stats.py`.
- Export ZIP par événement avec manifeste, sessions JSONL/CSV, montages et,
  sur demande, photos brutes.
- Tests purs et web couvrant activation exclusive, partage, métadonnées,
  filtres, compatibilité legacy et contenu de l'export.

### Changed
- La galerie rapproche les fichiers de leur session via l'identifiant timestamp
  déjà présent dans les noms et affiche événement/tags sur chaque vignette.
- `core/session.SessionState` transporte puis réinitialise l'instantané événement.

## `WIP` — Interface admin web optionnelle (v1)

### Added
- Module `web/` autonome : app Flask + Jinja2 + HTMX, service systemd séparé
  (`deploy/photobooth-admin.service`, port 8080, Basic Auth via
  `PHOTOBOOTH_ADMIN_PASS`). Communication avec le kiosque **uniquement** par
  filesystem — zéro import de `Photobooth_start` ou `ui/*`.
- 4 blueprints :
  - `/dashboard/` — sessions (réemploie `stats.calculer_stats`), disque + temp
    (réemploie `core/monitoring.DiskMonitor/TempMonitor`), histogramme horaire
  - `/galerie/` — parcours `data/print/` (10×15 + strips), miniatures PIL à la
    volée, pagination, protection path-traversal
  - `/templates/` — upload PNG → `assets/overlays/`, activation exclusive par
    mode (copie vers `OVERLAY_10X15`/`OVERLAY_STRIPS`), suppression guardée
  - `/settings/` — éditeur de `data/config_overrides.json` (whitelist stricte)
- `config.py::_appliquer_overrides()` + `_CONFIG_OVERRIDES_WHITELIST` : 18 clés
  surchargeables sans éditer le code (timings, imprimantes, slideshow,
  watermark, grain, Arduino, seuils disque/temp). Les résolutions et géométrie
  de montage restent figées. Typage strict (bool ≠ int).
- `web/db.py` : SQLite stdlib (`data/admin.db`) pour métadonnées de templates
  (id, nom, type, fichier, actif, uploaded_at). Source de vérité des fichiers
  reste `assets/overlays/`.
- `deploy/install-admin.sh` : installeur idempotent (apt/pip Flask, génère un
  mot de passe aléatoire dans `/etc/photobooth-admin.env` chmod 640, crée le
  service systemd). Indépendant de `deploy/install.sh`.
- `docs/ADMIN.md` : architecture, installation, variables d'env, liste des
  réglages whitelistés, sécurité.
- Tests : `test_web_app.py`, `test_web_gallery.py`, `test_web_templates.py`,
  `test_web_settings.py`, `test_config_overrides.py` — 32 tests couvrant auth,
  routing, upload/validation, activation exclusive, path-traversal, fusion
  d'overrides (whitelist, typage strict, JSON corrompu).

### Changed
- `.github/workflows/ci.yml` : ajoute `flask` aux deps CI (pas de `pygame` /
  `gphoto2` / `cv2` / `pyserial` toujours).
- `pyproject.toml` : `[tool.coverage.run] source` inclut `web/`.
- `CLAUDE.md`, `docs/ARCHITECTURE.md` : graphe de dépendances mis à jour pour
  refléter l'isolation de `web/*`.
- `docs/CONFIG.md` : mention des overrides et de leur whitelist.

### Stats
- Tests : 147 → **179** (+32)
- Coverage : `web/*` entre 77 % et 100 %, global 90,74 % (seuil 75 %)
- Zéro régression sur la suite existante (`ruff check .` propre)

### Sécurité
- Fail closed : sans `PHOTOBOOTH_ADMIN_PASS`, toutes les routes répondent 503.
- `hmac.compare_digest` pour la comparaison mdp.
- Upload PNG uniquement + `Image.verify()` pour rejeter les fichiers malformés.
- Path-traversal bloqué via `os.path.realpath` avec garde de racine.

---

## `WIP` — Perf court terme : décompte + spinner + profiling Pi

### Added
- `Photobooth_start.py::_get_masque_decompte(bande_w, alpha)` + cache module
  `_masque_decompte_cache` : la bande noire latérale du DECOMPTE (mode strips)
  est allouée une seule fois par (largeur, alpha) au lieu d'une `pygame.Surface`
  par frame
- `config.py::SPINNER_FPS=30` : framerate dédié au rafraîchissement du spinner
  (`executer_avec_spinner`, `ecran_attente_impression`), distinct de `FPS`
- `bench_spinner.py` : microbench autonome du `LoaderAnimation` (FPS moyen,
  ms/frame p50/p95/p99), override `--points` pour comparer avant/après optim,
  fallback SDL dummy si pas de display
- `docs/PROFILING.md` : protocole de profiling sur Pi (cProfile, tracemalloc,
  microbench spinner, checklist post-optim, baselines attendues)

### Changed
- `ui/helpers.py::LoaderAnimation` pré-rend `ANIM_NB_POINTS` sprites au boot
  (couleur + alpha figés par index) : la boucle de rendu ne fait plus qu'un
  `blit` par point au lieu de `fill` + `draw.circle` + `blit` → allocations
  par frame divisées par `ANIM_NB_POINTS`
- `config.py::ANIM_NB_POINTS` : 300 → **120** par défaut (suffisant visuellement,
  ~2,5× moins de blits/frame)
- `docs/CONFIG.md` : nouvelles entrées `ANIM_NB_POINTS` et `SPINNER_FPS` dans
  le tableau animation
- `docs/DEVELOPMENT.md` : pointeur vers `docs/PROFILING.md` + `bench_spinner.py`
  dans l'arbo

---

## `WIP` — Priorités stabilité exploitation

### Added
- `Photobooth_start.py::main()` : le module est importable sans lancer pygame,
  caméra ni Arduino ; le runtime n'est initialisé qu'en exécution directe
- Arrêt propre via Échap, SIGTERM et SIGINT, avec fermeture caméra/Arduino/Pygame
  dans un `finally`
- `core/camera.py::CameraManager.close()` pour libérer explicitement la session Canon
- Tests `test_camera.py` : 9 tests CameraManager avec mocks gphoto2/cv2/numpy/pygame
- Tests d'intégration : import `Photobooth_start.py` sans runtime + caméra sans dépendances

### Changed
- `ACTIVER_IMPRESSION=False` devient un vrai mode sans papier : montage archivé
  dans `data/print/`, aucun job CUPS envoyé, metadata `issue=print_disabled`
- Échec CUPS/imprimante : metadata `issue=print_failed` au lieu de `printed`
- `stats.py` affiche et exporte `print_failed` / `print_disabled`
- `core/camera.py` tolère l'absence de `gphoto2`, `cv2`, `numpy` ou `pygame`

### Stats
- Tests : 136 → **147** (+11)
- Coverage : 79,9 % → **92,8 %** ; `core/camera.py` : 0 % → **90 %**

---

## `WIP` — Grain de pellicule sur montages finaux

### Added
- `core/montage.py::MontageBase._appliquer_grain()` : bruit gaussien superposé
  via `Image.effect_noise` + `Image.blend`, niveaux de gris projetés sur les
  3 canaux (pas de dérive de teinte)
- `config.py` : `GRAIN_ENABLED=False`, `GRAIN_INTENSITE=8` (% mélange),
  `GRAIN_SIGMA=30.0`, avec validation assert au chargement
- Tests : 5 nouveaux tests `TestGrain` (disabled no-op, enabled altère canvas,
  intensité 0 ≡ disabled, strip accepte grain, preview jamais altérée)
- `docs/CONFIG.md` : section « Grain de pellicule » à côté du watermark

### Changed
- `MontageGenerator10x15.final()` et `MontageGeneratorStrip.final()` appellent
  `_appliquer_grain()` après le watermark (le grain couvre aussi le texte)

### Pourquoi
- Effet argentique discret demandé dans [IDEAS.md](IDEAS.md#effets-image--expérimentaux),
  activable selon l'ambiance de l'événement (mariage rétro, etc.)
- Isolé au rendu final : pas d'impact CPU sur les previews pendant la session,
  pas de régression visible quand désactivé

### Stats
- Tests : 131 → **136** (+5)
- Coverage : 80.6 % → **80.9 %** ; `core/montage.py` : 88 % → **93 %**

---

## `WIP` — Watchdog systemd + mode kiosque

### Added
- `deploy/photobooth.service` : unit systemd templatisé (`@USER@`, `@HOME@`)
  avec watchdog (`Restart=on-failure`, `StartLimitBurst=5/60s`, `MemoryMax=1G`,
  `TimeoutStopSec=30`)
- `deploy/kiosk.sh` : wrapper de démarrage (xset off, unclutter, export
  `PHOTOBOOTH_KIOSK=1`, venv, exec python)
- `deploy/install.sh` : installeur idempotent (apt install unclutter, sed
  substitution placeholders, systemctl enable)
- `deploy/uninstall.sh` : retrait propre du service
- `deploy/README.md` : guide complet d'installation + dépannage

### Changed
- `Photobooth_start.py` : `pygame.display.set_mode()` prend `FULLSCREEN | NOFRAME`
  si `config.KIOSK_FULLSCREEN=True`, curseur caché en kiosque
- `config.py` : `KIOSK_FULLSCREEN = os.environ.get("PHOTOBOOTH_KIOSK") == "1"`
  — auto-activation depuis l'env posé par `kiosk.sh`
- `docs/DEPLOYMENT.md` : sections 8 (systemd) et 9 (kiosque) remplacées par
  des pointeurs vers `deploy/`, plus de heredoc inline
- `docs/RUNBOOK.md` : commande de rearm watchdog (`systemctl reset-failed`)

### Pourquoi
- Fichiers d'infra versionnés (testables, reviewables) plutôt que heredocs
  enfouis dans la doc
- Watchdog complet avec limite anti-boucle + memory cap + stop gracieux
- Mode kiosque activable via env sans modification de config.py (dev/prod
  même base)

---

## `e60ec6c` — Monitoring température CPU (Raspberry Pi)

### Added
- `core/monitoring.py::TempMonitor` — même pattern que DiskMonitor,
  lit `/sys/class/thermal/thermal_zone0/temp`, inerte silencieux hors Pi
- `config.py` : `SEUIL_TEMP_CRITIQUE_C=75.0`, `INTERVALLE_CHECK_TEMP_S=30.0`,
  `TEMP_PATH`
- `status.py::check_temperature()` — diagnostic pré-événement non-bloquant
- `Photobooth_start.py` : bandeau orange en ACCUEIL si CPU ≥ 75 °C
- Tests : 7 nouveaux tests TempMonitor + 3 tests check_temperature

### Stats
- Tests : 121 → **131** (+10)
- Coverage : 80.1 % → **80.6 %**

---

## `fb704ab` — Split Photobooth_start.py : core/session + core/monitoring

### Added
- `core/session.py` : `Etat` enum, `SessionState` dataclass, `ecrire_metadata_session()`,
  `terminer_session_et_revenir_accueil()` — module pur, testable isolément
- `core/monitoring.py` : `DiskMonitor` (classe rate-limitée, remplace 3 globals
  module-level), `lister_images_slideshow(dossiers, nb_max)` (pure)
- `test_session.py` (11 tests) + `test_monitoring.py` (14 tests)

### Changed
- `Photobooth_start.py` : imports depuis `core.session` et `core.monitoring`,
  suppression de 190 lignes déplacées. 1183 → 1071 L.
- `docs/ARCHITECTURE.md` : modules session + monitoring ajoutés au graphe
- `docs/DEVELOPMENT.md` : arborescence mise à jour
- `docs/TESTING.md` : nouveaux tests inventoriés, couverture actualisée

### Stats
- Coverage : 78 % → **80 %** (seuil via `core/session` 100 % et `core/monitoring` 95 %)
- Tests totaux : 96 → **121** (+25)

---

## `19973c3` (PR #1) — Boîtier Arduino : 3 boutons-poussoirs à LED intégrée

### Added
- `core/arduino.py` : `ArduinoController` (thread pyserial → `pygame.KEYDOWN`,
  pilotage LED selon `Etat` via `tick()`)
- `arduino/photobooth_buttons/photobooth_buttons.ino` : firmware Nano
  (3 boutons `INPUT_PULLUP` + 3 LEDs PWM, protocole L/M/R ↔ LED:*:STATE)
- `docs/ARDUINO.md` : câblage, flash, protocole, dépannage, checklist Pi
- `config.py` : clefs `ARDUINO_ENABLED`, `ARDUINO_PORT`, `ARDUINO_BAUDRATE`

### Changed
- `Photobooth_start.py` : init du contrôleur après pygame, `arduino_ctrl.tick(...)`
  dans la boucle principale, `close()` à la sortie
- `docs/ARCHITECTURE.md` : mention du nouveau module dans le graphe de dépendances
- `docs/DEPLOYMENT.md` : ajout de `python3-serial` + renvoi vers `ARDUINO.md`

### Dépendance (optionnelle)
- `pyserial` — absent = fallback silencieux sur clavier uniquement

---

## `5d04934` — Quick wins code quality (6 items)

**Code quality** sans changement fonctionnel.

### Added
- Type hints sur classes publiques (`CameraManager`, `PrinterManager`,
  `MontageGenerator*`, helpers du `logger`)
- `from __future__ import annotations` pour support typing sur Python 3.9

### Changed
- `from config import *` → liste explicite de 96 noms (dépendances visibles)
- 15 `log_error()` migrés vers `log_info` / `log_warning` / `log_critical` nommés
- Semicolons one-liner → lignes séparées (ruff E702)
- `except Exception as e: log(...)` → bloc sur 2 lignes (ruff E701)
- Variables `l` ambigües → `ligne` dans status.py (ruff E741)
- Docstrings uniformisées (1re ligne courte, présent) + ajouts manquants

### Removed
- Dead code : `_CameraProxy`, wrappers `init_camera/set_liveview`,
  `generer_preview_10x15` & cie (call sites migrés vers classes),
  `imprimante_prete`, `imprimer_fichier_auto` (appels remplacés par `printer_mgr.send`)
- Imports inutilisés dans main : cv2, numpy, gphoto2, subprocess

### Stats
- 7 fichiers touchés, -138 / +118 lignes
- `ruff check .` : 0 warning
- Tests : 18/18 passent

---

## `1609da0` — Item 8 : split en dossiers `core/` + `ui/`

### Added
- Package `core/` : logger, camera, montage, printer
- Package `ui/` avec `helpers.py` et `__init__.py` qui re-exporte
- `core/__init__.py` + `ui/__init__.py` documentant leur rôle

### Changed
- Imports dans main : `from core.X import ...` et `from ui import ...`
- Cross-module : `core.camera` et `core.printer` importent `from core.logger`

### Renamed (git mv — historique préservé)
- `camera.py` → `core/camera.py`
- `logger.py` → `core/logger.py`
- `montage.py` → `core/montage.py`
- `printer.py` → `core/printer.py`
- `ui.py` → `ui/helpers.py`

---

## `9524d6d` — Items 9+11 (partiel) : extraction render functions

### Added
- `render_decompte(session)` : preview caméra + capture + transition
- `render_validation(session)` : aperçu + bandeau + burst countdown. Retourne `True` si auto-advance.
- `render_fin(session)` : aperçu final + overlay confirmation abandon

### Changed
- Main loop dispatch simplifié : chaque état (sauf ACCUEIL) est 1-3 lignes
- Main file : -231 / +228 lignes

### Non extrait
- `render_accueil` (complexité slideshow + `continue` interne)
- Event handlers par état (nombreux `continue` à refactor)

---

## `a9c8a20` — Item 7 : UIContext + ui.py

### Added
- `UIContext` singleton : `screen`, `clock`, fontes injectés au boot
- `ui.py` (348 lignes) : setup_sounds, jouer_son, draw_text_shadow_soft,
  inserer_background, obtenir_couleur_pulse, get_pygame_surf{_cropped},
  LoaderAnimation, afficher_message_plein_ecran, executer_avec_spinner,
  ecran_erreur, ecran_attente_impression, splash_connexion_camera
- `splash_connexion_camera(camera_mgr)` prend `camera_mgr` en paramètre (DI)

### Changed
- Main file : -230 lignes (1367 → 1137)
- `threading` retiré des imports du main (déplacé dans ui.py)

---

## `f00d3ad` — Item 10 : SessionState dataclass

### Added
- `@dataclass class SessionState` encapsulant 10 variables de session
  (etat, mode_actuel, photos_validees, id_session_timestamp, session_start_ts,
  path_montage, img_preview_cache, dernier_clic_time, abandon_confirm_until,
  last_activity_ts)
- Méthode `reset_pour_accueil()` centralisant le reset en fin de session

### Changed
- 133 références globales migrées vers `session.X`
- `terminer_session_et_revenir_accueil` appelle `session.reset_pour_accueil()`

### Removed
- Code mort : `selection`, `path_montage_hd` (jamais utilisés)
- Toutes les déclarations `global X` dispersées

---

## `247965f` — README.md + déplacement docs/ + mode burst strip

### Added
- `README.md` à la racine : démarrage rapide, architecture, observabilité, tests
- Mode burst strip : auto-validation photos 1 et 2 après `STRIP_BURST_DELAI_S`
  (désactivé par défaut `STRIP_MODE_BURST = False`)
- Countdown visible "Photo suivante dans Xs" en mode burst

### Moved
- `IDEAS.md` + `ROADMAP.md` → `docs/` (via `git mv`)

---

## `b400d7e` — Refactor modulaire + features événementiel (Sprints 1-6)

**Le gros bootstrap.** Voir commit message complet pour le détail.

### Sprints 1 — Stabilité
- Fuites PIL corrigées (`with Image.open`)
- Retry 3× + backoff sur capture gphoto2, rate-limit reconnexion USB
- Débounce `>=` au lieu de `>`
- `except` nus remplacés, `import sys` manquant ajouté

### Sprint 2 — UX événementiel
- Splash caméra boot avec retry visible
- Flash blanc 80 ms + son shutter, beep décompte, success impression
- Écran "Préparation impression..." avec spinner animé
- Écrans d'erreur visibles (capture, imprimante) avec timeout
- Vérification `lpstat` avant envoi CUPS
- Confirmation abandon double-press en état FIN
- Slideshow d'attente après 30 s idle
- Compteur "Photo N/3" renforcé en mode strip

### Sprint 3 — Performance
- Threading PIL avec spinner animé
- Cache `BANDEAU_CACHE` (surfaces statiques)
- Loader GC optim (buffer réutilisé au lieu de 300 surfaces/frame)
- Purge `PATH_TEMP` au startup + check disque continu

### Sprint 4 — Architecture (1re étape)
- `core/camera.py` : `CameraManager` avec `threading.Lock` + retry
- `core/montage.py` : `MontageGenerator10x15` / `MontageGeneratorStrip`
- `core/printer.py` : `PrinterManager` CUPS
- `core/logger.py` : `RotatingFileHandler` + helpers nommés
- `terminer_session_et_revenir_accueil` (consolidation 5 sites)
- `Etat` Enum remplace strings
- Validation config au chargement (18 assertions)

### Sprint 5 — Observabilité
- Logging rotatif 2 Mo × 5 = 10 Mo max
- `sessions.jsonl` metadata par session
- [status.py](../status.py) : diagnostic pré-événement autonome
- [stats.py](../stats.py) : rapport fin de soirée avec histogramme horaire
- Monitoring disque continu avec bandeau rouge écran < 500 Mo

### Sprint 6 — Features événementiel
- Slideshow idle ACCUEIL
- Compteur photo strip renforcé

### Tests
- [test_montage.py](../tests/test_montage.py) : 18 tests pytest, isolation via monkeypatch

### Documentation
- [ROADMAP.md](ROADMAP.md) : items actionnables priorisés
- [IDEAS.md](IDEAS.md) : pool d'idées + références open-source
  (PIBOOTH, photobooth-app, RaspAP, nodogsplash)

---

## `be5eb16` — Initial commit

Code mono-fichier historique. ~1086 lignes dans `Photobooth_start.py`, fonctionnel
mais avec fuites mémoire, retry absent, duplications de code, config non validée.
Point de départ du refactor documenté dans les sprints suivants.
