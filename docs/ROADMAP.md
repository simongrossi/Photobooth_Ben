# Roadmap — Photobooth Ben

> Items dev actionnables, priorisés. Pour les idées en vrac (micro-touches UX,
> effets exotiques, hardware, brainstorm), voir [IDEAS.md](IDEAS.md).
> Pour l'historique de ce qui a été fait, voir [CHANGELOG.md](CHANGELOG.md).

Dernière mise à jour : 2026-07-19 (audit du parcours invité, puis relecture du
suivi en fin de journée)

**Issues GitHub fermées le 2026-07-19** : #19 (décalage +12 h — horloge système,
pas le code), #20 (ralentissement — résorbé par le sprint performance, 142 Mo
après 5 h en production), #21 (quota d'impressions — livré, désactivé par
défaut). Reste ouverte : #15 (nouveau format 3 ou 4 photos en 10×15).

---

## État actuel — fait ✅

**Stabilité & bugs** : fuites PIL corrigées, retry caméra + rate-limit, débounce robuste, écrans d'erreur visibles, except Exception typés.

**UX événementiel** : splash caméra, flash + shutter sound, beep décompte, écran "Préparation...", confirmation abandon, slideshow d'attente désactivable, compteur photo strip, mode burst et impressions multiples désactivables.

**Quota d'impressions** : compteur persistant de feuilles DNP (`core/quota.py`, jamais remis à zéro), bridage au moment d'imprimer, déblocage par code 3 boutons (G→D→M ×2) ou depuis le dashboard admin, paliers configurables.

**Architecture modulaire** : split en `core/` + `ui/` — `core/session` (Etat+SessionState+metadata), `core/monitoring` (DiskMonitor+slideshow), UIContext singleton, render functions extraites (DECOMPTE/VALIDATION/FIN/ACCUEIL), event handlers par état, MontageGenerator/CameraManager/PrinterManager encapsulés. `Photobooth_start.py` est importable sans lancer le kiosque ; `main()` initialise le runtime.

**Hardware** : contrôleur Arduino Nano (`core/arduino.py`) — 3 boutons-poussoirs à LED intégrée via pyserial, pilotage LED selon `Etat`, fallback clavier si pyserial absent. `core/camera.py` dégrade proprement si `gphoto2`/`cv2`/`numpy`/`pygame` manque. Firmware `arduino/photobooth_buttons/`.

**Performance** : LiveView à la demande avec cache par génération, rendus PIL à
la résolution cible et décodage réduit, caches assets/textes/miniatures,
diaporama vide rate-limité, impression sans encodage/copie redondants et outils
de profilage fonctionnels (`profile_mem.py`, `profile_app.py`).

**Observabilité** : logging rotatif, `sessions.jsonl` metadata, télémétrie
performance structurée et rotative (`logs/performance.jsonl`), rapport p50/p95
avec alertes (`perf_report.py`), `status.py` (diagnostic), `stats.py` (rapport
avec histogramme horaire), monitoring disque avec bandeau rouge.

**Code quality** : `from config import *` → imports explicites (96 noms), dead code nettoyé, ruff clean, type hints sur classes publiques + docstrings, log_error → log_info/warning/critical.

**Tests & CI** : pytest (tests unitaires + intégration, `test_status.py`, `test_stats.py`, `test_integration.py`), GitHub Actions CI (`.github/workflows/ci.yml`), coverage (`pyproject.toml`), pre-commit hook (`.pre-commit-config.yaml`).

**Déploiement** : guide Raspberry Pi complet (`docs/DEPLOYMENT.md`), doc architecture (`docs/ARCHITECTURE.md`), doc Arduino (`docs/ARDUINO.md`), changelog (`docs/CHANGELOG.md`).

**Admin web optionnelle** (v1) : service systemd séparé (`photobooth-admin.service`), Flask + SQLite, Basic Auth. Dashboard stats avec horloge serveur persistante, galerie `data/print/`, upload/activation/association événementielle des templates, éditeur d'un sous-ensemble whitelisté de `config.py` (20 clés via `data/config_overrides.json`). Isolation stricte — `web/*` n'importe jamais `Photobooth_start` ni `ui/*`. Voir [ADMIN.md](ADMIN.md).

**Éditeur templates 10×15 et strip** : composition visuelle fond → photo(s) →
overlay, déplacement/redimensionnement par template et aperçu kiosque identique
au rendu final. Les trois zones strip sont réglables indépendamment.

**Gestion événementielle** : événements nommés avec dates et tags, activation
exclusive partagée à chaud avec le kiosque, instantané dans chaque session,
quatre templates facultatifs appliqués automatiquement, filtres
dashboard/galerie, compatibilité « Sans événement » et export ZIP/CSV.

---

## Priorité produit — fiabiliser le parcours utilisateur

Audit réalisé le 2026-07-19 à partir du parcours complet : démarrage, choix du
format, LiveView, capture, validation, reprise, impression, erreurs et retour à
l'accueil. La validation finale devra être faite sur le Raspberry Pi avec le
Canon, la DNP et plusieurs personnes qui ne connaissent pas l'application.

### P0 — fiabilité avant la prochaine prestation

- [x] **Ne déclarer une impression réussie qu'après confirmation de l'envoi** *(livré le 2026-07-19)*
  - Remonter le résultat de chaque appel `PrinterManager.send()` du thread vers
    la machine d'état au lieu de retourner systématiquement `printed` après un
    compte à rebours fixe.
  - Ne jouer le son de succès et ne consommer le quota que pour les feuilles
    effectivement acceptées par CUPS.
  - Distinguer dans l'interface « envoyée à l'imprimante » de « physiquement
    imprimée » et conserver le détail de chaque copie dans la télémétrie.
  - Empêcher une nouvelle impression concurrente tant que la précédente n'a
    pas fini d'être soumise.

- [x] **Rendre les erreurs d'impression récupérables** *(livré le 2026-07-19)*
  - Conserver la session et son montage à l'écran si CUPS ou la DNP refuse le
    travail, au lieu de revenir immédiatement à l'accueil.
  - Proposer `Réessayer`, `Terminer sans imprimer` et `Appeler l'animateur`.
  - Afficher un message invité compréhensible ; réserver le diagnostic CUPS
    détaillé aux logs et au dashboard.

- [ ] **Bloquer proprement les sessions quand la caméra n'est pas prête** *(3–5 h)*
  - Remplacer le trompeur « mode dégradé » par un état explicite « Caméra
    indisponible — reconnexion en cours ».
  - Désactiver le démarrage tant que la caméra n'est pas connectée et qu'aucune
    première frame LiveView valide n'a été reçue.
  - Réactiver automatiquement les formats après reconnexion, avec timeout,
    retour accueil et diagnostic visible par l'exploitant.
  - Ne jamais lancer un décompte sur un écran noir.

- [x] **Conserver un identifiant unique pendant toutes les reprises** *(livré le 2026-07-19)*
  - Initialiser une session selon l'absence de `id_session_timestamp`, pas selon
    `len(photos_validees) == 0`.
  - Couvre la reprise 10×15, `Recommencer` depuis FIN et le dépilement strip.
  - `tests/test_parcours_session.py` verrouille la condition et les trois
    chemins de reprise.

- [x] **Uniformiser la confirmation d'abandon** *(livré le 2026-07-19)*
  - Double confirmation appliquée au strip, comme au 10×15 et à l'écran final.
  - Auto-validation du mode rafale suspendue tant qu'une confirmation est
    armée : elle enchaînait sur la photo suivante pendant que l'invité hésitait,
    et l'annulation était perdue sans trace.
  - L'archivage n'annonce plus « Préparation de votre impression » : il ne
    montre plus rien du tout, puisqu'il est passé en tâche de fond (voir
    « Alléger les reprises et les abandons »).
  - Reste à faire : clignotement du seul bouton rouge pendant la fenêtre
    (côté LED Arduino, non couvert ici).

- [x] **Libérer automatiquement une session laissée sans utilisateur** *(livré le 2026-07-19)*
  - Inactivité sur `VALIDATION` et `FIN` (`DUREE_IDLE_SESSION`, 90 s par défaut,
    0 pour désactiver) ; le choix des copies avait déjà son délai, remonté en
    `DELAI_CHOIX_COPIES` configurable.
  - Compte à rebours affiché pendant les dernières secondes
    (`DUREE_AVERTISSEMENT_IDLE`) : l'écran ne se vide plus sans prévenir.
  - Cause tracée `idle_timeout` dans `sessions.jsonl` et comptée par `stats.py`,
    distincte d'un abandon volontaire.
  - Décision portée par `core/session.py` (fonctions pures, testées en CI).

- [ ] **Protéger la vie privée du diaporama et de la galerie** *(2–4 h)*
  - Limiter le diaporama aux photos de l'événement actif et exclure par défaut
    les événements précédents.
  - Rendre la publication d'une photo et l'accès viewer explicites et opt-in.
  - Prévoir un mode privé, une politique de rétention et une purge/restauration
    compréhensible par l'exploitant.

### P1 — cohérence et simplicité du parcours invité

- [ ] **Définir un contrat permanent pour les trois boutons** *(2–4 h)*
  - Gauche/blanc = retour ou reprendre ; milieu/vert = continuer ou valider ;
    droite/rouge = annuler ou abandonner.
  - Ne plus utiliser le bouton rouge pour `PLUS` sur l'écran des copies.
  - Ajouter des pictogrammes et la position physique du bouton : la couleur ne
    doit jamais être le seul moyen de comprendre l'action.

- [ ] **Repenser le choix du nombre de copies** *(2–3 h)*
  - En strip, afficher `2 bandelettes — 1 feuille` ou `4 bandelettes — 2 feuilles`.
  - Ajouter une action d'annulation et un rappel du quota disponible.
  - Ne pas valider silencieusement la valeur courante après 20 s ; avertir puis
    revenir au choix final ou appliquer uniquement la valeur minimale sûre.
  - Piloter correctement les LEDs Arduino pendant cet écran modal.

- [ ] **Réduire le délai invisible entre les appuis** *(1–2 h)*
  - Remplacer le verrou global de 2 s par un anti-rebond court, par état et par
    transition ; tenir compte des 30 ms déjà assurées par le firmware Arduino.
  - Ne jamais allumer une LED invitant à appuyer pendant que l'action est encore
    ignorée par le programme.

- [ ] **Rendre le réveil du diaporama intuitif** *(1 h)*
  - Un appui gauche ou droit doit réveiller et sélectionner directement le
    format correspondant, ou l'invitation doit annoncer qu'un premier appui ne
    fait qu'afficher les choix.
  - Tester séparément le comportement du bouton central.

- [ ] **Afficher exactement le cadrage qui sera imprimé** *(3–6 h)*
  - Préserver le ratio du LiveView au lieu de le déformer en 1280×800.
  - Reproduire le crop final 10×15/strip, les masques, la rotation et les zones
    réellement visibles sur le papier.
  - Ajouter des guides facultatifs de placement des visages et de marge sûre.

- [ ] **Clarifier le moment réel du déclenchement** *(2–3 h)*
  - Synchroniser le flash écran, le son et le feedback avec la capture réellement
    confirmée par gphoto2.
  - Afficher « Ne bougez plus… » pendant l'acquisition, puis une confirmation
    nette une fois le fichier reçu.

- [ ] **Uniformiser les parcours 10×15 et strip** *(3–5 h)*
  - Utiliser le même enchaînement mental : photo(s) → aperçu final → copies →
    impression.
  - Décider explicitement si le 10×15 doit conserver son impression directe ou
    passer par l'écran `FIN`, puis supprimer les branches inutilisées.
  - Éviter le calcul bloquant sans spinner lors de la génération de la preview
    finale strip.

- [ ] **Rendre l'écran d'erreur de capture actionnable** *(~1 h — le reste est livré)*
  - [x] Impression : `Réessayer` / `Terminer sans imprimer` / `Appeler
    l'animateur`, session et montage conservés *(livré le 2026-07-19,
    `5697e4b`)*.
  - [x] **Capture** : état récupérable livré le 2026-07-19. La session reste
    ouverte, le bouton du milieu relance le décompte dans la MÊME session
    (identifiant conservé), les deux autres rentrent à l'accueil.
  - [ ] Quota : message neutre pour l'invité et déblocage opérateur séparé ; ne
    pas exposer un écran de saisie de code comme parcours normal.
  - [ ] Traduire les erreurs techniques en consignes simples sans perdre le
    détail dans les logs.

- [ ] **Alléger les reprises et les abandons** *(2–3 h)*
  - [x] Ne plus faire attendre l'invité : les quatre chemins d'archivage
    (reprise et abandon, validation et fin) passent par
    `archiver_en_arriere_plan()` dans un thread daemon *(livré le 2026-07-19)*.
    Les dossiers `skipped_*` restent alimentés — la galerie admin les expose.
  - [x] Ne plus annoncer « Préparation de votre impression » pendant l'archivage
    d'une reprise ou d'un abandon *(livré le 2026-07-19, `1a3fb1a`)*. Le message
    dédié introduit alors a été supprimé le soir même : passé en tâche de fond,
    l'archivage n'affiche plus rien, donc plus rien à formuler.
  - [x] Harmoniser l'archivage du 10×15 et des strips : les quatre chemins
    passent par le même helper, qui choisit le générateur selon le mode.

### P2 — qualité visuelle, accessibilité et validation terrain

- [ ] **Faire un passage accessibilité de tous les écrans** *(3–5 h)*
  - Augmenter si nécessaire le bandeau bas et les zones réservées aux actions.
  - Vérifier contrastes, tailles, accents, casse, lisibilité de la police active
    et textes longs configurés depuis l'admin.
  - Ajouter un mode sans pulsations rapides et prévoir un fonctionnement
    silencieux qui reste parfaitement compréhensible.
  - Ne jamais dépendre uniquement du couple rouge/vert.

- [ ] **Créer des tests visuels headless du kiosque** *(4–8 h)*
  - Capturer des références pour accueil, décompte sans/avec LiveView,
    validation, confirmation, copies, impression et erreurs.
  - Tester les textes longs, assets manquants, ratios 1280×800 et 1920×1080 et
    absence de chevauchement dans les trois zones d'action.

- [ ] **Organiser un test avec des utilisateurs novices** *(1–2 h + observation)*
  - Faire exécuter les parcours 10×15, strip, reprise, abandon, copies et erreur
    simulée à au moins cinq personnes sans explication préalable.
  - Mesurer appuis inutiles, hésitations, abandons, durée et compréhension de la
    récupération de la photo imprimée.
  - Transformer chaque incompréhension reproductible en critère d'acceptation.

### Exploitation et administration liées au parcours

Les chantiers heartbeat, verrouillage des actions pendant une session,
activation atomique, CSRF, historique et sauvegardes restent détaillés dans
« Prochain sprint fonctionnel — sécurisation des fonctions récentes ».

- [ ] **Compléter le tableau de santé opérateur** *(3–5 h)*
  - Ajouter caméra, Arduino, profondeur/âge de la file CUPS, dernier envoi
    réussi, dernier échec et état de synchronisation du kiosque.
  - **Partiellement livré (2026-07-19)** : heartbeat/écran/dernière activité,
    caméra, Arduino, profondeur de file, dernier tirage réussi et espace disque.
    Restent l'âge de la file, le dernier échec et le suivi papier/ruban.
  - Séparer les alertes invité des diagnostics techniques et fournir une action
    de résolution sûre pour chaque état rouge.
  - Étudier un suivi papier/ruban DNP ou, à défaut, une estimation explicite à
    partir des feuilles consommées.

- [ ] **Définir le comportement réel des dates d'événement** *(1–2 h)*
  - Indiquer clairement si début/fin sont informatifs ou déclenchent activation
    et clôture automatiques.
  - Empêcher toute bascule d'événement au milieu d'une session et afficher ce
    qui arrivera aux templates et à la galerie lors de la clôture.

- [ ] **Renforcer l'authentification si l'admin sort du LAN privé** *(3–8 h)*
  - Conserver Basic Auth uniquement pour un réseau privé documenté.
  - Sinon ajouter HTTPS, sessions, expiration et vraie déconnexion ; garder la
    galerie publique séparée des routes d'administration.

### Évolutions produit après fiabilisation

- [ ] **Récupération invitée par QR code**, limitée à la session ou à la photo,
  avec expiration et consentement avant publication.
- [ ] **Presets de langue par événement** pour tous les libellés et erreurs du
  kiosque, avec test de débordement.
- [ ] **Modes d'usage explicites** : session rapide, groupe avec décompte long,
  impressions désactivées et galerie privée.
- [ ] **Filtres simples avant capture** : noir et blanc, sépia ou vintage, avec
  aperçu fidèle et possibilité de revenir au rendu naturel.
- [ ] **Écran final court et festif** indiquant clairement que le tirage a été
  envoyé et où le récupérer, puis retour automatique.
- [ ] **Entonnoir UX dans les statistiques** : format choisi, captures,
  reprises, validations, impressions, échecs, timeouts et abandons.

### Ordre produit recommandé

1. Vérité de l'impression et reprise après erreur.
2. Caméra prête avant décompte et LiveView fiable.
3. Identité de session, abandon cohérent et timeout d'inactivité.
4. Contrat des boutons, choix des copies et cadrage fidèle.
5. Confidentialité, accessibilité et tests terrain.
6. Santé opérateur et sécurisation complète de l'administration.
7. QR code, langues, modes et effets.

---

## Prochaine étape performance — mesurer sur le matériel réel

Principe : ne modifier aucun délai, FPS, rendu ou cycle caméra tant que les
mesures du Raspberry Pi ne montrent pas un écart reproductible. La télémétrie
agrège les temps de frame en mémoire et n'écrit que quelques lignes par session.

### P0 — baseline avant toute nouvelle optimisation

- [x] **Journal JSONL rotatif à faible coût**
  - Mesurer première frame LiveView, FPS caméra, acquisition/décodage, rendu du
    décompte, capture HQ, aperçu de validation, montage, CUPS, RAM et température.
  - Corréler les événements avec la session et le mode 10×15/strip.
- [x] **Rapport automatique p50/p95 et alertes**
  - `python3 perf_report.py --date AAAA-MM-JJ` pour comparer les modes et repérer
    les lenteurs réelles sans analyser les logs à la main.
- [ ] **Relever une baseline sur le serveur de production** *(30–45 min)*
  - Faire au minimum 5 sessions 10×15 et 5 sessions strip, dont une reprise et
    une impression, avec caméra et DNP réellement connectées.
  - Conserver le rapport JSON avant/après chaque future optimisation.
  - Vérifier en parallèle l'absence de changement visuel ou fonctionnel.

### P1 — n'agir que si le rapport confirme le seuil

- [x] **Première image / aperçu > 500 ms au p95** : Résolu via décodage Pillow `.draft()` et interpolation `BILINEAR`.
- [ ] **Rendu décompte > 25 ms au p95** : envisager un FPS par état ou des zones
  de rafraîchissement partielles, avec test visuel du décompte et de l'animation.
- [ ] **Capture HQ > 5 s au p95** : distinguer fermeture LiveView, gphoto2 et
  reprise LiveView ; ne réduire le délai de sécurité matériel qu'après un test
  d'endurance sans écran noir ni capture perdue.
- [x] **Montage > 3 s au p95** : Résolu par la mise en cache des calques d'habillage transformés et choix d'interpolation `BILINEAR` pour les previews.
- [x] **RAM +20 Mo sur 5 sessions ou température ≥ 75 °C** : Résolu par la fermeture explicite des images PIL et appel à `gc.collect()`.

### Ordre performance recommandé

1. Déployer la télémétrie telle quelle sur le Pi.
2. Capturer la baseline de 10 sessions et archiver le rapport.
3. Corriger uniquement le premier seuil rouge, un changement à la fois.
4. Rejouer exactement le même scénario et comparer p50/p95, RAM et température.
5. Garder le changement seulement si le gain est mesurable et les tests restent
   verts ; sinon revenir au comportement précédent.

---

## Prochain sprint fonctionnel — sécurisation des fonctions récentes

### P0 — avant la prochaine prestation

- [ ] **Validation complète des réglages avant application** *(2–4 h)*
  - Vérifier les bornes et les dépendances entre valeurs dans l'interface web,
    pas seulement leur type.
  - Effectuer un pré-vol avec import de la configuration générée avant de
    relancer le service.
  - Conserver automatiquement la dernière configuration valide et la restaurer
    si le kiosque ne redémarre pas correctement.
- [x] **État de santé et protection des sessions en cours** *(livré le 2026-07-19)*
  - Publier un heartbeat du kiosque avec son état courant (`ACCUEIL`,
    `DECOMPTE`, `VALIDATION`, `FIN`).
  - Afficher cet état dans le dashboard avec la date du dernier signal reçu.
  - Refuser ou mettre en attente les redémarrages, changements d'événement et
    changements de template pendant une session photo.
  - Heartbeat périmé = déverrouillage automatique. Les routes serveur et les
    contrôles visuels protègent redémarrages/arrêts/reboots, activation ou
    clôture d'événement, habillage actif et mise en page active.
- [ ] **Activation atomique des templates** *(2–4 h)*
  - Préparer les quatre couches et la configuration de mise en page dans des
    fichiers temporaires.
  - Basculer l'ensemble avec `os.replace`, puis revenir à la version précédente
    en cas d'échec.
  - Garantir que le kiosque ne puisse jamais lire un mélange entre ancien et
    nouveau template.
- [ ] **Protection CSRF de l'administration** *(2–3 h)*
  - Ajouter un jeton CSRF sur toutes les actions d'écriture.
  - Couvrir en priorité le redémarrage du service, l'activation d'un événement,
    les réglages et la suppression de médias.
  - Tester le refus d'une requête sans jeton ou avec un jeton invalide.

### P1 — rendre l'exploitation plus sûre

- [ ] **Définir clairement la fin d'un événement** *(1–2 h)*
  - Choisir et documenter si la clôture conserve le dernier habillage ou
    restaure un template « Sans événement ».
  - Afficher une confirmation explicite indiquant le résultat avant la clôture.
- [ ] **Créer un pack événement complet** *(4–8 h)*
  - Regrouper dans un même écran les quatre couches, les layouts 10×15 et strip,
    les textes/filigranes et les aperçus.
  - Ajouter une validation de complétude et une impression de test avant
    activation.
- [ ] **Protéger la suppression des templates utilisés** *(2–3 h)*
  - Afficher les événements qui référencent chaque template.
  - Bloquer la suppression tant qu'un remplacement n'a pas été choisi, au lieu
    de détacher silencieusement la référence.
- [ ] **Historique d'administration et annulation** *(3–5 h)*
  - Journaliser les modifications de réglages, d'événement actif, de templates
    et les redémarrages, avec leur date et les anciennes valeurs.
  - Permettre de restaurer la dernière configuration ou affectation valide
    depuis l'interface.
- [ ] **Test de déploiement Debian/systemd reproductible** *(3–5 h)*
  - Ajouter un smoke test couvrant les droits du dossier, `sudoers`, `systemctl`,
    la base SQLite et les fichiers d'assets.
  - Vérifier le comportement après perte puis retour de la caméra, de CUPS et de
    l'imprimante.
  - Documenter un retour arrière applicable sans environnement virtuel Python.

### P2 — confort et maintenance

- [ ] **Éditeur visuel plus précis** *(4–8 h)*
  - Ajouter annuler/rétablir, déplacement au clavier, guides magnétiques et
    zones de sécurité/fond perdu.
  - Proposer une impression de test depuis l'éditeur avec un rendu strictement
    identique à celui du kiosque.
- [ ] **Horloge serveur diagnostique** *(1–2 h)*
  - Compléter l'heure affichée par le fuseau horaire, l'état de synchronisation
    NTP et une alerte en cas de dérive.
- [ ] **Sauvegardes et contrôle d'intégrité** *(3–5 h)*
  - Sauvegarder ensemble la base SQLite, les templates/assets et la
    configuration active.
  - Ajouter une vérification d'intégrité et une restauration testée depuis le
    dashboard ou le runbook.

### Ordre recommandé

1. Validation et retour arrière des réglages.
2. Heartbeat du kiosque et verrouillage pendant les sessions.
3. Activation atomique des templates.
4. Protection CSRF.
5. Parcours événement complet, historique et déploiement Debian.
6. Améliorations de l'éditeur, diagnostic horaire et sauvegardes.

---

## Court terme — 30 min à 1 h chacun

### UX micro

_Les 3 items historiques (beep dernière seconde, filigrane strip, watermark)
sont livrés — voir [CHANGELOG.md](CHANGELOG.md) et [CONFIG.md](CONFIG.md)._

### Tests & qualité

_Coverage `core/camera.py` livré : 90 % via mocks gphoto2/cv2/numpy/pygame,
147 tests, couverture globale 92,8 %._

### Optimisations rapides

_Monitoring température CPU livré — voir [CHANGELOG.md](CHANGELOG.md)._

_Cache masque décompte, spinner pré-rendu + `SPINNER_FPS` configurable,
microbench `bench_spinner.py` + protocole `docs/PROFILING.md` livrés — voir
[CHANGELOG.md](CHANGELOG.md). Reste à relever les mesures sur Pi réel._

---

## Moyen terme — 1 à 3 h chacun

### Features événementiel

- [ ] **Filtres preset image** — N&B, sépia, vintage/polaroid via `PIL.ImageEnhance` + `ImageFilter`. Écran de choix avant le décompte. Appliqués dans `MontageGenerator.final()`
- [ ] **6.4 Galerie admin** — touche cachée (F1) → grille des montages du jour, navigation flèches, retour Échap. Nouvel état `Etat.GALERIE`
- [ ] **6.5 Overlays thématiques** sélectionnables (mariage, anniversaire, Noël, Halloween...) — scan `assets/overlays/<theme>/`, écran choix avant décompte
- [ ] Mode **timer 10s** — compte à rebours sans appui clavier pour groupes (3e mode accueil ou toggle depuis strip/10x15)

### Robustesse & infra

_Watchdog systemd + kiosk mode livrés — voir [deploy/README.md](../deploy/README.md)
et [CHANGELOG.md](CHANGELOG.md)._

- [ ] **Auto-upload nightly** vers NAS / Dropbox / Nextcloud (cron job rsync)

### Accès admin hors ligne — déploiement progressif

Objectif : garder l'admin Flask accessible sur place même sans box, Internet
ou réseau fourni par le lieu. Le réseau d'administration reste privé et ne se
confond pas avec une éventuelle galerie publique pour les invités.

#### Étape 1 — hotspot téléphone, sans matériel supplémentaire

- [ ] Enregistrer avec NetworkManager un profil Wi-Fi prioritaire : SSID
  `Photobooth`, mot de passe communiqué hors dépôt, reconnexion automatique.
- [ ] Préconiser le partage en **2,4 GHz** pour la compatibilité ; documenter la
  création/renommage du hotspot sur Android et iPhone.
- [ ] Valider le scénario recommandé à deux appareils : téléphone A fournit le
  hotspot, téléphone/tablette B ouvre l'admin.
- [ ] Exposer l'admin via `http://photobooth.local:8080` (mDNS/Avahi), avec
  l'adresse IPv4 courante en solution de secours.
- [ ] Ajouter au diagnostic `status.py` : interface, SSID, IP, état de
  `photobooth-admin.service` et URL complète.
- [ ] Afficher un petit QR code « Admin » contenant l'URL locale, sans intégrer
  le mot de passe Wi-Fi dans les logs ni dans le dépôt.
- [ ] Tester démarrage sans Internet, extinction/réactivation du hotspot,
  reconnexion automatique et reboot complet du Pi.
- [ ] Écrire une fiche client d'une page avec procédure normale et retour
  arrière (`nmcli connection down/up`).

#### Étape 2 — point d'accès avec le Wi-Fi intégré

- [ ] Créer un profil hotspot NetworkManager (`nmcli`) avec SSID privé
  `Photobooth-Admin`, WPA2 et adresse stable (ex. `10.42.0.1`).
- [ ] Utiliser le Wi-Fi intégré comme point d'accès permanent ; réserver
  Ethernet à l'accès Internet éventuel.
- [ ] Restreindre le réseau aux services nécessaires : admin `8080` et SSH de
  maintenance ; ne pas exposer CUPS ou la galerie publique par défaut.
- [ ] Prévoir activation/désactivation idempotente via un script `deploy/` et
  documenter la récupération locale si la configuration réseau échoue.

#### Étape 3 — clé USB Wi-Fi dédiée (cible robuste)

- [ ] Wi-Fi intégré → réseau du lieu ; clé USB → point d'accès privé toujours
  disponible, sans dépendance au Wi-Fi de la salle.
- [ ] Privilégier un chipset avec pilote noyau Linux et mode AP vérifié par
  `iw list`; éviter les références dont le chipset change selon la révision.
- [ ] Candidats à tester sur le Pi réel : **ALFA AWUS036ACM / MT7612U** (choix
  principal), **AWUS036ACHM / MT7610U** (alternative), **AWUS036AXM /
  MT7921AUN** (à valider) ; BrosTrend/Realtek seulement en dernier recours à
  cause des pilotes DKMS.
- [ ] Tester alimentation USB et coexistence pendant plusieurs heures avec
  caméra, Arduino et impression DNP actifs.
- [ ] Ajouter un mode de secours : si le réseau amont disparaît, maintenir le
  point d'accès admin sans interrompre le kiosque.

---

## Long terme — 3 h et plus

### Event Network (feature signature)

> Volet public distinct du réseau d'administration ci-dessus. Combine galerie
> invités, QR code de téléchargement et portail local. À faire après validation
> du point d'accès privé et de son isolation.

**Architecture cible** :
1. Réseau admin privé `Photobooth-Admin`, protégé et réservé à l'exploitation.
2. Réseau invités séparé ou règles firewall strictes, sans accès aux routes admin.
3. Galerie Flask publique locale en lecture seule, téléchargement direct.
4. QR code après impression → URL directe du montage de la session.
5. Portail captif facultatif seulement après validation Android/iOS sur site.
6. ✅ Admin dashboard Flask livré : événements, stats, galerie, templates,
   kiosque et réglages.

**Sous-tâches** :
- ✅ Admin dashboard v1 (Flask + SQLite + Basic Auth) — dashboard, galerie, templates, réglages whitelistés
- [ ] **v2 admin** — état réseau et configuration NetworkManager via `nmcli`
  avec sudoers ciblé, queue imprimante et logs systemd (bouton « redémarrer
  kiosque » et export CSV événement déjà livrés).
- [ ] Évaluer NetworkManager en priorité ; n'introduire `hostapd` + `dnsmasq`
  que si les besoins multi-interface/portail captif le justifient.
- [ ] Extension galerie → mode **LAN public** : route publique sans auth pour téléchargement des montages du jour (à exposer uniquement via l'AP captif)
- [ ] `qrcode` Python : affiche QR après impression (nouvel écran côté kiosque)
- [ ] Captive portal `nodogsplash` ou redirection DNS catchall
- [ ] Choisir entre HTTP strictement local et certificat réellement approuvé ;
  éviter un certificat auto-signé qui déclencherait des alertes navigateur.
- [ ] Config live reload (file watcher sur `data/config_overrides.json`) — évite le `systemctl restart` après chaque réglage

**Effort restant** : ~3-4 jours (l'admin v1 a défriché le plus gros : auth, serveur, galerie, SQLite).
**Inspirations** : voir [IDEAS.md § Références open-source](IDEAS.md#références-open-source-à-étudier) — `photobooth-app` et `RaspAP` notamment.

### Autres gros chantiers

- [ ] **Email / SMS delivery** — après impression, écran "Entrez votre email/numéro" (clavier virtuel tactile) → photo envoyée en PJ. SMTP + formulaire. Peut s'implémenter soit côté kiosque (tactile sur place) soit côté admin v2 (envoi différé depuis la galerie).
- [ ] **Multi-langue** (EN/FR/ES) — toutes les strings extraites dans `i18n/*.json`, toggle sur l'accueil
- [ ] **Branding par événement — suite** : templates et fonds sont désormais
  rattachés automatiquement ; ajouter les textes/filigranes propres à chaque
  événement.

---

## Principe général

**Toujours valider sur matos cible avant de continuer** — `py_compile` ne détecte pas les régressions visuelles ni les bugs d'intégration (caméra USB qui ne revient pas, imprimante qui bugge sur un papier, etc.).

**Commits fréquents avec tags** pour bisect facile en cas de régression entre deux événements.

**Une idée ne monte en roadmap qu'une fois** :
1. Cas d'usage réel identifié (pas juste "ce serait cool")
2. Effort estimé crédible (<1 jour pour court/moyen terme)
3. Chemin d'implémentation clair

Sinon elle reste dans [IDEAS.md](IDEAS.md).
