#!/bin/bash
# Script de mise à jour et de redémarrage des services du Photobooth

set -e

echo "=== Mise à jour du Photobooth depuis GitHub ==="
git fetch origin
git checkout main
git pull origin main

echo ""
echo "=== Redémarrage des services systemd ==="
echo "Redémarrage de l'application Photobooth (écran)..."
sudo systemctl restart photobooth.service

echo "Redémarrage de l'administration web..."
sudo systemctl restart photobooth-admin.service

echo ""
echo "=== Vérification des statuts ==="
sleep 2

if systemctl is-active --quiet photobooth.service; then
    echo "✔ photobooth.service est ACTIF"
else
    echo "❌ Erreur: photobooth.service n'a pas pu démarrer."
    echo "Derniers logs :"
    sudo journalctl -n 20 -u photobooth.service
fi

if systemctl is-active --quiet photobooth-admin.service; then
    echo "✔ photobooth-admin.service est ACTIF"
else
    echo "❌ Erreur: photobooth-admin.service n'a pas pu démarrer."
    echo "Derniers logs :"
    sudo journalctl -n 20 -u photobooth-admin.service
fi

echo ""
echo "=== Mise à jour terminée ==="
