# Roadmap — Photobooth Ben

> Items dev actionnables, priorisés. Pour les idées en vrac (micro-touches UX,
> effets exotiques, hardware, brainstorm), voir [IDEAS.md](IDEAS.md).
> Pour l'historique de ce qui a été fait, voir [CHANGELOG.md](CHANGELOG.md).

Dernière mise à jour : 2026-04-21 (post-TempMonitor)

---

## État actuel — fait ✅

**Stabilité & bugs** : fuites PIL corrigées, retry caméra + rate-limit, débounce robuste, écrans d'erreur visibles, except Exception typés.

**UX événementiel** : splash caméra, flash + shutter sound, beep décompte, écran "Préparation...", confirmation abandon, slideshow d'attente, compteur photo strip, mode burst.

**Architecture modulaire** : split en `core/` + `ui/` — `core/session` (Etat+SessionState+metadata), `core/monitoring` (DiskMonitor+slideshow), UIContext singleton, render functions extraites (DECOMPTE/VALIDATION/FIN/ACCUEIL), event handlers par état, MontageGenerator/CameraManager/PrinterManager encapsulés. `Photobooth_start.py` : 1183 → 1071 L.

**Hardware** : contrôleur Arduino Nano (`core/arduino.py`) — 3 boutons-poussoirs à LED intégrée via pyserial, pilotage LED selon `Etat`, fallback clavier si pyserial absent. Firmware `arduino/photobooth_buttons/`.

**Performance** : threading spinner génération montage, cache des surfaces statiques + ASSETS cache, capture HQ async (subprocess.Popen + polling), loader GC optim, purge temp + check disque continu, profiling mémoire (`profile_mem.py`, `profile.py`).

**Observabilité** : logging rotatif, `sessions.jsonl` metadata, `status.py` (diagnostic), `stats.py` (rapport avec histogramme horaire), monitoring disque avec bandeau rouge.

**Code quality** : `from config import *` → imports explicites (96 noms), dead code nettoyé, ruff clean, type hints sur classes publiques + docstrings, log_error → log_info/warning/critical.

**Tests & CI** : pytest (tests unitaires + intégration, `test_status.py`, `test_stats.py`, `test_integration.py`), GitHub Actions CI (`.github/workflows/ci.yml`), coverage (`pyproject.toml`), pre-commit hook (`.pre-commit-config.yaml`).

**Déploiement** : guide Raspberry Pi complet (`docs/DEPLOYMENT.md`), doc architecture (`docs/ARCHITECTURE.md`), doc Arduino (`docs/ARDUINO.md`), changelog (`docs/CHANGELOG.md`).

---

## Court terme — 30 min à 1 h chacun

### UX micro

_Les 3 items historiques (beep dernière seconde, filigrane strip, watermark)
sont livrés — voir [CHANGELOG.md](CHANGELOG.md) et [CONFIG.md](CONFIG.md)._

### Tests & qualité

- [ ] **Coverage `core/camera.py`** — à 0 % car cv2/gphoto2 absents en CI. Mocks complexes ou tests Pi-only (voir [TESTING.md](TESTING.md)). Global à 80 %, tout le reste ≥ 87 %.

### Optimisations rapides

_Monitoring température CPU livré — voir [CHANGELOG.md](CHANGELOG.md)._

---

## Moyen terme — 1 à 3 h chacun

### Features événementiel

- [ ] **Filtres preset image** — N&B, sépia, vintage/polaroid via `PIL.ImageEnhance` + `ImageFilter`. Écran de choix avant le décompte. Appliqués dans `MontageGenerator.final()`
- [ ] **6.4 Galerie admin** — touche cachée (F1) → grille des montages du jour, navigation flèches, retour Échap. Nouvel état `Etat.GALERIE`
- [ ] **6.5 Overlays thématiques** sélectionnables (mariage, anniversaire, Noël, Halloween...) — scan `assets/overlays/<theme>/`, écran choix avant décompte
- [ ] Mode **timer 10s** — compte à rebours sans appui clavier pour groupes (3e mode accueil ou toggle depuis strip/10x15)

### Robustesse & infra

- [ ] **Watchdog `systemd`** — unit file `photobooth.service` qui relance si crash
- [ ] **Kiosk mode** — désactiver Alt+Tab, souris, raccourcis système, plein écran forcé
- [ ] **Auto-upload nightly** vers NAS / Dropbox / Nextcloud (cron job rsync)

---

## Long terme — 3 h et plus

### Event Network (feature signature)

> Combine point WiFi partagé + QR code partage + admin web. Transforme le
> photobooth en attraction réseau intégrée. **À faire en dernier**, après
> stabilisation complète.

**Architecture cible** :
1. Raspberry en **mode Access Point** (`hostapd` + `dnsmasq`) : SSID public `Mariage-Wifi` sans mot de passe
2. **Captive portal** (`nodogsplash`) : redirection auto vers la galerie web
3. **Mini-serveur FastAPI** sur port 80 : galerie temps réel, téléchargement direct
4. **QR code à l'écran** après impression → URL directe du montage
5. **Admin dashboard web** : stats live, toggle imprimante, maintenance, config live

**Sous-tâches** :
- [ ] Install / config `hostapd` + `dnsmasq` avec SSID + DHCP local
- [ ] FastAPI app `server.py` : `/` galerie, `/photo/<id>`, `/qr/<id>`
- [ ] `qrcode` Python : affiche QR après impression (nouvel écran)
- [ ] Captive portal `nodogsplash` ou redirection DNS catchall
- [ ] Certificat self-signed HTTPS (éviter warnings iOS)
- [ ] Admin dashboard : config live, stats, queue imprimante, maintenance
- [ ] Auth basique admin (PIN ou mot de passe simple)

**Effort total** : ~1 semaine dédiée.
**Inspirations** : voir [IDEAS.md § Références open-source](IDEAS.md#références-open-source-à-étudier) — `photobooth-app` et `RaspAP` notamment.

### Autres gros chantiers

- [ ] **Email / SMS delivery** — après impression, écran "Entrez votre email/numéro" (clavier virtuel tactile) → photo envoyée en PJ. SMTP + formulaire
- [ ] **Multi-langue** (EN/FR/ES) — toutes les strings extraites dans `i18n/*.json`, toggle sur l'accueil
- [ ] **Branding par événement** — dossier `events/mariage-smith-2026/` qui surcharge assets + overlays + textes + config

---

## Principe général

**Toujours valider sur matos cible avant de continuer** — `py_compile` ne détecte pas les régressions visuelles ni les bugs d'intégration (caméra USB qui ne revient pas, imprimante qui bugge sur un papier, etc.).

**Commits fréquents avec tags** pour bisect facile en cas de régression entre deux événements.

**Une idée ne monte en roadmap qu'une fois** :
1. Cas d'usage réel identifié (pas juste "ce serait cool")
2. Effort estimé crédible (<1 jour pour court/moyen terme)
3. Chemin d'implémentation clair

Sinon elle reste dans [IDEAS.md](IDEAS.md).
