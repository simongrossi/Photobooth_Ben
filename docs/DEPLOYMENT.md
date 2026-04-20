# Déploiement sur Raspberry Pi

Guide pas-à-pas pour installer et lancer le photobooth sur un Raspberry en
mode kiosque. Testé avec Raspberry Pi 4 (4 Go) + Raspberry Pi OS bookworm
64-bit + Canon EOS 500D/750D + imprimante DNP DS-RX1/620.

---

## 1. Matériel requis

- **Raspberry Pi 4** (ou 5) avec alim 5 V / 3 A officielle
- **Carte microSD 32 Go** (classe 10 minimum)
- **Écran HDMI** 1280 × 800 ou 1920 × 1080
- **Clavier USB** (3 touches utilisées : G, M, D configurables dans `config.py`)
  — remplaçable (ou complété) par un **boîtier Arduino Nano 3 boutons à LED
  intégrée**, voir [`ARDUINO.md`](ARDUINO.md)
- **Canon EOS** compatible gphoto2 (cf. `http://www.gphoto.org/proj/libgphoto2/support.php`)
- **Imprimante DNP** (ou équivalent CUPS) en USB
- Câbles USB A-B + câble USB caméra

---

## 2. Raspberry Pi OS — install initial

1. Flasher la dernière **Raspberry Pi OS (64-bit) Bookworm** avec Raspberry Pi Imager
2. Dans l'imager : activer SSH + configurer user/mot de passe + SSID WiFi (domicile, pour le setup)
3. Booter le Raspberry, se connecter en SSH :
   ```bash
   ssh ton_user@raspberrypi.local
   ```
4. Mettre à jour :
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo reboot
   ```

---

## 3. Installer les dépendances système

```bash
sudo apt install -y \
    python3-pip python3-venv python3-dev \
    python3-pygame python3-numpy python3-pil \
    python3-gphoto2 gphoto2 libgphoto2-dev \
    cups cups-client libcups2-dev \
    python3-serial \
    git
```

> `python3-serial` est uniquement nécessaire si le boîtier Arduino est
> utilisé (voir [`ARDUINO.md`](ARDUINO.md)). Sinon, le photobooth se replie
> silencieusement sur le clavier.

### Vérification rapide

```bash
gphoto2 --version          # doit afficher >= 2.5
lpstat -r                  # "scheduler is running"
python3 --version          # >= 3.9
```

---

## 4. Configurer CUPS pour l'imprimante DNP

1. Brancher l'imprimante DNP en USB
2. Ouvrir `http://localhost:631` dans un navigateur (depuis le Raspberry ou via tunnel SSH `-L 631:localhost:631`)
3. Onglet **Administration** → **Add Printer** → sélectionner la DNP détectée
4. Installer les **drivers dnp-printer-driver** si nécessaire :
   ```bash
   sudo apt install printer-driver-dnp
   ```
5. Créer **deux files** avec les noms attendus par `config.py` :
   - `DNP_10x15` → format 6×4
   - `DNP_STRIP` → format 2×6 (bandelettes)
6. Pour chaque file : désactiver "Automatically reject jobs" et "Do not cache"

### Test d'impression

```bash
echo "test" | lp -d DNP_10x15     # doit imprimer une page de test
lpstat -p                          # listing des files, état
```

Si le nom de ta file est différent de `DNP_10x15` / `DNP_STRIP`, édite `config.py` :
```python
NOM_IMPRIMANTE_10X15 = "MaQueue10x15"
NOM_IMPRIMANTE_STRIP = "MaQueueStrip"
```

---

## 5. Cloner le projet et installer les dépendances Python

```bash
cd ~
git clone https://github.com/simongrossi/Photobooth_Ben.git
cd Photobooth_Ben
```

### Venv (recommandé)

```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install --upgrade pip
pip install Pillow pytest pytest-cov ruff
```

> **Note** : `--system-site-packages` permet au venv de voir les paquets système
> (pygame, gphoto2) déjà installés via apt. Évite de recompiler pygame dans le venv.

### Assets à déposer

Copier les assets graphiques dans `assets/` selon la structure attendue :

```
assets/
├── interface/
│   ├── background.jpg
│   ├── img_10x15.png
│   └── img_strip.png
├── backgrounds/
│   ├── 10x15_background.jpg
│   └── strips_background.jpg
├── overlays/
│   ├── 10x15_overlay.png
│   └── strips_overlay.png
├── fonts/
│   └── WesternBangBang-Regular.ttf
└── sounds/                    # optionnel
    ├── beep.wav
    ├── shutter.wav
    └── success.wav
```

---

## 6. Premier lancement — diagnostic

Avant de lancer le photobooth, exécuter le diagnostic :

```bash
cd ~/Photobooth_Ben
source .venv/bin/activate   # si venv utilisé
python3 status.py
```

**Tout doit être vert.** Si un item est rouge, corriger avant de continuer :
- ❌ Caméra → brancher/rebrancher USB, `gphoto2 --auto-detect` manuellement
- ❌ Imprimante → vérifier CUPS (`lpstat -p`, `cupsenable DNP_10x15`)
- ❌ Assets → vérifier la structure `assets/`
- ❌ Disque → libérer > 1 Go (`df -h`)

---

## 7. Lancement manuel du photobooth

```bash
cd ~/Photobooth_Ben
source .venv/bin/activate
python3 Photobooth_start.py
```

Tester le flux complet :
1. Accueil s'affiche → presser **G** (10x15) ou **D** (strip)
2. Presser **M** pour démarrer → décompte → capture
3. Validation → presser **M** pour imprimer → attendre → retour accueil
4. Quitter : **Alt+F4** ou `Ctrl+C` en SSH

### Vérifier les logs

```bash
tail -f logs/photobooth.log       # temps réel
cat data/sessions.jsonl            # historique des sessions
```

---

## 8. Auto-start au boot + watchdog + kiosque

Les fichiers d'infrastructure sont versionnés dans [`deploy/`](../deploy/) :

| Fichier | Rôle |
|---|---|
| [`deploy/photobooth.service`](../deploy/photobooth.service) | Unit systemd avec watchdog, limites mémoire, restart policy |
| [`deploy/kiosk.sh`](../deploy/kiosk.sh) | Wrapper démarrage : xset off, unclutter, PHOTOBOOTH_KIOSK=1, venv, exec |
| [`deploy/install.sh`](../deploy/install.sh) | Installe unclutter, substitue `@USER@` / `@HOME@`, enable service |
| [`deploy/uninstall.sh`](../deploy/uninstall.sh) | Retire le service proprement |

### 8.1 Installation

```bash
cd ~/Photobooth_Ben
sudo ./deploy/install.sh
sudo systemctl start photobooth.service
```

### 8.2 Watchdog

Le service `photobooth.service` embarque par défaut :

- `Restart=on-failure` + `RestartSec=5` : relance 5 s après chaque crash
- `StartLimitBurst=5` / `StartLimitIntervalSec=60` : **5 crashs en 60 s →
  arrêt définitif** (évite la boucle infinie). Rearm :
  `sudo systemctl reset-failed photobooth.service`
- `MemoryMax=1G` : kill + restart si fuite mémoire
- `TimeoutStopSec=30` : 30 s de grâce pour `SIGTERM` avant `SIGKILL`
  (permet la fermeture propre Arduino + caméra)

Quitter via **Échap** est un exit propre — pas de relance.

### 8.3 Mode kiosque

Le wrapper `kiosk.sh` :

- Désactive l'économiseur d'écran et DPMS (`xset s off; xset -dpms`)
- Cache le curseur (`unclutter -root -idle 0`)
- Exporte `PHOTOBOOTH_KIOSK=1` → pygame passe en `FULLSCREEN | NOFRAME`
  (voir `KIOSK_FULLSCREEN` dans [CONFIG.md](CONFIG.md))

En dev local (variable absente), pygame reste en mode fenêtré standard — même
code, deux environnements.

Pour les détails de maintenance et dépannage infra, voir
[`deploy/README.md`](../deploy/README.md).

---

## 10. Maintenance pendant l'événement

### Fichier status en un clin d'œil
```bash
python3 ~/Photobooth_Ben/status.py
```

### Voir les logs en direct
```bash
journalctl -u photobooth.service -f
# ou
tail -f ~/Photobooth_Ben/logs/photobooth.log
```

### Redémarrer le photobooth à chaud
```bash
sudo systemctl restart photobooth.service
```

### Arrêt propre
```bash
sudo systemctl stop photobooth.service
```

### Stats fin de soirée
```bash
cd ~/Photobooth_Ben && source .venv/bin/activate
python3 stats.py
python3 stats.py --date 2026-04-20   # filtre date
python3 stats.py --json > rapport.json
```

---

## 11. Troubleshooting courant

### Caméra non détectée

```bash
# Tuer les processus qui bloquent l'USB
sudo pkill -f gvfs-gphoto2-volume-monitor
sudo pkill -f gphoto2

# Retester
gphoto2 --auto-detect
```

Si toujours rien, vérifier `dmesg | tail` après branchement USB.

### Imprimante offline

```bash
lpstat -p                       # listing
cupsenable DNP_10x15           # si disabled
cancel -a DNP_10x15             # annuler les jobs bloqués
sudo systemctl restart cups
```

### Photobooth crashe au lancement

```bash
# Vérifier syntaxe
python3 -m py_compile Photobooth_start.py

# Voir la dernière erreur
tail -50 logs/systemd.log

# Lancer en foreground pour debug
sudo systemctl stop photobooth.service
cd ~/Photobooth_Ben && source .venv/bin/activate
python3 Photobooth_start.py
```

### Écran noir mais service "active (running)"

Problème de permissions X. Vérifier :
```bash
xhost +local:                   # autoriser l'accès local
echo $DISPLAY                   # doit être :0
```

### Performance dégradée (< 30 FPS)

Lancer le profile sur le matériel :
```bash
python3 profile.py 60           # 60 secondes d'usage
# Lire le rapport top 30 cumulatif
```

Si fuite mémoire suspectée :
```bash
python3 profile_mem.py 120      # 2 minutes avec multiples sessions
# Lire le top 30 des CROISSANCES (révèle les fuites)
```

---

## 12. Avant chaque événement — checklist pré-vol

- [ ] Raspberry allumé, connecté à l'écran
- [ ] Caméra branchée USB (pas via hub)
- [ ] Imprimante branchée + papier + cassette
- [ ] `python3 status.py` → tout vert
- [ ] Test capture manuelle (1 session 10x15 + 1 session strip)
- [ ] Vérifier que `logs/` et `data/` sont writables
- [ ] Espace disque > 2 Go libres
- [ ] Horloge système correcte (pour les timestamps de session)
- [ ] Si WiFi Event Network prévu : vérifier `hostapd` actif

---

## 13. Après l'événement

```bash
# Backup des sessions
cd ~/Photobooth_Ben
tar czf backup_event_$(date +%Y%m%d).tar.gz data/ logs/ assets/

# Stats
python3 stats.py --date $(date +%Y-%m-%d)

# Transférer vers NAS (exemple rsync)
rsync -avz data/print/ nas.local:/photos/events/$(date +%Y-%m-%d)/
```

---

## Ressources

- **Issues / questions** : https://github.com/simongrossi/Photobooth_Ben/issues
- **gphoto2 support** : http://www.gphoto.org/
- **CUPS docs** : https://www.cups.org/doc/
- **Raspberry Pi forums** : https://forums.raspberrypi.com/

Voir aussi [ARCHITECTURE.md](ARCHITECTURE.md) pour comprendre le code,
et [ROADMAP.md](ROADMAP.md) pour les évolutions prévues.
