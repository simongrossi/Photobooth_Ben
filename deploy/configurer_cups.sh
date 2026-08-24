#!/usr/bin/env bash
# configurer_cups.sh — empêche CUPS de désactiver les files DNP sur erreur.
#
# À lancer UNE FOIS sur la machine du photobooth :
#   sudo ./deploy/configurer_cups.sh
#
# Idempotent : relançable sans risque.
#
# Indépendant de install.sh, qui ne concerne que les cibles systemd. La machine
# de production est un mini-PC démarré par autostart XFCE, où install.sh n'est
# pas exécuté.
#
# Pourquoi : par défaut CUPS applique ErrorPolicy=stop-printer. Une panne de
# papier désactive la file ET y laisse le job. Au rechargement, réactiver la
# file redispatche ce job, qui échoue de nouveau et redésactive la file — ni le
# redémarrage du PC ni plusieurs « Démarrer l'imprimante » ne cassent la boucle,
# parce que l'état Stopped et le job en attente survivent tous deux au reboot.
#
# Avec retry-job, la file reste active et le tirage repart tout seul dès que le
# papier revient.

set -euo pipefail

FILE_10X15="${FILE_10X15:-DNP_10x15}"
FILE_STRIP="${FILE_STRIP:-DNP_STRIP}"
CUPSD_CONF="/etc/cups/cupsd.conf"
UTILISATEUR="${SUDO_USER:-$USER}"

if [[ $EUID -ne 0 ]]; then
  echo "❌ À lancer avec sudo : sudo ./deploy/configurer_cups.sh" >&2
  exit 1
fi

echo "→ Politique d'erreur des files DNP..."
for f in "$FILE_10X15" "$FILE_STRIP"; do
  if ! lpstat -p "$f" >/dev/null 2>&1; then
    echo "❌ File CUPS introuvable : $f" >&2
    echo "   Files disponibles :" >&2
    lpstat -a 2>/dev/null | awk '{print "     " $1}' >&2 || true
    exit 1
  fi
  lpadmin -p "$f" -o printer-error-policy=retry-job
  echo "   $f → retry-job"
done

# Par défaut : 5 tentatives × 30 s = 2 min 30, trop court pour changer un
# rouleau. 240 × 30 s ≈ 2 h.
echo "→ Persistance des jobs en attente..."
for reglage in "JobRetryInterval 30" "JobRetryLimit 240"; do
  cle="${reglage%% *}"
  if grep -qE "^${cle}\b" "$CUPSD_CONF"; then
    sed -i "s|^${cle}\b.*|${reglage}|" "$CUPSD_CONF"
  else
    echo "$reglage" >> "$CUPSD_CONF"
  fi
  echo "   $reglage"
done

echo "→ Droits CUPS de l'utilisateur du kiosque..."
if id -nG "$UTILISATEUR" | tr ' ' '\n' | grep -qx lpadmin; then
  echo "   $UTILISATEUR est dans lpadmin ✅"
else
  echo "❌ $UTILISATEUR n'est PAS dans le groupe lpadmin." >&2
  echo "   Sans ce droit, le photobooth ne pourra pas réarmer une file." >&2
  echo "   Corrige avec : sudo usermod -aG lpadmin $UTILISATEUR" >&2
  exit 1
fi

echo "→ Redémarrage de CUPS..."
systemctl restart cups

echo
echo "✅ CUPS configuré. Vérification :"
echo "   lpstat -l -p $FILE_10X15 | grep -i policy"
