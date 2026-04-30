#!/usr/bin/env bash
# kiosk.sh — wrapper de démarrage kiosque pour le photobooth.
#
# Appelé par photobooth.service (systemd) ou directement depuis
# ~/.bashrc en mode console autologin + startx.
#
# Tâches :
# 1. Désactiver l'économiseur d'écran et le DPMS (écran reste allumé)
# 2. Cacher le curseur de souris (unclutter)
# 3. Désactiver les raccourcis système compositor (si xfce/lxqt présent)
# 4. Activer PHOTOBOOTH_KIOSK=1 (pygame lira FULLSCREEN + NOFRAME)
# 5. Charger le venv et exec Python
#
# Usage :
#   ./deploy/kiosk.sh               # lance le photobooth
#   PHOTOBOOTH_KIOSK=0 ./deploy/kiosk.sh   # force désactivation fullscreen

set -u

PROJET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${PROJET_DIR}/.venv/bin/python3"
MAIN_SCRIPT="${PROJET_DIR}/Photobooth_start.py"

# --- 1. Configuration X11 (tolérant si outils absents) ---
# `xset` : économiseur + DPMS off (l'écran ne doit jamais s'éteindre)
if command -v xset >/dev/null 2>&1; then
    xset s off 2>/dev/null || true
    xset -dpms 2>/dev/null || true
    xset s noblank 2>/dev/null || true
fi

# `unclutter` : cache le curseur de souris immédiatement
if command -v unclutter >/dev/null 2>&1; then
    # -root : cache sur tout l'écran. -idle 0 : cache immédiatement.
    # & pour laisser tourner en arrière-plan ; le PID mourra avec la session X.
    unclutter -root -idle 0 &
fi

# `xdotool` (optionnel) : désactive Ctrl+Alt+F1..F7 (TTY switching)
# Désactivation douce via désactivation des keybindings de Xfce/LXDE si présents.
# On ne touche pas aux raccourcis système OS-wide (trop intrusif).

# --- 2. Export du flag kiosque ---
export PHOTOBOOTH_KIOSK="${PHOTOBOOTH_KIOSK:-1}"

# --- 3. Lancement du photobooth ---
cd "${PROJET_DIR}"

if [[ -x "${VENV_PYTHON}" ]]; then
    exec "${VENV_PYTHON}" "${MAIN_SCRIPT}"
else
    # Fallback système si pas de venv installé
    exec python3 "${MAIN_SCRIPT}"
fi
