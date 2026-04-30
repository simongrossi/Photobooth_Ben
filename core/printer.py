"""printer.py — gestion des files d'impression CUPS.

Encapsule `lpstat` + `lp` dans un PrinterManager avec vérif d'état et 2 files
(10x15 + strip). Module pur (subprocess uniquement), testable isolément.

Sprint 4.3 + 4.6 : extrait de Photobooth_start.py.
"""
from __future__ import annotations
import subprocess
from typing import Optional

from core.logger import log_info, log_critical


class PrinterManager:
    """Encapsule les files d'impression CUPS (10x15 + strip) avec vérif d'état physique et logique."""

    def __init__(self, nom_10x15: str, nom_strip: str) -> None:
        self._noms: dict[str, str] = {"10x15": nom_10x15, "strips": nom_strip}

    def nom(self, mode: str) -> Optional[str]:
        """Retourne le nom de la file CUPS pour ce mode, ou None."""
        return self._noms.get(mode)

    def is_ready(self, mode: str):
        nom_file = self._noms.get(mode)
        if not nom_file:
            return "MODE INCONNU"

        # --- 1. CHECK DES JOBS (Évite l'accumulation de photos) ---
        try:
            jobs_proc = subprocess.run(["lpstat", "-o", nom_file], capture_output=True, text=True, timeout=2)
            # On filtre les lignes vides pour compter les vrais jobs
            lines = [line for line in jobs_proc.stdout.strip().split('\n') if line]
            if len(lines) >= 1: 
                return "FILE D'ATTENTE PLEINE"
        except Exception:
            pass

        # --- 2. CHECK DE L'ÉTAT PHYSIQUE ---
        try:
            result = subprocess.run(["lpstat", "-p", nom_file], capture_output=True, text=True, timeout=2)
            out = result.stdout.lower()
            
            # ATTENTION : On ne met PAS 'paused' ici, car CUPS met en pause quand c'est éteint
            etats_ok = ("idle", "enabled", "activée", "printing", "inoccupée")
            
            # Si on détecte "paused", c'est que l'imprimante est offline
            if "paused" in out or "en pause" in out:
                return "IMPRIMANTE ÉTEINTE OU DÉBRANCHÉE"

            if not any(x in out for x in etats_ok):
                return "IMPRIMANTE HORS LIGNE"
                
        except Exception:
            return "ERREUR SYSTÈME CUPS"

        return True

    def send(self, chemin: str, mode: str) -> bool:
        """Envoie à la file correspondante. Retourne True si l'envoi a démarré."""
        nom_file = self._noms.get(mode)
        if not nom_file:
            log_critical(f"Mode imprimante inconnu : {mode}")
            return False
            
        status = self.is_ready(mode)
        if status is not True:
            # Maintenant, le message "IMPRIMANTE ÉTEINTE" sera bien loggé ici
            log_critical(f"Annulation : {status} (File: {nom_file})")
            return False
            
        try:
            # check=True lève une erreur si la commande échoue
            subprocess.run(["lp", "-d", nom_file, "-o", "fit-to-page", chemin], check=True, capture_output=True)
            log_info(f"🖨️ Impression lancée sur {nom_file}")
            return True
        except subprocess.CalledProcessError as e:
            log_critical(f"Erreur commande lp : {e.stderr.decode()}")
            return False
        except Exception as e:
            log_critical(f"Erreur système impression : {e}")
            return False
