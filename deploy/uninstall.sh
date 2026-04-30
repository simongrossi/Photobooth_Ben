#!/usr/bin/env bash
# uninstall.sh — désinstalle le service systemd photobooth.
#
# Laisse unclutter installé (trivial à enlever manuellement : apt purge unclutter).
# Ne touche pas au code, aux logs ni aux données du projet.

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Ce script doit être lancé en sudo." >&2
    exit 1
fi

SERVICE="photobooth.service"

if systemctl is-active --quiet "${SERVICE}"; then
    echo "→ Arrêt du service..."
    systemctl stop "${SERVICE}"
fi

if systemctl is-enabled --quiet "${SERVICE}" 2>/dev/null; then
    echo "→ Désactivation du service..."
    systemctl disable "${SERVICE}"
fi

if [[ -f "/etc/systemd/system/${SERVICE}" ]]; then
    echo "→ Suppression de /etc/systemd/system/${SERVICE}..."
    rm -f "/etc/systemd/system/${SERVICE}"
fi

systemctl daemon-reload
systemctl reset-failed "${SERVICE}" 2>/dev/null || true

echo "✅ Désinstallation terminée. Le code et les données restent en place."
