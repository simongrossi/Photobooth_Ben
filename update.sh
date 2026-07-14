#!/bin/bash
# Script de mise à jour et de redémarrage des services du Photobooth

set +e

echo "=== Mise à jour du Photobooth depuis GitHub ==="
git fetch origin
git checkout main
git pull origin main

echo ""
echo "=== Redémarrage des services systemd ==="

# Gestion de photobooth.service (écran)
if [[ $(systemctl show -p LoadState photobooth.service 2>/dev/null) == "LoadState=loaded" ]]; then
    echo "Redémarrage de l'application Photobooth (écran)..."
    sudo systemctl restart photobooth.service
else
    echo "ℹ photobooth.service n'est pas installé sous systemd (non trouvé)."
    echo "Recherche d'une instance manuelle en cours d'exécution..."
    if pgrep -f Photobooth_start.py > /dev/null; then
        echo "Arrêt de l'instance manuelle en cours (pkill)..."
        pkill -f Photobooth_start.py
        sleep 1
    else
        echo "Aucune instance manuelle trouvée."
    fi
    echo "ℹ Pour relancer l'écran manuellement : run_app.sh ou python3 Photobooth_start.py (ou rebooter le serveur)"
fi

# Gestion de photobooth-admin.service (web)
if [[ $(systemctl show -p LoadState photobooth-admin.service 2>/dev/null) == "LoadState=loaded" ]]; then
    echo "Redémarrage de l'administration web..."
    sudo systemctl restart photobooth-admin.service
else
    echo "ℹ photobooth-admin.service n'est pas installé sous systemd (non trouvé)."
fi

echo ""
echo "=== Vérification des statuts ==="
sleep 2

if [[ $(systemctl show -p LoadState photobooth.service 2>/dev/null) == "LoadState=loaded" ]]; then
    if systemctl is-active --quiet photobooth.service; then
        echo "✔ photobooth.service est ACTIF"
    else
        echo "❌ Erreur: photobooth.service n'a pas pu démarrer."
        echo "Derniers logs :"
        sudo journalctl -n 20 -u photobooth.service
    fi
fi

if [[ $(systemctl show -p LoadState photobooth-admin.service 2>/dev/null) == "LoadState=loaded" ]]; then
    if systemctl is-active --quiet photobooth-admin.service; then
        echo "✔ photobooth-admin.service est ACTIF"
    else
        echo "❌ Erreur: photobooth-admin.service n'a pas pu démarrer."
        echo "Derniers logs :"
        sudo journalctl -n 20 -u photobooth-admin.service
    fi
fi

echo ""
echo "=== Mise à jour terminée ==="
