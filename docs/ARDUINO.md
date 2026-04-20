# Arduino Nano — 3 boutons-poussoirs à LED intégrée

Guide complet pour brancher, flasher et utiliser le boîtier de 3 gros boutons
lumineux qui pilote le photobooth. L'Arduino remplace (ou complète) le clavier :
le module Python `core/arduino.py` injecte des événements `pygame.KEYDOWN` pour
chaque bouton pressé, et en retour pilote les LEDs intégrées selon l'état de
la session (accueil, validation, confirmation d'abandon, etc.).

- Fichiers concernés :
  - `arduino/photobooth_buttons/photobooth_buttons.ino` — firmware Arduino
  - `core/arduino.py` — contrôleur côté Python (thread série + injection pygame)
  - `config.py` — clefs `ARDUINO_ENABLED`, `ARDUINO_PORT`, `ARDUINO_BAUDRATE`

---

## 1. Matériel

| Élément | Quantité | Remarques |
|---|---|---|
| Arduino Nano (ATmega328P, clone CH340 ou original FTDI) | 1 | USB-B mini ou USB-C selon clone |
| Bouton-poussoir **vert** (central) avec LED intégrée 5 V | 1 | "momentary push-button with integrated LED" |
| Bouton-poussoir **rouge** (petit) | 1 | idem |
| Bouton-poussoir **blanc** (petit) | 1 | idem |
| Résistances 220 Ω (ou 330 Ω selon LED) | 3 | en série avec chaque anode de LED |
| Fils de raccordement + câble USB Nano↔Raspberry/PC | — | |

> ⚠ Vérifier la **tension nominale** des LEDs intégrées. Beaucoup de boutons
> industriels ont une LED **12 V** avec résistance interne ; ceux-là ne peuvent
> pas être pilotés directement par une sortie 5 V de l'Arduino. Acheter des
> boutons explicitement **5 V** pour ce projet, ou prévoir un étage MOSFET.

### Affectation des couleurs

Le photobooth affecte visuellement ces couleurs aux textes du bandeau bas :

| Position | Texte typique | Couleur UI (code) | LED recommandée |
|---|---|---|---|
| Gauche  | "Accueil" / "Reprendre" | **blanc** (`COULEUR_TEXTE_G`) | blanc |
| Milieu  | "IMPRIMER" / "Valider" | **vert** (`COULEUR_TEXTE_M`)  | vert  |
| Droite  | "Supprimer" / "Annuler" | **rouge** (`COULEUR_TEXTE_D`) | rouge |

> 💡 Dans la demande initiale, la disposition prévue était *rouge à gauche /
> blanche à droite*. C'est l'inverse de ce que l'UI affiche à l'écran. Pour
> éviter toute confusion côté utilisateur, **monter le bouton blanc à gauche
> et le rouge à droite** (ou swapper les couleurs de texte dans `config.py`
> aux clefs `COULEUR_TEXTE_G` / `COULEUR_TEXTE_D`).

---

## 2. Câblage

```
   Arduino Nano                            Boîtier 3 boutons
  ┌──────────────┐
  │         D2   ├───────────────── NO ─── bouton GAUCHE (blanc) ─── GND
  │         D3   ├───────────────── NO ─── bouton MILIEU (vert)  ─── GND
  │         D4   ├───────────────── NO ─── bouton DROITE (rouge) ─── GND
  │              │
  │         D5   ├──[ 220 Ω ]────── anode LED GAUCHE
  │         D6   ├──[ 220 Ω ]────── anode LED MILIEU
  │         D9   ├──[ 220 Ω ]────── anode LED DROITE
  │              │                  cathodes LED ───────────────────── GND
  │        GND   ├─────────────────────────────────────────────────── GND commun
  │              │
  │    USB ──────┴── vers Raspberry Pi / PC ── alimentation + série
  └──────────────┘
```

### Détails techniques

- **Boutons** : entrée `INPUT_PULLUP` dans le firmware → pas de résistance
  de tirage externe. Le circuit est bouclé au GND par le poussoir, appui =
  niveau bas. Un anti-rebond logiciel (30 ms) filtre les parasites.
- **LEDs** : sorties PWM (broches 5, 6, 9 du Nano) pour permettre la
  respiration douce (`PULSE`). Résistance série 220 Ω pour une LED rouge 5 V
  (~15 mA), ajuster à 330 Ω pour une LED blanche ou verte si elle tire trop.
- **Alimentation** : l'USB du Raspberry/PC alimente l'Arduino. Aucun besoin
  de bloc secteur séparé si la consommation des 3 LEDs reste < 200 mA.
- **Masses** : **toutes les masses doivent être communes**. Celle des boutons,
  celle des LEDs, celle du Nano.

### Schéma des 4 bornes d'un bouton à LED intégrée

Un bouton-poussoir lumineux type *DS-212* ou équivalent expose 4 cosses :

```
  NO ── contact, ouvert au repos ┐
                                 │ gérés côté Arduino (D2/D3/D4 + GND)
 COM ── commun du contact       ┘

  + ── anode LED (via résistance) ┐
                                  │ gérés côté Arduino (D5/D6/D9 + GND)
  – ── cathode LED                ┘
```

Les 4 cosses sont indépendantes (le bouton *n'allume pas* automatiquement
la LED quand il est pressé — c'est le firmware qui s'en charge, ce qui
permet de faire respirer la LED même sans appui).

---

## 3. Flasher le firmware

### 3.1 Avec Arduino IDE (simple)

1. Installer [Arduino IDE 2.x](https://www.arduino.cc/en/software).
2. Si Nano clone CH340, installer le pilote CH340 (macOS / Windows).
3. Ouvrir `arduino/photobooth_buttons/photobooth_buttons.ino`.
4. **Tools → Board** : `Arduino Nano`.
5. **Tools → Processor** : `ATmega328P` (ou `ATmega328P (Old Bootloader)`
   sur certains clones — essayer l'autre si l'upload échoue avec
   `avrdude: stk500_recv(): programmer is not responding`).
6. **Tools → Port** : sélectionner le port du Nano.
7. **Sketch → Upload** (⌘U / Ctrl+U).

Au boot, les 3 LEDs clignotent chacune 200 ms (auto-test), puis le firmware
envoie `READY\n` sur le port série.

### 3.2 Avec arduino-cli (headless, idéal Raspberry)

```bash
# Installation (une fois)
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
./bin/arduino-cli core update-index
./bin/arduino-cli core install arduino:avr

# Compilation + flash
./bin/arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 arduino/photobooth_buttons
./bin/arduino-cli upload  --fqbn arduino:avr:nano:cpu=atmega328 \
    -p /dev/ttyUSB0 arduino/photobooth_buttons
```

> Remplacer `cpu=atmega328` par `cpu=atmega328old` si le clone Nano utilise
> l'ancien bootloader (symptôme : upload qui timeout).

---

## 4. Configuration côté Python

Dans `config.py` :

```python
ARDUINO_ENABLED   = True
ARDUINO_PORT      = "/dev/ttyUSB0"   # adapter selon l'OS (voir plus bas)
ARDUINO_BAUDRATE  = 115200
```

### Trouver le bon port

| OS | Commande | Valeur typique |
|---|---|---|
| Raspberry Pi / Linux | `ls /dev/ttyUSB* /dev/ttyACM*` | `/dev/ttyUSB0` (CH340) ou `/dev/ttyACM0` (FTDI) |
| macOS | `ls /dev/tty.usb*` | `/dev/tty.usbserial-XXXX` ou `/dev/tty.usbmodemXXXX` |
| Windows | Gestionnaire de périphériques → *Ports (COM et LPT)* | `COM3`, `COM4`, ... |

### Permissions série (Linux / Raspberry)

Sans action, `/dev/ttyUSB0` appartient à `root:dialout` et n'est pas accessible
au user courant :

```bash
sudo usermod -a -G dialout $USER
# Se déconnecter/reconnecter (ou reboot) pour que le groupe soit effectif.
```

### Dépendance Python

Ajouter **pyserial** :

```bash
pip install pyserial
# ou, sur Raspberry Pi OS :
sudo apt install python3-serial
```

Si `pyserial` n'est pas installé, le contrôleur se désactive silencieusement
(warning au démarrage) et le photobooth reste pilotable au clavier.

---

## 5. Protocole série

**115200 bauds, 8N1, LF (`\n`) en fin de trame.**
`\r` est toléré et ignoré côté Arduino.

### Arduino → PC (émis par le firmware)

| Trame      | Sens                                              |
|------------|---------------------------------------------------|
| `READY`    | Boot terminé, firmware prêt.                      |
| `L`        | Bouton **gauche** pressé (front descendant).      |
| `M`        | Bouton **milieu** pressé.                         |
| `R`        | Bouton **droit** pressé.                          |
| `PONG`     | Réponse à une commande `PING`.                    |

Côté Python, `ArduinoController._handle_line()` route les 3 presses vers
`pygame.event.post(KEYDOWN, key=TOUCHE_*)`. Le reste du code (handlers
d'événements) ne voit aucune différence entre un appui clavier et un appui
Arduino.

### PC → Arduino (commandes reçues)

| Trame                 | Effet                                            |
|-----------------------|--------------------------------------------------|
| `LED:L:OFF`           | Éteint la LED gauche.                            |
| `LED:L:ON`            | Allume à pleine intensité.                       |
| `LED:L:PULSE`         | Respiration douce 0.25 Hz (invitation à presser).|
| `LED:L:FAST`          | Clignotement rapide 4 Hz (alerte / confirmation).|
| `LED:M:…` / `LED:R:…` | Idem pour les LEDs milieu / droite.              |
| `LED:ALL:OFF`         | Éteint les 3 LEDs d'un coup (raccourci).         |
| `PING`                | Test de liaison (le firmware répond `PONG`).     |

### Pilotage automatique des LEDs selon l'état

`ArduinoController.tick(etat, mode_actuel, abandon_armed)` est appelée une
fois par frame. Elle ne parle sur le port série que lors des **transitions**
(elle mémorise la dernière signature envoyée), donc le coût à 30 FPS est nul.

| État (`Etat.value`) | Gauche | Milieu | Droite |
|---|---|---|---|
| `ACCUEIL` (sans mode)       | `PULSE` | `OFF`   | `PULSE` |
| `ACCUEIL` (mode choisi)     | `ON`    | `PULSE` | `ON`    |
| `DECOMPTE`                  | `OFF`   | `OFF`   | `OFF`   |
| `VALIDATION`                | `ON`    | `PULSE` | `ON`    |
| `FIN` (abandon non armé)    | `ON`    | `PULSE` | `ON`    |
| `FIN` (confirmation armée)  | `OFF`   | `OFF`   | `FAST`  |

Modifier cette mapping dans `ArduinoController.tick()` si le feedback
lumineux doit changer.

---

## 6. Test manuel (sans lancer le photobooth)

Tester la liaison avec `screen` ou `miniterm` après avoir flashé :

```bash
# Linux/macOS
screen /dev/ttyUSB0 115200
# puis taper (sans guillemets) :
#   PING       → le Nano doit répondre PONG
#   LED:M:PULSE → la LED verte centrale se met à respirer
#   LED:ALL:OFF → tout s'éteint
# Appuyer sur les boutons : lire L, M ou R dans le terminal.
# Quitter : Ctrl+A puis K, puis Y.
```

Avec `miniterm` (fourni par pyserial) :

```bash
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

---

## 7. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| Log `Arduino : pyserial non installé` | `pyserial` absent | `pip install pyserial` |
| Log `ouverture /dev/ttyUSB0 échouée (Permission denied)` | User pas dans `dialout` | `sudo usermod -a -G dialout $USER` + relogin |
| Log `ouverture ... échouée ([Errno 2] No such file...)` | Mauvais nom de port | Lister (`ls /dev/tty*`) et corriger `ARDUINO_PORT` |
| Aucun bouton ne répond, mais `READY` apparaît | Fils NO/GND inversés ou contact défaillant | Vérifier au multimètre la continuité à l'appui |
| LEDs ne s'allument jamais | Anode/cathode inversées, ou LED 12 V | Tester avec `LED:L:ON` dans miniterm ; contrôler la tension nominale |
| Les appuis génèrent plusieurs L/M/R par pression | Anti-rebond insuffisant | Augmenter `DEBOUNCE_MS` dans le firmware (30 → 50 ms) |
| Upload `avrdude: stk500_recv(): programmer is not responding` | Bootloader incorrect | IDE → Tools → Processor → essayer **ATmega328P (Old Bootloader)** |
| L'Arduino se reset à chaque ouverture du port | Comportement normal (DTR toggle) | Le contrôleur attend 2.5 s avant d'écrire — ne pas réduire ce délai |

---

## 8. Checklist déploiement Raspberry Pi

Sur le Pi final :

- [ ] `sudo apt install python3-serial`
- [ ] User du photobooth ajouté au groupe `dialout`
- [ ] Firmware flashé via `arduino-cli` (ou clone d'une install locale)
- [ ] `ARDUINO_PORT` dans `config.py` vérifié (`ls /dev/ttyUSB*`)
- [ ] Test manuel `miniterm` : `PING` → `PONG`, appuis → `L`/`M`/`R`
- [ ] Lancement du photobooth : log `🎛  Arduino connecté sur /dev/ttyUSB0 @ 115200 bauds.`
- [ ] Sur l'accueil, les 2 LEDs latérales respirent → on sait que le `tick()` passe
- [ ] Appuyer sur chaque bouton → transition d'état visible à l'écran (comme au clavier)

---

## 9. Extensions futures possibles

- **Son de retour** côté Arduino (buzzer piézo sur une 4e broche) pour retour
  tactile même sans haut-parleur.
- **Commande `BRIGHT:<0..255>`** pour moduler la luminosité max (utile en
  extérieur vs ambiance tamisée).
- **Remontée `RELEASE`** des boutons (front montant) si on veut supporter
  des appuis longs côté Python (double-press déjà géré pour `DUREE_CONFIRM_ABANDON`
  mais uniquement en mesurant l'écart entre 2 appuis).
- **Watchdog série** côté Python : si plus de `PONG` après X secondes, tenter
  une reconnexion automatique plutôt que de rester inerte.
