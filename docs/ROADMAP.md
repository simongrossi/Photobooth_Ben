# Roadmap — Photobooth Ben

> Items sérieux, actionnables, priorisés. Pour les idées en vrac (micro-touches UX,
> effets exotiques, hardware, features brainstorm), voir [IDEAS.md](IDEAS.md).

Dernière mise à jour : 2026-04-20

---

## État actuel

- **Stabilité** : fuites mémoire corrigées, retry caméra, débounce robuste, écrans d'erreur visibles
- **UX** : splash caméra, flash + son shutter, écran "Préparation...", confirmation abandon, slideshow d'attente
- **Architecture modulaire** : `camera.py`, `montage.py`, `printer.py`, `logger.py`, `status.py` extraits
- **Observabilité** : logging rotatif, `sessions.jsonl` metadata, script `status.py` pré-événement
- **Performance** : threading pour génération montage avec spinner, cache des surfaces statiques

---

## Court terme — 30 min chacun

- [ ] **5.3** Tests unitaires `MontageGenerator` (pytest sur images factices, isolé depuis `montage.py`)
- [ ] **5.6 suite** Monitoring espace disque **continu** pendant l'événement (actuellement : check seul au boot → alerte écran si < 500 Mo)
- [ ] **6.6** Script stats fin de soirée — parse `sessions.jsonl` → nb sessions, taux impression, durée moyenne, heure de pointe
- [ ] **4.8 suite** Externaliser les constantes restantes dans `config.py` : `(840, 540)`, `(1640, 1040)`, offsets `(30, 30)` / `(80, 80)`, `l_p = 520`
- [ ] **5.2** Migrer les `log_error()` explicites vers `log_info` / `log_warning` / `log_error` nommés (remplacer la détection auto par emoji)

---

## Moyen terme — 1 à 3 h chacun

### Architecture
- [ ] **4.6 finir** Extraire `LoaderAnimation` dans `loader.py` + UI helpers (`afficher_message_plein_ecran`, `ecran_erreur`, `splash_connexion_camera`, `executer_avec_spinner`) dans `ui.py` via un `UIContext` singleton
- [ ] Split en dossiers `core/` + `ui/` (après extraction complète des UI helpers)

### Features événementiel
- [ ] **Filtres preset image** — N&B, sépia, vintage/polaroid, HDR. PIL (`ImageEnhance` + `ImageFilter`) suffit. Écran de choix avant le décompte. Appliqués dans `MontageGenerator` avant sauvegarde
- [ ] **6.4** Galerie admin — touche cachée (F1) → grille des montages du jour, navigation flèches, retour Échap
- [ ] **6.5** Overlays thématiques sélectionnables (mariage, anniversaire, Noël...) — écran de choix avant le décompte
- [ ] Mode **burst** en strip — 3 photos auto sans validation intermédiaire (plus fluide)
- [ ] Mode **timer 10s** — compte à rebours sans appui clavier (pour groupes qui veulent tous être sur la photo)

### Robustesse
- [ ] **Watchdog `systemd`** — unit file `photobooth.service` qui relance si crash
- [ ] **Kiosk mode** — désactiver Alt+Tab, souris, raccourcis système ; plein écran forcé
- [ ] **Auto-upload nightly** vers NAS / Dropbox / Nextcloud après l'événement (cron job)

---

## Long terme — 3 h et plus

### Event Network (feature signature)

> Combine point WiFi partagé + QR code partage + admin web. Le photobooth devient une
> attraction réseau intégrée à l'événement. **À faire en dernier**, une fois tout le
> reste stabilisé.

**Architecture cible** :
1. Raspberry en **mode Access Point** (`hostapd` + `dnsmasq`) : SSID public `Mariage-Wifi` sans mot de passe
2. **Captive portal** (`nodogsplash`) : redirection auto vers la galerie web
3. **Mini-serveur FastAPI** sur port 80 : galerie temps réel, téléchargement direct
4. **QR code à l'écran après impression** → URL directe de leur montage
5. **Admin dashboard web** : stats live, toggle imprimante on/off, maintenance, config live

**Sous-tâches** :
- [ ] Installer/configurer `hostapd` + `dnsmasq` avec SSID event + DHCP local
- [ ] FastAPI app `server.py` : `/` galerie session, `/photo/<id>` télécharger, `/qr/<id>` générer QR
- [ ] Intégrer `qrcode` Python : affiche QR après impression
- [ ] Captive portal via `nodogsplash` ou redirection DNS catchall
- [ ] Certificat self-signed HTTPS (éviter warnings iOS)
- [ ] Admin dashboard : config live, stats temps réel, queue imprimante, déclencher maintenance
- [ ] Auth basique admin (PIN ou mot de passe simple)

**Effort total** : ~1 semaine de travail dédié.
**Inspirations** : voir [IDEAS.md § Références open-source](IDEAS.md#références-open-source-à-étudier) — `photobooth-app` et `RaspAP` notamment.

### Autres gros chantiers
- [ ] **Email / SMS delivery** — après impression, écran "Entrez votre email/numéro" (clavier virtuel tactile) → photo envoyée en PJ. Nécessite SMTP + formulaire
- [ ] **Multi-langue** (EN/FR/ES) — toutes les strings extraites dans `i18n/*.json`, toggle sur l'accueil
- [ ] **3.1 Capture HQ async** — subprocess.Popen + polling, UI fluide pendant les 2-3s de capture. Restructuration machine d'état DECOMPTE
- [ ] **Customisation branding par événement** — dossier `events/mariage-smith-2026/` qui surcharge assets + overlays + textes

---

## Principe général

**Toujours valider sur matos cible avant de continuer** — `py_compile` ne détecte pas les régressions visuelles ou les bugs d'intégration.

**Commits fréquents avec tags** pour bisect facile en cas de régression entre deux événements.

**Une idée ne monte en roadmap qu'une fois** :
1. Un cas d'usage réel identifié (pas juste "ce serait cool")
2. Un effort estimé crédible (<1 journée pour court/moyen terme)
3. Un chemin d'implémentation clair

Sinon elle reste dans [IDEAS.md](IDEAS.md).
