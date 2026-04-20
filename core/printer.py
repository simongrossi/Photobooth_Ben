"""printer.py — gestion des files d'impression CUPS.

Encapsule `lpstat` + `lp` dans un PrinterManager avec vérif d'état et 2 files
(10x15 + strip). Module pur (subprocess uniquement), testable isolément.

Sprint 4.3 + 4.6 : extrait de Photobooth_start.py.
"""
import subprocess

from core.logger import log_info, log_warning, log_critical


class PrinterManager:
    """Encapsule les files d'impression CUPS (10x15 + strip) avec vérif d'état."""

    def __init__(self, nom_10x15, nom_strip):
        self._noms = {"10x15": nom_10x15, "strips": nom_strip}

    def nom(self, mode):
        """Retourne le nom de la file CUPS pour ce mode, ou None."""
        return self._noms.get(mode)

    def is_ready(self, mode):
        """Vérifie via lpstat si la file est disponible (pas disabled, pas absente)."""
        nom_file = self._noms.get(mode)
        if not nom_file:
            log_critical(f"Mode imprimante inconnu : {mode}")
            return False
        try:
            result = subprocess.run(
                ["lpstat", "-p", nom_file],
                capture_output=True, text=True, timeout=3,
            )
            out = (result.stdout or "").lower()
            if not out.strip() or "disabled" in out:
                return False
            return any(tag in out for tag in ("idle", "enabled", "printing"))
        except Exception as e:
            log_warning(f"Check imprimante {nom_file} échoué : {e}")
            return False

    def send(self, chemin, mode):
        """Envoie à la file correspondante. Retourne True si l'envoi a démarré."""
        nom_file = self._noms.get(mode)
        if not nom_file:
            log_critical(f"Mode imprimante inconnu : {mode}")
            return False
        if not self.is_ready(mode):
            log_critical(f"Imprimante {nom_file} non disponible (offline/disabled)")
            return False
        try:
            subprocess.Popen(["lp", "-d", nom_file, "-o", "fit-to-page", chemin])
            log_info(f"🖨️ Impression lancée sur {nom_file}")
            return True
        except Exception as e:
            log_critical(f"Erreur impression : {e}")
            return False
