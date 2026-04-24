# Interface admin web (optionnelle)

Service séparé du kiosque pygame, activable à la demande sur le Raspberry Pi.
Permet de piloter le photobooth depuis un navigateur (ordinateur ou mobile)
sur le même LAN, sans toucher au code.

- **Dashboard** : stats de sessions, état disque/CPU, dossier d'impression.
- **Galerie** : parcours des montages produits (10×15 et strips) avec
  miniatures à la volée.
- **Templates** : upload de PNG d'overlay, sélection du template actif par mode.
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
| Overlays PNG | `assets/overlays/*.png` | admin | kiosque (montage) |
| Overlay actif | `assets/overlays/10x15_overlay.png` et `strips_overlay.png` (copie du template activé) | admin | kiosque |
| Métadonnées templates | `data/admin.db` (SQLite) | admin | admin |
| Surcharges config | `data/config_overrides.json` | admin | kiosque (à chaque import de `config`) |

Le kiosque n'a **pas besoin** de connaître l'admin : les overrides sont lus au
démarrage de `config.py` via une whitelist stricte (voir
`config.py:_CONFIG_OVERRIDES_WHITELIST`).

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
4. Active le démarrage au boot.

Récupère le mot de passe dans `/etc/photobooth-admin.env`, puis ouvre
`http://<ip-du-pi>:8080` dans un navigateur.

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
- Impression : `ACTIVER_IMPRESSION`, `NOM_IMPRIMANTE_10X15`,
  `NOM_IMPRIMANTE_STRIP`.
- Effets : `WATERMARK_ENABLED`, `WATERMARK_TEXT`, `GRAIN_ENABLED`,
  `GRAIN_INTENSITE`, `STRIP_MODE_BURST`.
- Hardware : `ARDUINO_ENABLED`.
- Monitoring : `SEUIL_DISQUE_CRITIQUE_MB`, `SEUIL_TEMP_CRITIQUE_C`.
- Divers : `NB_MAX_IMAGES_SLIDESHOW`.

Les modifications s'appliquent **au prochain redémarrage du service
kiosque** :

```bash
sudo systemctl restart photobooth.service
```

## Sécurité

- **Basic Auth uniquement** — conçu pour un réseau d'événement privé. Pour
  exposer à Internet : reverse-proxy HTTPS + authentification plus robuste.
- Le mot de passe est en clair dans `/etc/photobooth-admin.env` (chmod 640,
  propriétaire `root:<user>`). Comparable à tout fichier de config prod.
- Upload de templates : extension `.png` uniquement + validation PIL
  (`Image.verify()`) pour rejeter les fichiers mal formés.
- Les chemins sont résolus et vérifiés contre path-traversal (`os.path.realpath`
  avec garde de racine).

## Désinstallation

```bash
sudo systemctl disable --now photobooth-admin.service
sudo rm /etc/systemd/system/photobooth-admin.service
sudo rm /etc/photobooth-admin.env
sudo systemctl daemon-reload
```

Les données restent (`data/admin.db`, `data/config_overrides.json`,
`assets/overlays/*`) — les supprimer manuellement si besoin.
