# Runbook — Exploitation événementiel

Checklist opérationnelle pour faire tourner le photobooth sur un événement
réel. Pensée pour être suivie par quelqu'un qui n'a pas codé l'appli (déléguer
l'exploitation au jour J).

Pour l'installation initiale sur le Pi voir [DEPLOYMENT.md](DEPLOYMENT.md).
Pour la config voir [CONFIG.md](CONFIG.md).

---

## J-1 : préparation (30–45 min)

### 1. Matériel

- [ ] Raspberry Pi branché à l'écran HDMI (1280×800 ou 1920×1080)
- [ ] Canon EOS branché en USB — batterie chargée + alim secteur si possible
- [ ] Imprimante DNP branchée en USB + papier rempli + ruban frais
- [ ] Boîtier Arduino Nano branché en USB (si utilisé — voir [ARDUINO.md](ARDUINO.md))
- [ ] Clavier USB de secours (toujours le brancher, même si on compte sur l'Arduino)
- [ ] Alim Pi officielle 5 V / 3 A (pas une alim de téléphone)

### 2. Démarrage et diagnostic

```bash
cd ~/Photobooth_Ben
source .venv/bin/activate
python3 status.py
```

Tout doit être **vert**. Si rouge :

| Rouge | Action |
|---|---|
| Caméra | `gphoto2 --auto-detect` puis `sudo killall gvfs-gphoto2-volume-monitor` |
| Imprimante | `lpstat -p` + `lpstat -r`, relancer `cups` si nécessaire |
| Assets manquants | Re-copier depuis le repo (`git pull`) |
| Disque < 500 Mo | Purger `data/raw/` et `data/temp/` |
| Arduino | Voir [ARDUINO.md § Dépannage](ARDUINO.md) |

### 3. Test de bout en bout

- [ ] Lancer `python3 Photobooth_start.py` (ou `sudo systemctl start photobooth.service`)
- [ ] Faire 1 photo en mode **10×15** et vérifier qu'elle sort de l'imprimante
- [ ] Faire 1 série **strip** (3 photos) et vérifier la bandelette imprimée
- [ ] Vérifier les 3 **LEDs Arduino** si boîtier utilisé (pulsent sur accueil, vertes sur validation)
- [ ] Quitter proprement (Échap) → vérifier que `sessions.jsonl` est créé dans `data/`

### 4. Personnalisation événement

Si overlays ou fonds dédiés à l'événement :

- [ ] Remplacer `assets/backgrounds/10x15_background.jpg` et `strips_background.jpg`
- [ ] Remplacer `assets/overlays/10x15_overlay.png` et `strips_overlay.png` (format **RGBA** PNG)
- [ ] Vérifier dimensions : 1800×1200 (10×15) et 600×1800 (strip)
- [ ] Tester un tirage pour vérifier l'alignement

Si besoin d'ajuster un texte : éditer `config.py` section 7 (voir
[CONFIG.md § 7. Textes](CONFIG.md#7-textes-localisation)).

### 5. Sauvegardes

- [ ] Noter le nom de la branche git et le commit courant : `git log -1 --oneline`
- [ ] Si modifs locales (overlays événement) : `git status` et éventuel commit sur branche dédiée
- [ ] Idéalement, **tag git** `event-YYYY-MM-DD-lieu` pour rollback facile

---

## Jour J : pendant l'événement

### Lancement

```bash
sudo systemctl start photobooth.service    # si systemd configuré (via deploy/install.sh)
# OU
python3 Photobooth_start.py                # manuel
```

Si le service systemd a été installé (`sudo ./deploy/install.sh`), il démarrera
**automatiquement au boot** avec watchdog et mode kiosque. Voir
[deploy/README.md](../deploy/README.md).

### Surveillance discrète

Toutes les 30–60 min, vérifier du coin de l'œil :

- [ ] **Bandeau rouge en bas** = disque < 500 Mo → purger `data/temp/`
- [ ] **"Appareil photo non détecté — mode dégradé"** → replugger USB caméra
  (le mode dégradé fonctionne mais sans photo réelle)
- [ ] **Queue d'impression** : regarder la pile de photos qui sort — si rien ne sort
  alors que des impressions sont lancées, `lpstat -o` pour voir les jobs CUPS
- [ ] **Papier & ruban** de l'imprimante DNP (un pack = ~400 tirages selon format)

### En cas de blocage total

```bash
# Relancer proprement
sudo systemctl restart photobooth.service

# OU si lancé manuellement : Échap pour quitter, puis relancer
```

Si systemd affiche `Failed with result 'exit-code'` et refuse de relancer
(5 crashs en 60 s — limite du watchdog) :

```bash
sudo systemctl reset-failed photobooth.service
sudo systemctl start photobooth.service
```

Ne **pas** couper l'alim du Pi brutalement sauf nécessité — attendre un retour
à l'accueil si possible.

### Problèmes typiques

| Symptôme | Cause probable | Action |
|---|---|---|
| Écran figé sur "Connexion à l'appareil photo" > 10 s | gvfs monopolise la caméra | `sudo killall gvfs-gphoto2-volume-monitor` |
| Photo prise mais imprimante silencieuse | File CUPS bloquée | `lpstat -o` → `cancel -a` → relancer print |
| Boutons Arduino inertes | Port série changé | Vérifier `ls /dev/ttyUSB*` → ajuster `ARDUINO_PORT` → redémarrer |
| Lenteur inhabituelle | Disque plein, RAM pleine | `df -h`, `free -h` — purger `data/temp/` |
| Couleurs d'impression fades | Ruban en fin de vie | Remplacer le pack DNP |

---

## J+1 : après l'événement

### 1. Arrêt propre

- [ ] Quitter l'appli (Échap) ou `sudo systemctl stop photobooth.service`
- [ ] Débrancher l'alim de l'imprimante (prolonge la durée de vie du ruban)
- [ ] Éteindre le Pi proprement : `sudo shutdown now`

### 2. Statistiques & archivage

```bash
cd ~/Photobooth_Ben
source .venv/bin/activate

# Rapport du jour
python3 stats.py --date YYYY-MM-DD

# Export JSON pour archivage
python3 stats.py --date YYYY-MM-DD --json > ~/archives/event-YYYY-MM-DD.json
```

Chiffres intéressants : nombre total de sessions, répartition 10×15 vs strip,
histogramme horaire (pic d'affluence), temps moyen d'une session.

### 3. Récupération des photos

Les originaux sont dans `data/raw/`, les montages imprimés dans
`data/print/print_10x15/` et `data/print/print_strip/`. Pour archiver :

```bash
# Vers un NAS
rsync -avh data/ user@nas:/path/photobooth-YYYY-MM-DD/

# Vers une clé USB
rsync -avh data/ /media/usb/photobooth-YYYY-MM-DD/
```

### 4. Nettoyage

Une fois l'archivage validé :

```bash
rm -rf data/raw/*           # ~100 Mo par 100 photos
rm -rf data/temp/*          # temporaires
rm -rf data/print/*/*.jpg   # montages (déjà archivés)
# NE PAS supprimer data/sessions.jsonl avant d'avoir vérifié les stats !
```

### 5. Retour d'expérience

Noter dans [IDEAS.md](IDEAS.md) ou une issue :
- Ce qui a marché / pas marché
- Features demandées par les invités
- Bugs rencontrés (+ conditions de reproduction)

Ça alimente le [ROADMAP.md](ROADMAP.md) pour le prochain événement.

---

## Contacts de secours / numéros utiles

_(À renseigner selon l'événement — à garder sur papier à côté du setup)_

- Technicien sur place : _______________
- Loueur imprimante / consommables DNP : _______________
- Numéro personnel du photographe : _______________

---

## Annexe : kit de survie en clé USB

À préparer une fois pour toutes, à garder dans le flight case :

- [ ] Image SD de secours du Pi (`dd if=/dev/mmcblk0 of=pi-backup.img`)
- [ ] Copie du repo git (clone + venv déjà installé)
- [ ] Clavier USB de secours
- [ ] Câble USB caméra de secours
- [ ] Ruban + papier DNP de spare
- [ ] Alim Pi de spare
- [ ] Cable HDMI de spare
- [ ] Ce runbook imprimé
