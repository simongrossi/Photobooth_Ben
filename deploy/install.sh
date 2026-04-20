#!/usr/bin/env bash
# install.sh — installe le service systemd photobooth + dépendances kiosque.
#
# À lancer UNE SEULE FOIS sur le Raspberry Pi cible, depuis le dossier du projet :
#   cd ~/Photobooth_Ben
#   sudo ./deploy/install.sh
#
# Ce que le script fait (idempotent — peut être relancé) :
# 1. Installe unclutter (cache du curseur) si absent
# 2. Substitue @USER@ et @HOME@ dans photobooth.service vers l'utilisateur qui
#    a invoqué sudo (SUDO_USER)
# 3. Copie le service dans /etc/systemd/system/
# 4. Active le service (démarrage au boot)
# 5. Affiche les commandes utiles pour la suite
#
# Le script NE démarre PAS le service immédiatement — c'est à toi de le faire :
#   sudo systemctl start photobooth.service

set -euo pipefail

# --- Garde-fous ---
if [[ "${EUID}" -ne 0 ]]; then
    echo "Ce script doit être lancé en sudo." >&2
    exit 1
fi

if [[ -z "${SUDO_USER:-}" ]]; then
    echo "SUDO_USER vide — lance via 'sudo ./deploy/install.sh' (pas en root direct)." >&2
    exit 1
fi

TARGET_USER="${SUDO_USER}"
TARGET_HOME="$(getent passwd "${TARGET_USER}" | cut -d: -f6)"
PROJET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${PROJET_DIR}" != "${TARGET_HOME}/Photobooth_Ben" ]]; then
    echo "⚠  Le projet n'est pas dans ${TARGET_HOME}/Photobooth_Ben." >&2
    echo "   Chemin détecté : ${PROJET_DIR}"
    echo "   Le service systemd utilise ce chemin fixe. Déplace le projet ou édite"
    echo "   le service manuellement après installation."
    read -rp "Continuer quand même ? [y/N] " reply
    [[ "${reply}" =~ ^[Yy]$ ]] || exit 1
fi

echo "→ Utilisateur cible : ${TARGET_USER}"
echo "→ Répertoire projet : ${PROJET_DIR}"
echo

# --- 1. Dépendances kiosque ---
if ! command -v unclutter >/dev/null 2>&1; then
    echo "→ Installation de unclutter (masquage curseur)..."
    apt update
    apt install -y unclutter
else
    echo "✓ unclutter déjà installé"
fi

# --- 2. Permissions kiosk.sh ---
chmod +x "${PROJET_DIR}/deploy/kiosk.sh"

# --- 3. Génération du service avec substitution ---
SERVICE_SRC="${PROJET_DIR}/deploy/photobooth.service"
SERVICE_DEST="/etc/systemd/system/photobooth.service"

echo "→ Génération de ${SERVICE_DEST}..."
sed \
    -e "s|@USER@|${TARGET_USER}|g" \
    -e "s|@HOME@|${TARGET_HOME}|g" \
    "${SERVICE_SRC}" > "${SERVICE_DEST}"

# --- 4. Activation systemd ---
echo "→ Rechargement systemd..."
systemctl daemon-reload
systemctl enable photobooth.service

# --- 5. Création du dossier logs (évite l'échec sur premier boot) ---
mkdir -p "${PROJET_DIR}/logs"
chown -R "${TARGET_USER}:${TARGET_USER}" "${PROJET_DIR}/logs"

echo
echo "✅ Installation terminée."
echo
echo "Commandes utiles :"
echo "  sudo systemctl start photobooth.service     # démarrer maintenant"
echo "  sudo systemctl status photobooth.service    # état + derniers logs"
echo "  sudo systemctl restart photobooth.service   # redémarrage à chaud"
echo "  sudo systemctl stop photobooth.service      # arrêt propre"
echo "  journalctl -u photobooth.service -f         # logs temps réel"
echo
echo "Pour désinstaller : sudo ./deploy/uninstall.sh"
