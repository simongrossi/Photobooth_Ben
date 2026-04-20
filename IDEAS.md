# Ideas — Photobooth Ben

> Pool d'idées en vrac pour piocher quand tu as du temps. Pas priorisé, pas engagé.
> Pour les items actionnables et priorisés, voir [ROADMAP.md](ROADMAP.md).

Une idée passe en roadmap uniquement quand :
1. Un cas d'usage réel est identifié (pas juste "ce serait cool")
2. Un effort estimé crédible existe
3. Un chemin d'implémentation est clair

---

## UX — micro-touches

- [ ] **Confetti animation** sur l'écran après impression réussie (quelques particules Pygame simples)
- [ ] **Voix synthétique décompte** ("Trois... deux... un... souriez !") via `espeak` ou samples pré-enregistrés (bien plus sympa qu'un beep sec)
- [ ] **Countdown en filigrane** pendant la capture en mode strip (3 → 2 → 1 semi-transparent)
- [ ] **Watermark événement** discret sur les montages (ex: "Mariage Smith — 20/04/2026") configurable
- [ ] **Bip différent** pour la dernière seconde du décompte (tension montante)
- [ ] **"Session suivante dans X"** affiché si queue de personnes (désambiguïse les appuis)
- [ ] **Mode réservé** avec PIN administrateur (évite les gamins qui spamment)
- [ ] **Sélecteur émoji réactions** après impression (❤️ 😂 🎉) → agrégé dans les stats
- [ ] **Animation "page qui tourne"** entre les écrans (transitions plus pro)
- [ ] **Mode photo seule** sans montage (3e mode accueil) pour gens pressés

---

## Hardware

- [ ] **Monitoring batterie** si photobooth portable (UPS / powerbank + lecture I²C)
- [ ] **LEDs RGB** WS2812 pilotées pendant le décompte (rouge/jaune/vert)
- [ ] **Capteur de mouvement PIR** pour auto-démarrer le slideshow quand quelqu'un approche
- [ ] **Écran secondaire HDMI2** pour live view / slideshow côté public
- [ ] **Imprimante thermique de tickets** (numéro de retrait) pour séparer capture et retrait photo
- [ ] **NFC tap-to-pair** : sticker NFC → téléphone tape → pré-rempli email/profil
- [ ] **Bouton physique GPIO** en plus du clavier (expérience plus tactile)
- [ ] **Ring light LED** piloté via GPIO (allume juste avant la capture)
- [ ] **Monitoring température Raspberry** pendant l'événement (alerte écran si > 75°C)

---

## Post-événement

- [ ] **Album PDF auto** de toutes les photos de la soirée (script cron nightly, `reportlab`)
- [ ] **Site web statique** généré en fin d'événement, photos classées par heure
- [ ] **Diaporama vidéo** (ffmpeg) : toutes les photos en musique
- [ ] **Rapport PDF au client** : stats + échantillon de montages
- [ ] **Sauvegarde différentielle** vers disque dur externe (backup avant de démonter)
- [ ] **Envoi batch** de tous les montages par email au marié / organisateur

---

## Effets image — expérimentaux

- [ ] **Mode GIF animé boomerang** — générer un GIF boucle en plus du strip (PIL `save_all=True, append_images=...`)
- [ ] **Stop-motion** à partir des preview frames capturés pendant le décompte (5 frames → GIF)
- [ ] **Beauty filter** (skin smoothing léger) — optionnel, activable dans config (OpenCV `bilateralFilter`)
- [ ] **Détection de visages** (OpenCV Haar / DNN) pour recadrer intelligemment
- [ ] **Auto-correction exposition** (CLAHE) — `cv2.createCLAHE` ou PIL
- [ ] **Remplacement de fond** (greenscreen) — nécessite tissu vert + OpenCV color keying
- [ ] **Effet miroir / kaléidoscope** pour mode fun
- [ ] **Grain / texture film** ajouté à la passe finale
- [ ] **Colorisation sélective** (N&B sauf rouge, par exemple)
- [ ] **Cartoonify / paint effect** via ImageMagick (`convert -paint 4` ou `-charcoal`)

---

## Références open-source à étudier

> **Ne pas fork** : étudier l'archi, piocher patterns + UI, mais garder ton code simple.
> Ton projet fait ~2000 lignes lisibles ; `photobooth-app` en fait ~30 000 + plugins.

### Photobooths open-source

- **PIBOOTH** — `github.com/pibooth/pibooth`
  - **Exactement ton stack** (Python + Pygame)
  - Système de plugins bien pensé (Google Photos upload, Dropbox, etc.)
  - Config via `.cfg` simple
  - Pas de web admin mais l'**archi plugins** est très inspirante
  - À étudier en premier

- **photobooth-app** — `github.com/photobooth-app/photobooth-app`
  - Python + FastAPI + Vue frontend
  - **Admin dashboard web très complet** : config live, stats, queue, plugins
  - Support Canon gphoto2 comme toi
  - Très proche de ce que tu veux construire (Event Network)
  - À étudier quand tu attaqueras l'admin web

- **Photobooth Project** (Reuter) — `github.com/PhotoboothProject/photobooth`
  - PHP + Node.js + Vue
  - Stack différente mais **design UI admin le plus léché**
  - Bon pour piocher des idées d'ergonomie

### WiFi + réseau

- **RaspAP** — `github.com/RaspAP/raspap-webgui`
  - Transforme un Raspberry en AP WiFi avec interface web d'admin
  - `hostapd` + `dnsmasq` + PHP
  - Peut s'installer à côté du photobooth, ou en **copier les scripts de config**
  - Référence incontournable pour la partie point WiFi

- **nodogsplash** — `github.com/nodogsplash/nodogsplash`
  - Captive portal pour redirection auto des invités connectés
  - Utilisé dans RaspAP

- **hostapd** + **dnsmasq** — stack DIY si RaspAP est overkill
  - `hostapd` = AP WiFi
  - `dnsmasq` = DHCP + DNS local

### Frameworks UI utiles

- **FastAPI** — backend Python moderne, docs auto, type hints natifs (plus adapté que Flask pour une API)
- **HTMX** — interactions web dynamiques sans framework JS (idéal pour admin simple)
- **Svelte** / **Vue** — si frontend plus riche nécessaire
- **Filebrowser** — `github.com/filebrowser/filebrowser` : référence pour une interface de galerie

---

## Features méta / admin

- [ ] **Remote admin dashboard** — webapp FastAPI sur le réseau local : stats temps réel, toggle imprimante on/off, déclencher maintenance
- [ ] **Mode self-service multi-stations** — 2 photobooths en parallèle qui partagent stockage + imprimante
- [ ] **Config live reload** — file watcher sur `config.py` ; modifications appliquées sans restart
- [ ] **Web-based config editor** — formulaire web qui édite `config.py` (remplace édition texte manuelle)
- [ ] **API d'export stats** — endpoint JSON pour feed dans Grafana ou similaire
- [ ] **Plugins system** à la PIBOOTH — permettre des extensions sans toucher au core

---

## Ne pas faire — avec rationale

| Item | Raison du skip |
|------|-------|
| **3.5** Cache preview frame caméra | Gain marginal (~5 ms/frame) pour complexité d'invalidation |
| **3.1** Capture async sans demande explicite | Le "SOURIEZ !" comble déjà le wait, restructurer la machine d'état pour 2s de plus n'en vaut pas la peine |
| **4.6 extraction UI totale** en tant que rewrite pur | 4 modules extraits suffisent. Le reste (UI helpers) nécessite restructurer tous les appels à `screen`/fonts, gros coût pour bénéfice invisible |
| **Frontend React complet** | Pygame reste le bon choix pour l'app cliente. React/Vue seulement pour l'admin web, pas pour remplacer l'UI kiosque |
| **Fork d'un autre photobooth** | Hériter de leur complexité pour toujours. Mieux vaut étudier et réimplémenter proprement |
| **Système de plugins complet** | Overkill tant que tu es seul dev. À reconsidérer si d'autres veulent contribuer |

---

## Brainstorm — notes libres

*Espace libre pour jeter des idées au fil de l'eau. Déplacer en sections ci-dessus si l'idée prend forme.*

- (vide)
