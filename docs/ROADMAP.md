# Roadmap — Photobooth Ben

> Items dev actionnables, priorisés. Pour les idées en vrac (micro-touches UX,
> effets exotiques, hardware, brainstorm), voir [IDEAS.md](IDEAS.md).
> Pour l'historique de ce qui a été fait, voir [CHANGELOG.md](CHANGELOG.md).

Dernière mise à jour : 2026-07-14 (options de veille et d'impressions multiples)

---

## État actuel — fait ✅

**Stabilité & bugs** : fuites PIL corrigées, retry caméra + rate-limit, débounce robuste, écrans d'erreur visibles, except Exception typés.

**UX événementiel** : splash caméra, flash + shutter sound, beep décompte, écran "Préparation...", confirmation abandon, slideshow d'attente désactivable, compteur photo strip, mode burst et impressions multiples désactivables.

**Architecture modulaire** : split en `core/` + `ui/` — `core/session` (Etat+SessionState+metadata), `core/monitoring` (DiskMonitor+slideshow), UIContext singleton, render functions extraites (DECOMPTE/VALIDATION/FIN/ACCUEIL), event handlers par état, MontageGenerator/CameraManager/PrinterManager encapsulés. `Photobooth_start.py` est importable sans lancer le kiosque ; `main()` initialise le runtime.

**Hardware** : contrôleur Arduino Nano (`core/arduino.py`) — 3 boutons-poussoirs à LED intégrée via pyserial, pilotage LED selon `Etat`, fallback clavier si pyserial absent. `core/camera.py` dégrade proprement si `gphoto2`/`cv2`/`numpy`/`pygame` manque. Firmware `arduino/photobooth_buttons/`.

**Performance** : threading spinner génération montage, cache des surfaces statiques + ASSETS cache, capture HQ async (subprocess.Popen + polling), loader GC optim, purge temp + check disque continu, profiling mémoire (`profile_mem.py`, `profile.py`).

**Observabilité** : logging rotatif, `sessions.jsonl` metadata, `status.py` (diagnostic), `stats.py` (rapport avec histogramme horaire), monitoring disque avec bandeau rouge.

**Code quality** : `from config import *` → imports explicites (96 noms), dead code nettoyé, ruff clean, type hints sur classes publiques + docstrings, log_error → log_info/warning/critical.

**Tests & CI** : pytest (tests unitaires + intégration, `test_status.py`, `test_stats.py`, `test_integration.py`), GitHub Actions CI (`.github/workflows/ci.yml`), coverage (`pyproject.toml`), pre-commit hook (`.pre-commit-config.yaml`).

**Déploiement** : guide Raspberry Pi complet (`docs/DEPLOYMENT.md`), doc architecture (`docs/ARCHITECTURE.md`), doc Arduino (`docs/ARDUINO.md`), changelog (`docs/CHANGELOG.md`).

**Admin web optionnelle** (v1) : service systemd séparé (`photobooth-admin.service`), Flask + SQLite, Basic Auth. Dashboard stats, galerie `data/print/`, upload/activation de templates overlays, éditeur d'un sous-ensemble whitelisté de `config.py` (20 clés via `data/config_overrides.json`). Isolation stricte — `web/*` n'importe jamais `Photobooth_start` ni `ui/*`. Voir [ADMIN.md](ADMIN.md).

**Éditeur templates 10×15 et strip** : composition visuelle fond → photo(s) →
overlay, déplacement/redimensionnement par template et aperçu kiosque identique
au rendu final. Les trois zones strip sont réglables indépendamment.

**Gestion événementielle** : événements nommés avec dates et tags, activation
exclusive partagée à chaud avec le kiosque, instantané dans chaque session,
filtres dashboard/galerie, compatibilité « Sans événement » et export ZIP/CSV.

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
  avec sudoers ciblé, bouton « redémarrer kiosque », queue imprimante et logs
  systemd (export CSV événement déjà livré).
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
- [ ] **Branding par événement** — rattacher automatiquement les templates,
  fonds et textes au registre d'événements désormais livré.

---

## Principe général

**Toujours valider sur matos cible avant de continuer** — `py_compile` ne détecte pas les régressions visuelles ni les bugs d'intégration (caméra USB qui ne revient pas, imprimante qui bugge sur un papier, etc.).

**Commits fréquents avec tags** pour bisect facile en cas de régression entre deux événements.

**Une idée ne monte en roadmap qu'une fois** :
1. Cas d'usage réel identifié (pas juste "ce serait cool")
2. Effort estimé crédible (<1 jour pour court/moyen terme)
3. Chemin d'implémentation clair

Sinon elle reste dans [IDEAS.md](IDEAS.md).
