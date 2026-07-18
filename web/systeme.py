"""systeme.py — contrôle du service kiosque depuis l'admin web (liste blanche).

Trois actions fermées, exécutées via `sudo -n systemctl …` grâce à la règle
`/etc/sudoers.d/photobooth-admin` posée par deploy/install-admin.sh. L'action
est une CLÉ de dictionnaire — jamais un fragment de commande : impossible
d'injecter quoi que ce soit depuis la requête HTTP.

`etat_kiosque()` lit l'état du service sans sudo (`systemctl is-active`).
Sur une machine sans systemd (dev macOS), tout dégrade proprement :
état 'indisponible', actions en échec avec message clair.
"""
from __future__ import annotations

import shutil
import subprocess

SUDO_PATH = shutil.which("sudo") or "/usr/bin/sudo"
SYSTEMCTL_PATH = shutil.which("systemctl") or "/usr/bin/systemctl"
SERVICE_KIOSQUE = "photobooth.service"
TIMEOUT_S = 20

ACTIONS = {
    "redemarrer-kiosque": [SUDO_PATH, "-n", SYSTEMCTL_PATH, "restart", SERVICE_KIOSQUE],
    "arreter-kiosque":    [SUDO_PATH, "-n", SYSTEMCTL_PATH, "stop", SERVICE_KIOSQUE],
    "redemarrer-machine": [SUDO_PATH, "-n", SYSTEMCTL_PATH, "reboot"],
}

LIBELLES = {
    "redemarrer-kiosque": "Redémarrage du kiosque lancé (~10 s).",
    "arreter-kiosque": "Kiosque arrêté — relançable via « Redémarrer le kiosque ».",
    "redemarrer-machine": "Redémarrage de la machine lancé — de retour dans ~1 minute.",
}


def executer_action(action: str) -> tuple[bool, str]:
    """Exécute une action de la liste blanche. Retourne (ok, message utilisateur).

    Lève ValueError si l'action n'est pas dans la liste blanche (la route en
    fait un 404).
    """
    commande = ACTIONS.get(action)
    if commande is None:
        raise ValueError(f"Action système inconnue : {action!r}")
    try:
        resultat = subprocess.run(
            commande, capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"L'action a dépassé {TIMEOUT_S} secondes."
    except OSError as e:
        return False, f"Commande indisponible sur cette machine : {e}"
    if resultat.returncode == 0:
        return True, LIBELLES[action]
    detail = (resultat.stderr or resultat.stdout).strip()
    suffixe = f" ({detail[:200]})" if detail else ""
    return False, f"Échec de l'action{suffixe}. Vérifie la règle sudoers (install-admin.sh)."


def etat_kiosque() -> str:
    """'active' | 'inactive' | 'failed' | 'indisponible' (sans sudo)."""
    try:
        resultat = subprocess.run(
            [SYSTEMCTL_PATH, "is-active", SERVICE_KIOSQUE],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "indisponible"
    etat = (resultat.stdout or "").strip()
    return etat if etat in ("active", "inactive", "failed") else (etat or "indisponible")
