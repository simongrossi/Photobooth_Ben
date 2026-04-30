# Déploiement — fichiers d'infrastructure

Ressources pour installer le photobooth en **mode kiosque avec autostart +
watchdog** sur un Raspberry Pi. Tous les fichiers sont *versionnés avec le
projet* — plus besoin de copier-coller du heredoc depuis DEPLOYMENT.md.

| Fichier | Rôle |
|---|---|
| [photobooth.service](photobooth.service) | Unit systemd (template avec placeholders `@USER@` / `@HOME@`) |
| [kiosk.sh](kiosk.sh) | Wrapper de démarrage : désactive screensaver, cache curseur, lance Python |
| [install.sh](install.sh) | Installe `unclutter`, substitue les placeholders, active le service |
| [uninstall.sh](uninstall.sh) | Retire proprement le service systemd |

---

## Installation rapide

```bash
cd ~/Photobooth_Ben
sudo ./deploy/install.sh
sudo systemctl start photobooth.service
```

C'est tout. Le service démarrera désormais automatiquement au boot.

---

## Ce que le watchdog fait

Le service `photobooth.service` utilise :

- `Restart=on-failure` + `RestartSec=5` : redémarre 5 s après chaque crash
- `StartLimitBurst=5` / `StartLimitIntervalSec=60` : **5 crashs en 60 s → arrêt
  définitif** pour éviter la boucle infinie (cas d'un bug permanent). Rearm :
  `sudo systemctl reset-failed photobooth.service`
- `MemoryMax=1G` : kill + restart si le process dépasse 1 Go
- `TimeoutStopSec=30` : laisse 30 s au photobooth pour quitter proprement
  (close Arduino, ferme caméra) avant SIGKILL

Quitter avec **Échap** compte comme un exit propre → pas de relance.
Seul un crash ou un `kill -9` déclenche le watchdog.

---

## Ce que le mode kiosque fait

Le wrapper `kiosk.sh` :

1. Désactive l'économiseur d'écran et DPMS (`xset s off; xset -dpms`) — l'écran
   reste allumé pendant toute la soirée
2. Cache le curseur de souris (`unclutter -root -idle 0`)
3. Exporte `PHOTOBOOTH_KIOSK=1` → pygame passe en `FULLSCREEN | NOFRAME`
4. Active le venv et exec le Python principal

En dev local (sans `PHOTOBOOTH_KIOSK=1`), pygame reste en mode fenêtré standard
— le même code fonctionne des deux côtés.

### Limites connues

- Ne désactive **pas** les raccourcis OS (`Ctrl+Alt+F1..F7`, `Alt+Tab` du
  compositor) — trop intrusif et dépend du DE utilisé. Pour une isolation totale
  il faut un setup X minimal (`xinit` sans DE).
- Les raccourcis du clavier USB qui pourraient fermer la fenêtre (`Alt+F4`)
  sont conservés — utile pour la maintenance. Retirer physiquement le clavier
  en événement si besoin.

---

## Commandes de gestion courantes

```bash
# État + derniers logs
sudo systemctl status photobooth.service

# Logs temps réel (journald)
journalctl -u photobooth.service -f

# Logs fichier (append à chaque run)
tail -f ~/Photobooth_Ben/logs/systemd.log

# Redémarrage à chaud
sudo systemctl restart photobooth.service

# Arrêt propre
sudo systemctl stop photobooth.service

# Rearm après 5 crashs consécutifs
sudo systemctl reset-failed photobooth.service
```

Voir aussi [../docs/RUNBOOK.md](../docs/RUNBOOK.md) pour la checklist
événementiel complète (J-1 / J / J+1).

---

## Dépannage

**Le service ne démarre pas** : `journalctl -u photobooth.service -n 50` puis
chercher l'erreur. Causes fréquentes :
- `DISPLAY=:0` absent → le serveur X n'est pas démarré avant le service.
  Vérifier `After=graphical.target` dans le service.
- Permissions sur `/home/USER/.Xauthority` → le service tourne bien en tant
  que `USER` (pas root) ?
- Venv manquant → le projet doit avoir `.venv/bin/python3`. Sinon, installe-le
  ou `kiosk.sh` retombe sur `python3` système (suppose pygame apt).

**Curseur visible en événement** : `unclutter` pas lancé. Vérifier :
```bash
pgrep -af unclutter
```
Si absent, relancer manuellement : `unclutter -root -idle 0 &`.

**L'écran s'éteint après quelques minutes** : DPMS / screensaver réactivé par
le DE après le `xset` de `kiosk.sh`. Vérifier que le DE ne réinitialise pas ces
paramètres (Xfce Power Manager, gnome-screensaver…). Désactiver le daemon
concerné :
```bash
# Xfce
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/dpms-enabled -s false
```

---

## Test local (macOS / Linux dev)

`install.sh` et le service sont Linux/systemd uniquement. Sur macOS pour
tester le wrapper :

```bash
# Le wrapper s'exécute sans xset/unclutter (blocs `if command -v` tolérants)
./deploy/kiosk.sh
# → lance le photobooth en mode dev (PHOTOBOOTH_KIOSK=1 mais pygame passera
#   en fenêtré si l'env n'a pas de serveur X)
```

Pour tester en vrai, il faut un Raspberry Pi (ou toute machine systemd+X11).
