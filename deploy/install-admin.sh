#!/usr/bin/env bash
# install-admin.sh — installe l'interface admin web OPTIONNELLE.
#
# À lancer si tu veux l'admin web, indépendamment de l'installation du
# kiosque principal (deploy/install.sh). Les deux services coexistent sans
# interférence.
#
#   cd ~/Photobooth_Ben
#   sudo ./deploy/install-admin.sh
#
# Ce que le script fait (idempotent) :
# 1. Installe python3-flask (ou pip install flask si apt absent)
# 2. Crée /etc/photobooth-admin.env avec un mot de passe aléatoire (une fois)
# 3. Substitue @USER@/@HOME@ dans photobooth-admin.service → /etc/systemd/system/
# 4. Enable + affiche les commandes utiles
#
# Pour désinstaller : sudo systemctl disable --now photobooth-admin.service
#                     sudo rm /etc/systemd/system/photobooth-admin.service
#                     sudo rm /etc/photobooth-admin.env

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Ce script doit être lancé en sudo." >&2
    exit 1
fi
if [[ -z "${SUDO_USER:-}" ]]; then
    echo "SUDO_USER vide — lance via 'sudo ./deploy/install-admin.sh'." >&2
    exit 1
fi

TARGET_USER="${SUDO_USER}"
TARGET_HOME="$(getent passwd "${TARGET_USER}" | cut -d: -f6)"
PROJET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "→ Utilisateur cible : ${TARGET_USER}"
echo "→ Projet            : ${PROJET_DIR}"
echo

# --- 1. Dépendance Flask ---
if ! python3 -c "import flask" 2>/dev/null; then
    echo "→ Installation de Flask..."
    if command -v apt >/dev/null 2>&1; then
        apt update
        apt install -y python3-flask
    else
        pip3 install flask
    fi
else
    echo "✓ Flask déjà installé"
fi

# --- 2. Fichier d'environnement avec mot de passe ---
ENV_FILE="/etc/photobooth-admin.env"
if [[ ! -f "${ENV_FILE}" ]]; then
    echo "→ Génération de ${ENV_FILE} avec un mot de passe aléatoire..."
    PASSWORD="$(openssl rand -base64 18 | tr -d '\n')"
    cat > "${ENV_FILE}" <<EOF
# Variables d'environnement du service photobooth-admin.
# Le mot de passe ci-dessous protège l'interface — conserve-le précieusement.
PHOTOBOOTH_ADMIN_PASS=${PASSWORD}
PHOTOBOOTH_ADMIN_PORT=8080
EOF
    chmod 640 "${ENV_FILE}"
    chown root:"${TARGET_USER}" "${ENV_FILE}"
    echo "  ✓ Mot de passe admin : ${PASSWORD}"
    echo "  (à noter ; relisible dans ${ENV_FILE})"
else
    echo "✓ ${ENV_FILE} déjà présent (mot de passe conservé)"
fi

# --- 3. Génération du service systemd ---
SERVICE_SRC="${PROJET_DIR}/deploy/photobooth-admin.service"
SERVICE_DEST="/etc/systemd/system/photobooth-admin.service"
echo "→ Génération de ${SERVICE_DEST}..."
sed \
    -e "s|@USER@|${TARGET_USER}|g" \
    -e "s|@HOME@|${TARGET_HOME}|g" \
    "${SERVICE_SRC}" > "${SERVICE_DEST}"

# --- 4. Dossier logs ---
mkdir -p "${PROJET_DIR}/logs"
chown -R "${TARGET_USER}:${TARGET_USER}" "${PROJET_DIR}/logs"

# --- 5. Activation ---
systemctl daemon-reload
systemctl enable photobooth-admin.service

echo
echo "✅ Installation de l'admin terminée."
echo
echo "Commandes utiles :"
echo "  sudo systemctl start photobooth-admin.service     # démarrer"
echo "  sudo systemctl status photobooth-admin.service    # état"
echo "  sudo systemctl restart photobooth-admin.service   # redémarrer"
echo "  sudo systemctl stop photobooth-admin.service      # arrêter"
echo
echo "Accès : http://<ip-du-pi>:8080"
echo "Identifiant : admin"
echo "Mot de passe : voir ${ENV_FILE}"
