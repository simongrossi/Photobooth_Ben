# Design — Contrôle du kiosque depuis l'admin (volet 3/3)

**Date** : 2026-07-18 · **Statut** : validé (Simon).
**Volets** : 1 = refonte UI (livré) · 2 = assets kiosque (livré) · **3 = ce document**.

## Objectif

Piloter le kiosque depuis l'admin web (rôle admin uniquement) : redémarrer
l'appli, l'arrêter, redémarrer la machine. Prérequis : le kiosque tourne en
service systemd (`deploy/photobooth.service`, déjà dans le repo avec watchdog
anti-crash — jamais déployé sur la machine, aujourd'hui en autostart XFCE).

## Décisions validées

- 3 actions : **redémarrer kiosque**, **arrêter kiosque**, **redémarrer machine**.
  (« Démarrer » = le bouton Redémarrer : `systemctl restart` démarre un service
  arrêté.)
- **Pas** de redémarrage automatique 2 h (issue #20) : on attend le diagnostic
  `[PERF]` ; le watchdog systemd (`Restart=on-failure`) couvre déjà les crashs.
- Panneau visible **admin uniquement** ; viewer : rien à l'écran, 401 sur les POST.
- Redémarrage machine : double confirmation côté UI.

## Architecture

```
web/systeme.py                 ← module pur : liste blanche + exécution subprocess
web/routes/dashboard.py        ← routes POST /dashboard/systeme/<action> + état service
web/templates/dashboard.html   ← panneau « Contrôle du kiosque » (admin) + pastille santé
deploy/photobooth-admin-sudoers← règle sudoers (template @USER@)
deploy/install-admin.sh        ← installe/valide le sudoers (visudo -c)
deploy/photobooth-admin.service← fix : @PROJET_DIR@ au lieu de @HOME@/Photobooth_Ben
```

### `web/systeme.py`

```python
SERVICE_KIOSQUE = "photobooth.service"

ACTIONS = {
    "redemarrer-kiosque": ["sudo", "-n", "/usr/bin/systemctl", "restart", SERVICE_KIOSQUE],
    "arreter-kiosque":    ["sudo", "-n", "/usr/bin/systemctl", "stop", SERVICE_KIOSQUE],
    "redemarrer-machine": ["sudo", "-n", "/usr/bin/systemctl", "reboot"],
}

def executer_action(action: str) -> tuple[bool, str]:
    """Exécute une action de la liste blanche. (ok, message) ; ValueError si inconnue."""

def etat_kiosque() -> str:
    """'active' | 'inactive' | 'failed' | 'indisponible' via `systemctl is-active`
    (sans sudo). 'indisponible' si systemctl absent (dev Mac) ou timeout."""
```

- `subprocess.run(..., capture_output=True, timeout=10)` ; jamais de shell,
  jamais de commande construite depuis l'entrée utilisateur (l'action est une
  **clé** de dict, pas un fragment de commande).
- Échec sudo (`sudo -n` sans règle) → `(False, stderr)` affiché en flash.

### Routes (dashboard.py)

- `POST /dashboard/systeme/<action>` : `require_auth` ; clé inconnue → 404 ;
  flash succès/échec ; redirect dashboard. Cas spécial `redemarrer-machine` :
  flash « Redémarrage lancé — la machine revient dans ~1 minute ».
- `index()` : ajoute la pastille « Kiosque : actif/arrêté/en panne/N-A » au
  bandeau santé (`etat_kiosque()`, mappé ok/warn/err/na) et passe
  `actions_systeme` au gabarit.

### Gabarit

Panneau admin (`{% if role == 'admin' %}`) sous le bandeau santé : 3 boutons
avec `confirm()` (double `confirm()` pour la machine), note « ~10 s / ~1 min ».

## Sudoers (`deploy/photobooth-admin-sudoers`)

```
# Autorise UNIQUEMENT le contrôle du service kiosque par l'admin web.
@USER@ ALL=(root) NOPASSWD: /usr/bin/systemctl restart photobooth.service, /usr/bin/systemctl stop photobooth.service, /usr/bin/systemctl start photobooth.service, /usr/bin/systemctl reboot
```

`install-admin.sh` : substitue `@USER@`, écrit vers `/etc/sudoers.d/photobooth-admin`
via un fichier temporaire validé par `visudo -c -f` (jamais d'écriture directe
d'un sudoers invalide), `chmod 440`. Idempotent.

## Fix au passage

`deploy/photobooth-admin.service` : `WorkingDirectory`/chemins passent de
`@HOME@/Photobooth_Ben` (hardcodé — avait exigé un sed manuel sur la machine)
à `@PROJET_DIR@`, substitué par `install-admin.sh` comme le fait `install.sh`.

## Gestion d'erreurs

- systemctl absent (dev) : pastille « N/A », boutons présents mais l'action
  retourne un flash d'erreur propre.
- Règle sudoers manquante : `sudo -n` échoue immédiatement → flash avec stderr.
- Timeout subprocess (10 s) → flash d'erreur, pas de blocage du worker Flask.

## Tests (CI pure)

- `tests/test_web_systeme.py` : liste blanche (clé inconnue → ValueError/404),
  succès et échec avec `subprocess.run` monkeypatché, `etat_kiosque` mappé,
  systemctl absent → 'indisponible'.
- Routes : POST action valide (subprocess mocké) → redirect + flash ; action
  inconnue → 404 ; sans auth → 401 ; viewer ne voit pas « Contrôle du kiosque »
  dans le HTML, l'admin le voit.

## Migration de la machine (guidée, hors repo)

1. `git pull` puis `sudo ./deploy/install.sh` (crée + enable photobooth.service).
2. `rm ~/.config/autostart/photobooth.desktop` (fin de l'autostart XFCE).
3. `sudo ./deploy/install-admin.sh` (pose le sudoers ; env conservé).
4. `sudo reboot` — le kiosque revient via systemd. Réversible (recréer le .desktop).

## Hors périmètre

- Redémarrage périodique automatique (attend les données [PERF]).
- Actions supplémentaires (mise à jour git depuis l'admin, arrêt machine).
- Migration Wayland.
