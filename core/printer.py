"""printer.py — gestion des files d'impression CUPS.

Encapsule `lpstat` + `lp` dans un PrinterManager avec vérif d'état et 2 files
(10x15 + strip). Module pur (subprocess uniquement), testable isolément.

Sprint 4.3 + 4.6 : extrait de Photobooth_start.py.
"""
from __future__ import annotations
import os 
import subprocess
from typing import Optional

from core.logger import log_info, log_warning, log_critical


class PrinterManager:
    """Encapsule les files d'impression CUPS (10x15 + strip) avec vérif d'état physique et logique."""

    def __init__(self, nom_10x15: str, nom_strip: str) -> None:
        self._noms: dict[str, str] = {"10x15": nom_10x15, "strips": nom_strip}

    def nom(self, mode: str) -> Optional[str]:
        """Retourne le nom de la file CUPS pour ce mode, ou None."""
        return self._noms.get(mode)

    def is_ready(self, mode: str): # On enlève -> bool car on peut renvoyer du texte
        nom_file = self._noms.get(mode)
        if not nom_file:
            return "MODE INCONNU"

        # --- 1. CHECK DES JOBS (Trop de photos) ---
        try:
            jobs_proc = subprocess.run(["lpstat", "-o", nom_file], capture_output=True, text=True, timeout=2)
            lines = jobs_proc.stdout.strip().split('\n')
            nb_jobs = len(lines) if (len(lines) > 0 and lines[0] != "") else 0
            
            if nb_jobs >= 2: # Seuil de tolérance : 2 jobs en attente (ajustable selon les besoins)
                return "FILE D'ATTENTE PLEINE" # Message spécifique
        except:
            pass

        # --- 2. CHECK DE L'ÉTAT (Éteinte/Pause) ---
        try:
            result = subprocess.run(["lpstat", "-p", nom_file], capture_output=True, text=True, timeout=2)
            out = result.stdout.lower()
            etats_ok = ("idle", "enabled", "activée", "printing", "paused", "en pause", "inoccupée")
            
            if not any(x in out for x in etats_ok):
                return "IMPRIMANTE HORS LIGNE" # Message spécifique
        except:
            return "ERREUR SYSTÈME CUPS"

        return True # Tout est OK
    def send(self, chemin: str, mode: str) -> bool:
        """Envoie à la file correspondante. Retourne True si l'envoi a démarré."""
        nom_file = self._noms.get(mode)
        if not nom_file:
            log_critical(f"Mode imprimante inconnu : {mode}")
            return False
            
        # is_ready va maintenant bloquer ici si l'imprimante est éteinte
        if not self.is_ready(mode):
            log_critical(f"Imprimante {nom_file} non disponible (éteinte ou offline)")
            return False
            
        try:
            subprocess.Popen(["lp", "-d", nom_file, "-o", "fit-to-page", chemin])
            log_info(f"🖨️ Impression lancée sur {nom_file}")
            return True
        except Exception as e:
            log_critical(f"Erreur impression : {e}")
            return False
