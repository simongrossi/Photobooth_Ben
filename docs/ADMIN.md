# Interface admin web (optionnelle)

Service séparé du kiosque pygame, activable à la demande sur le Raspberry Pi.
Permet de piloter le photobooth depuis un navigateur (ordinateur ou mobile)
sur le même LAN, sans toucher au code.

- **Dashboard** : heartbeat et écran courant du kiosque, dernière activité,
  caméra, Arduino, profondeur des files CUPS, dernier tirage réussi, disque et CPU,
  compteurs du jour avec activité par heure, totaux (taux d'impression, photos,
  durées, modes), heure locale du serveur toujours visible et historique par journée. Thème clair/sombre automatique
  (suit le réglage du navigateur/téléphone). Carte **Impressions DNP** :
  feuilles consommées / quota / restant, avec bouton de déblocage
  (`+QUOTA_IMPRESSIONS_INCREMENT` feuilles, équivalent au code 3 boutons du
  kiosque).
- **Événements** : création avec dates, tags et quatre choix de templates,
  activation exclusive, fin et archivage. L'événement actif et son habillage
  sont appliqués aux nouvelles sessions sans redémarrer le kiosque. Accès direct aux statistiques, à la galerie et à
  l'export ZIP (avec ou sans photos brutes).
- **Galerie** : parcours des montages produits (10×15 et strips) avec
  miniatures à la volée, filtrable par événement, tag et type. Bouton
  « Retirer » par photo → déplacée vers
  `data/corbeille/` (disparaît du slideshow et de la galerie en ≤ 30 s, jamais
  supprimée définitivement), restaurable depuis la section Corbeille.
  Bouton **« Télécharger le ZIP »** : archive toutes les images du filtre
  courant (type, événement, tag — pas seulement la page affichée), avec un
  `manifest.json` récapitulant le filtre et les fichiers inclus.
  Les mires et sorties connues de tests sont exclues automatiquement.
- **Templates** : bibliothèque des deux couches d'habillage — **overlays** (PNG
  par-dessus la photo) et **fonds** (image sous les photos) — upload, activation
  par format (10×15 / strip), et état « Aucun » par couche×format (photo nue /
  fond blanc, effet à la photo suivante, sans redémarrage du kiosque). La page
  commence par une vue rangée par événement : les quatre emplacements sont
  modifiables et enregistrables ensemble. Le 10×15 et le strip disposent d'un
  éditeur visuel. Pour le strip, les trois
  photos se déplacent et se redimensionnent indépendamment, avec un aperçu
  exact fond → photos → overlay et mémorisation par template.
- **Kiosque** : assets globaux de la borne — **fond d'écran d'accueil**, **fond
  de transition** et **police des textes** (bibliothèque + activation « actif +
  fallback », effet au redémarrage du kiosque, bouton « Revenir au défaut »), et
  **slides perso** ajoutés à la rotation du diaporama d'attente (effet à chaud,
  ≤ 30 s). Le fond de transition couvre les écrans d'attente (annulation d'une
  photo, reprise, impression) ; laissé au défaut, il reprend automatiquement le
  fond d'accueil, pour qu'aucun écran n'affiche une image inattendue.
- **Écrans** : inventaire de tous les écrans du kiosque — pour chacun, la
  vignette du fond **réellement résolu** (avec son origine : activé depuis
  l'admin, hérité du fond d'accueil, défaut versionné, introuvable, ou aucun
  fond par conception) et les textes, durées, tailles et positions en vigueur,
  les valeurs personnalisées étant signalées. Chaque écran est éditable via un
  formulaire généré depuis `core/ecrans.py`. Un bandeau « redémarrage requis »
  apparaît quand la config sur disque a divergé de celle que le kiosque a
  chargée. Écrit `data/ecrans_overrides.json`, indépendant des Réglages.
  L'écran Accueil dispose en plus d'un **aperçu positionné** : les icônes se
  déplacent au glisser-déposer, l'aperçu et les champs se répondent dans les
  deux sens. Le rendu HTML reste approximatif (le rendu final est celui de
  pygame), mais les positions et les tailles de police sont fidèles.
- **Réglages** : édition d'un sous-ensemble de `config.py` via
  `data/config_overrides.json` (timings, imprimantes, slideshow, watermark…).

## Architecture

- Process **totalement séparé** du kiosque : l'arrêt de l'admin n'a aucun
  impact sur les prises de vue.
- Module `web/` qui importe uniquement `core/*` et `config` — jamais
  `Photobooth_start` ni `ui/`.
- Stack : **Flask + Jinja2** (pas de SPA), SQLite (`data/admin.db`), Basic Auth.
- Port par défaut : **8080** sur `0.0.0.0` (LAN). Pour exposition Internet,
  mettre un reverse-proxy HTTPS devant.

## Source de vérité

| Donnée | Stockage | Écrit par | Lu par |
|---|---|---|---|
| Sessions | `data/sessions.jsonl` (append-only) | kiosque | kiosque + admin (dashboard) |
| Événements, tags et templates associés | `data/admin.db` (SQLite) | admin | admin |
| Événement actif | `data/evenement_actif.json` (remplacement atomique) | admin | kiosque au début d'une session |
| Overlays PNG (bibliothèque) | `assets/overlays/*.png` | admin | kiosque (montage) |
| Fonds JPG/PNG (bibliothèque) | `assets/backgrounds/*` | admin | kiosque (montage) |
| Couches actives | `assets/overlays/{10x15,strips}_overlay.png` et `assets/backgrounds/{10x15,strips}_background.jpg` (copies du template activé ; fichier absent = « aucun ») | admin | kiosque |
| Assets kiosque (bibliothèques) | `assets/interface/accueil/`, `assets/interface/transition/`, `assets/fonts/bibliotheque/`, `assets/slideshow/` | admin | kiosque (slideshow à chaud) |
| Assets kiosque actifs | `assets/interface/accueil_actif.jpg`, `assets/interface/transition_actif.jpg`, `assets/fonts/police_active.ttf` (absents = défauts versionnés) | admin | kiosque (au boot) |
| Corbeille galerie | `data/corbeille/<mode>/` | admin | admin (restauration) |
| Métadonnées templates & assets | `data/admin.db` (SQLite) | admin | admin |
| Mise en page 10×15 active | `data/mise_en_page_10x15.json` (remplacement atomique) | admin | kiosque à chaque rendu |
| Mise en page strip active | `data/mise_en_page_strip.json` (remplacement atomique) | admin | kiosque à chaque rendu |
| Surcharges config | `data/config_overrides.json` | admin (page Réglages) | kiosque (à chaque import de `config`) |
| Surcharges d'écran | `data/ecrans_overrides.json` (textes, durées, tailles, positions) | admin (page Écrans) | kiosque (à chaque import de `config`) |
| Compteur/quota d'impressions | `data/quota_impressions.json` (remplacement atomique) | kiosque (tirages) + admin (déblocage) | kiosque + admin (dashboard) |
| Heartbeat kiosque | `data/kiosque_etat.json` (remplacement atomique) | kiosque toutes les 2 s | admin (dashboard et protection des commandes) |

Le kiosque n'a **pas besoin** de connaître l'admin : les overrides sont lus au
démarrage de `config.py` via une whitelist stricte (voir
`config.py:_CONFIG_OVERRIDES_WHITELIST`).

### Éditeur de mise en page 10×15 et strip

Depuis une carte de template 10×15, **Modifier la mise en page** ouvre un
aperçu à l'échelle avec la dernière photo brute disponible. La photo se déplace
à la souris et se redimensionne par la poignée bleue ; les champs X, Y, largeur
et hauteur permettent un réglage précis. Le ratio 3:2 est verrouillé par défaut.

La géométrie est enregistrée sur le template. Si un fond et un overlay actifs
ont tous deux une géométrie, celle de l'overlay est prioritaire. Sans réglage
personnalisé, le moteur reprend les valeurs par défaut de `config.py`.
Pour un template strip, l'éditeur présente trois cadres numérotés : chacun
possède ses propres coordonnées X/Y et dimensions. Le fond et l'overlay sont
orientés comme ils le seront dans le fichier imprimé.

## Cycle de vie d'un événement

1. Créer l'événement avec son nom, ses dates, ses tags, ses notes et ses choix
   de fond/overlay pour les formats 10×15 et strip. Chaque emplacement accepte
   aussi « Aucun template ».
2. Cliquer sur **Activer** avant les premières prises de vue. Une seule ligne
   SQLite peut avoir le statut `actif` ; activer un autre événement termine le
   précédent et publie automatiquement ses quatre choix de templates ainsi que
   leurs mises en page.
   Pendant une session photo, activation, clôture, modification de l'événement
   actif, changement d'habillage actif et mise en page active sont verrouillés
   dans l'interface et refusés côté serveur. Un heartbeat périmé lève ce verrou.
3. Le kiosque lit `evenement_actif.json` au début de la première capture et
   copie `event_id`, `event_name` et `event_tags` dans `sessions.jsonl`.
4. Utiliser les filtres du dashboard et de la galerie. Les anciennes sessions
   sans ces champs apparaissent sous **Sans événement**.
5. Cliquer sur **Terminer**, puis télécharger l'export ZIP. L'option
   **ZIP + brutes** ajoute `data/raw`; l'export standard contient les montages,
   abandons et rejouées rattachés à l'événement.

Renommer un événement actif met immédiatement à jour l'instantané pour les
sessions futures. Les sessions déjà terminées gardent leur nom et leurs tags
d'origine, ce qui préserve l'historique.

La section **Habillage par événement** de la page **Templates** présente
l'événement actif en premier, puis les brouillons et les événements terminés.
Chaque carte permet de choisir ensemble fond et overlay pour les formats 10×15
et strip. L'enregistrement publie immédiatement les quatre choix si l'événement
est actif ; sinon ils seront appliqués lors de sa prochaine activation. La
bibliothèque située dessous reste dédiée à l'upload, à l'aperçu et à l'édition
de la mise en page des fichiers.

## Contrôle du kiosque (dashboard, admin uniquement)

Trois boutons sur le dashboard, avec confirmation (double pour la machine) :

- **Redémarrer le kiosque** (~10 s) — applique fond/police activés, débloque un
  plantage. Sert aussi de « Démarrer » si le kiosque est arrêté.
- **Arrêter le kiosque** — fin d'événement sans éteindre la machine.
- **Redémarrer la machine** (~1 min) — si le problème dépasse l'appli (USB, CUPS).

Une pastille « Kiosque : actif / arrêté / en panne » est affichée dans le
bandeau santé (visible aussi du viewer).

Le kiosque publie également son écran courant, l'heure de dernière activité,
l'état caméra/Arduino et le dernier tirage réellement accepté. Les boutons de
redémarrage, arrêt et reboot sont désactivés et refusés côté serveur pendant
une session. Si le process disparaît sans fermer son fichier d'état, le verrou
expire après `EXPIRATION_HEARTBEAT_KIOSQUE_S` afin de permettre la récupération.

**Prérequis** : le kiosque doit tourner en service systemd
(`sudo ./deploy/install.sh`) et la règle sudoers doit être posée
(`sudo ./deploy/install-admin.sh`, validée par `visudo -c`) — elle n'autorise
que les commandes systemctl exactes ci-dessus, rien d'autre.

### Migration depuis l'autostart XFCE (une fois)

```bash
cd <dossier du projet>
sudo ./deploy/install.sh                       # crée + enable photobooth.service
rm ~/.config/autostart/photobooth.desktop      # fin de l'autostart XFCE
sudo ./deploy/install-admin.sh                 # pose/actualise la règle sudoers
sudo reboot                                    # le kiosque revient via systemd
```

Réversible : recréer le `.desktop` et `sudo systemctl disable photobooth.service`.
Bonus systemd : redémarrage automatique en cas de crash du kiosque
(`Restart=on-failure`, 5 essais max par minute).

## Niveaux d'accès

Deux rôles, gérés par `web/auth.py` :

- **admin** — Basic Auth (`admin` + `PHOTOBOOTH_ADMIN_PASS`) : accès complet,
  toutes les actions. Bouton « Connexion admin » dans la nav pour déclencher la
  fenêtre de mot de passe du navigateur. Le bouton **Se déconnecter** repasse
  l'interface en consultation ; **Connexion admin** réactive ensuite l'accès
  complet (les identifiants Basic peuvent rester mémorisés par le navigateur).
- **viewer** — anonyme, **consultation seule** : dashboard (sans chemins système
  ni bouton de déblocage quota) et galerie (sans « Retirer » ni corbeille).
  Aucune action possible, aucune page de gestion accessible.

⚠️ **Vie privée** : en mode viewer, la galerie (photos de l'événement) est
visible de **tout appareil connecté au même réseau/wifi**. Pour un événement
privé, couper le mode public : `PHOTOBOOTH_ACCES_LIBRE=0` dans
`/etc/photobooth-admin.env` puis `sudo systemctl restart photobooth-admin` —
tout exige alors le mot de passe admin. Sans `PHOTOBOOTH_ADMIN_PASS` configuré,
tout est fermé (503), viewer compris.

## Installation

```bash
cd ~/Photobooth_Ben
sudo ./deploy/install-admin.sh
sudo systemctl start photobooth-admin.service
```

Le script :
1. Installe Flask (apt ou pip).
2. Génère un mot de passe aléatoire et l'écrit dans
   `/etc/photobooth-admin.env`.
3. Crée le service `photobooth-admin.service` dans `/etc/systemd/system/`.
4. Installe une règle sudoers limitée au seul redémarrage de
   `photobooth.service`.
5. Active le démarrage au boot.

Récupère le mot de passe dans `/etc/photobooth-admin.env`, puis ouvre
`http://<ip-du-pi>:8080` dans un navigateur.

## Aperçu du rendu final

`/templates/apercu` (lien « Aperçu du rendu » en haut de la page Templates)
montre le montage tel que le kiosque le produirait, à partir d'une photo déjà
présente dans `data/raw/`. L'objectif est de valider un calage sans imprimer.

On choisit quatre choses :

| Champ | Valeurs |
|---|---|
| Format | `10×15` (une photo) ou `strip` (une session de trois photos) |
| Fond | un template `fond`, le template actif, ou « Aucun » (toile blanche) |
| Overlay | un template `overlay`, le template actif, ou « Aucun » (photo nue) |
| Photo(s) | une session de `data/raw/`, la plus récente par défaut |

Le rendu passe par `core.montage` — le moteur du kiosque — donc il inclut le
recadrage `ImageOps.fit`, le filigrane, le grain et la rotation à 180° des
calques strip. C'est ce qui le distingue de l'aperçu de l'éditeur de mise en
page, qui empile des images dans le navigateur et reste une approximation utile
pour le calage interactif, pas pour la validation finale.

À savoir :

- **Rien n'est activé.** Une combinaison fond + overlay peut être essayée sans
  toucher à ce que le kiosque utilise — c'est sans risque en plein événement.
- **Rien n'est écrit** dans `data/temp/` ni `data/print/` : l'image est produite
  en mémoire et envoyée telle quelle au navigateur.
- **Refusé pendant une session** (HTTP 409) : un rendu 1800×1200 n'a rien à
  faire sur la machine pendant une capture.
- Le strip affiche la bandelette 600×1800, pas la planche `READY_TO_PRINT`
  envoyée à CUPS (deux bandes + offsets de calibration DNP).
- Sans aucune photo dans `data/raw/`, l'aperçu utilise une image de
  substitution : le cadrage est fidèle, pas le contenu.
- Réservé à l'admin (`require_auth`), pas aux viewers anonymes du LAN.

## Exports ZIP (galerie et événements)

Trois points d'entrée, un seul mécanisme :

| Bouton | Route | Contenu |
|---|---|---|
| Galerie · « Télécharger le ZIP » | `/galerie/export.zip?type=&evenement=&tag=` | toutes les images du filtre courant + `manifest.json` |
| Événements · « Export ZIP » | `/evenements/<id>/export.zip` | montages de l'événement + `manifest.json`, `sessions.jsonl`, `sessions.csv` |
| Événements · « ZIP + brutes » | `/evenements/<id>/export.zip?inclure_raw=1` | idem + `data/raw/` (archive lourde, plusieurs Go) |

**Construction différée.** Un « ZIP + brutes » représente vite plusieurs
centaines de photos : la requête ne construit plus l'archive elle-même. Elle
crée une tâche (`web/exports.py`), redirige vers `/export/<tache_id>` et cette
page affiche une barre de progression en interrogeant `/export/<tache_id>/etat`
toutes les 500 ms. Dès que l'archive est prête, le téléchargement démarre seul ;
un lien manuel reste disponible en cas de blocage du navigateur.

- Les images sont écrites **sans compression** (JPEG/PNG le sont déjà) : le
  deflate ne gagnait rien et coûtait l'essentiel du temps. Seuls les fichiers
  texte du ZIP sont compressés.
- **L'archive est écrite dans `data/cache/exports/`, jamais dans `/tmp`.** Sur
  la machine, `/tmp` est un tmpfs (en RAM) et `photobooth-admin.service` tourne
  sous `MemoryMax=256M` : une archive de plusieurs Go y était comptée dans le
  cgroup et faisait tuer le service en cours d'export. Le dossier `data/` est
  sur le disque des photos, donc dimensionné pour elles.
- **Contrôle d'espace avant de démarrer** : la somme des sources plus 512 Mo de
  marge (`exports.MARGE_DISQUE`, pour que le kiosque puisse continuer à écrire)
  doit tenir sur le disque, sinon l'export est refusé avec la taille manquante.
- Une erreur d'écriture (disque plein) **fait échouer l'export visiblement** et
  supprime l'archive partielle. Elle n'est jamais confondue avec un fichier
  source disparu, qui lui est simplement ignoré.
- Le téléchargement accepte les requêtes Range : une coupure réseau au milieu
  d'un ZIP de plusieurs Go peut reprendre au lieu de tout recommencer.
- L'archive est conservée 30 min (`exports.TTL_S`) puis supprimée, et au plus
  8 archives (`exports.MAX_TACHES`) coexistent — les plus anciennes sont
  purgées. Les archives orphelines (laissées par un redémarrage du service)
  sont nettoyées au lancement de l'export suivant. Un lien de suivi périmé
  renvoie 404 : il suffit de relancer l'export.
- Les tâches vivent en mémoire du process admin : un redémarrage de
  `photobooth-admin.service` annule les exports en cours.
- Un fichier disparu entre le listing et l'écriture est ignoré plutôt que de
  faire échouer tout l'export.

## Sauvegarde d'un événement terminé

Cliquer **« Terminer »** sur un événement déclenche, en plus du changement de
statut, la construction d'une **archive complète** — montages *et* photos brutes,
plus `manifest.json` / `sessions.jsonl` / `sessions.csv` — déposée dans
`data/backups/` sous le nom `<slug>__<AAAAMMJJ-HHMM>.zip`. Elle y attend d'être
copiée sur une clé USB à la main.

- La construction passe par le même mécanisme différé que les exports : elle ne
  bloque rien et sa progression est visible. L'archive n'apparaît sous son nom
  final qu'une fois **complète** (renommage atomique), donc un fichier présent
  dans `data/backups/` est toujours un ZIP intègre.
- **Ne pas pouvoir sauvegarder n'empêche jamais de terminer un événement.** Si
  le disque est trop plein, l'événement passe quand même en « terminé » et un
  message le signale.
- Bouton **« Sauvegarder »** par événement pour (re)générer à la demande, y
  compris sur un événement déjà terminé ou archivé.
- La section **« Sauvegardes à copier »** de la page Événements liste ce qui
  attend, avec taille et date, un lien de téléchargement direct, et le bouton
  **« J'ai copié sur clé »**.

⚠️ **Aucune purge automatique.** Une sauvegarde n'est supprimée que par la
confirmation explicite de copie. C'est délibéré : perdre les photos d'un
événement parce qu'un ménage automatique est passé avant la copie serait
irrattrapable, alors qu'un disque qui se remplit se voit et se corrige. La
contrepartie est réelle — chaque sauvegarde pèse autant que l'événement entier
(plusieurs Go). **Copiez puis validez régulièrement**, sinon le disque du
kiosque se remplira et les nouvelles photos ne pourront plus être écrites.

```bash
# Ce qui attend d'être copié, et ce que ça pèse
du -sh data/backups/* 2>/dev/null || echo "aucune sauvegarde"
```

### Récupérer la sauvegarde — ne passez pas par le navigateur

Une sauvegarde pèse plusieurs Go. Le bouton « Télécharger » de l'admin passe par
le serveur de développement Flask : pratique pour un petit export, **inadapté à
2,5 Go**. Par ordre de rapidité :

| Voie | Débit typique | 2,5 Go |
|---|---|---|
| Clé USB branchée sur la machine | 30–100 Mo/s | 30 s – 1,5 min |
| `rsync` en Ethernet | 50–100 Mo/s | 30 s – 1 min |
| `rsync` en WiFi | 3–10 Mo/s | 4 – 15 min |
| Bouton « Télécharger » (WiFi) | quelques centaines de ko/s | plusieurs heures |

**Clé USB, directement sur la machine** — c'est la voie prévue par la
fonctionnalité, et elle n'utilise pas du tout le réseau :

```bash
cp data/backups/*.zip /media/$USER/NOM_DE_LA_CLE/ && sync
```

**Depuis un autre poste**, `rsync` contourne le serveur Flask (il passe par
`sshd`, qui n'est pas bridé) et **reprend là où il s'est arrêté** si la
connexion coupe :

```bash
rsync -avP utilisateur@photobooth:~/Photobooth_Ben/data/backups/ ./sauvegardes/
```

Une fois la copie faite et vérifiée, validez-la dans l'admin (« J'ai copié sur
clé ») pour libérer la place disque.

> ⚠️ **Priorité I/O du service.** `photobooth-admin.service` tournait sous
> `IOSchedulingClass=idle`, qui ne donne des I/O que si le disque est totalement
> inactif. Le slideshow du kiosque lisant des images en continu, l'admin y était
> affamé : un téléchargement plafonnait à ~57 ko/s, soit 13 h pour 2,5 Go.
> L'unité utilise désormais `best-effort` en priorité 7 — le kiosque garde la
> main, sans famine. Après mise à jour :
> `sudo systemctl daemon-reload && sudo systemctl restart photobooth-admin`.

## Usage en dev local (hors Pi)

```bash
pip install flask
PHOTOBOOTH_ADMIN_PASS=secret python3 -m web.app
# → http://localhost:8080
```

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `PHOTOBOOTH_ADMIN_PASS` | *(aucun)* | Mot de passe Basic Auth. **Obligatoire** — sans elle toutes les routes répondent 503. |
| `PHOTOBOOTH_ADMIN_PORT` | `8080` | Port d'écoute HTTP. |
| `PHOTOBOOTH_ADMIN_HOST` | `0.0.0.0` | Interface d'écoute. Mettre `127.0.0.1` pour limiter à l'hôte local. |
| `PHOTOBOOTH_ADMIN_SECRET` | aléatoire au démarrage | Clé de signature des cookies flash. Fixer pour conserver les messages flash après redémarrage (non critique). |

## Réglages modifiables à chaud

Clés whitelistées dans `config.py` (tout le reste reste figé pour éviter de
casser les invariants du pipeline de rendu) :

- Timings : `TEMPS_DECOMPTE`, `DELAI_SECURITE`, `TEMPS_ATTENTE_IMP`,
  `DUREE_IDLE_SLIDESHOW`, `DUREE_PAR_IMAGE_SLIDESHOW`, `STRIP_BURST_DELAI_S`.
- Impression : `ACTIVER_IMPRESSION`, `ACTIVER_IMPRESSIONS_MULTIPLES`,
  `NOM_IMPRIMANTE_10X15`, `NOM_IMPRIMANTE_STRIP`.
- Diaporama : `ACTIVER_DIAPORAMA_VEILLE`.
- Effets : `WATERMARK_ENABLED`, `WATERMARK_TEXT`, `GRAIN_ENABLED`,
  `GRAIN_INTENSITE`, `STRIP_MODE_BURST`.
- Hardware : `ARDUINO_ENABLED`.
- Monitoring : `SEUIL_DISQUE_CRITIQUE_MB`, `SEUIL_TEMP_CRITIQUE_C`.
- Divers : `NB_MAX_IMAGES_SLIDESHOW`.

Le bouton **Enregistrer et appliquer** écrit les réglages puis redémarre
uniquement `photobooth.service`. Le Raspberry Pi et le service admin ne sont
pas redémarrés. **Enregistrer seulement** permet de différer l'application au
prochain démarrage du kiosque.

Après une mise à jour ajoutant cette fonctionnalité, relancer une fois
l'installateur pour créer la règle sudoers :

```bash
sudo ./deploy/install-admin.sh
```

## Sécurité

- **Basic Auth uniquement** — conçu pour un réseau d'événement privé. Pour
  exposer à Internet : reverse-proxy HTTPS + authentification plus robuste.
- Le mot de passe est en clair dans `/etc/photobooth-admin.env` (chmod 640,
  propriétaire `root:<user>`). Comparable à tout fichier de config prod.
- `/etc/sudoers.d/photobooth-admin` autorise seulement la commande exacte
  `systemctl restart photobooth.service`, sans argument fourni par le navigateur.
- Upload de templates : extension `.png` uniquement + validation PIL
  (`Image.verify()`) pour rejeter les fichiers mal formés.
- Les chemins sont résolus et vérifiés contre path-traversal (`os.path.realpath`
  avec garde de racine).

## Désinstallation

```bash
sudo systemctl disable --now photobooth-admin.service
sudo rm /etc/systemd/system/photobooth-admin.service
sudo rm /etc/photobooth-admin.env
sudo rm /etc/sudoers.d/photobooth-admin
sudo systemctl daemon-reload
```

Les données restent (`data/admin.db`, `data/config_overrides.json`,
`assets/overlays/*`) — les supprimer manuellement si besoin.
