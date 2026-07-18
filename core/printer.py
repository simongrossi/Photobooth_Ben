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
        # Dernier message d'erreur lisible (rempli par is_ready/send, affiché par l'UI).
        # None quand tout va bien. Évite l'AttributeError historique côté appelant.
        self.last_error: Optional[str] = None

    def nom(self, mode: str) -> Optional[str]:
        """Retourne le nom de la file CUPS pour ce mode, ou None."""
        return self._noms.get(mode)

    def _echec(self, message: str) -> str:
        """Mémorise le message d'erreur et le retourne (contrat is_ready inchangé)."""
        self.last_error = message
        return message

    def jobs_en_attente(self, mode: str) -> Optional[int]:
        """Nombre de jobs CUPS visibles pour la file, ou None si inconnu."""
        nom_file = self._noms.get(mode)
        if not nom_file:
            return None
        try:
            resultat = subprocess.run(
                ["lpstat", "-o", nom_file],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            return None
        if getattr(resultat, "returncode", 0) != 0:
            return None
        return len([ligne for ligne in resultat.stdout.splitlines() if ligne.strip()])

    def is_ready(self, mode: str):
        """Retourne True si la file est prête, sinon une chaîne décrivant le problème.
        Dans les deux cas, `self.last_error` reflète l'état (None si prêt)."""
        nom_file = self._noms.get(mode)
        if not nom_file:
            return self._echec("MODE INCONNU")

        # --- 1. CHECK DES JOBS (Évite l'accumulation de photos) ---
        try:
            jobs_proc = subprocess.run(["lpstat", "-o", nom_file], capture_output=True, text=True, timeout=2)
            # On filtre les lignes vides pour compter les vrais jobs
            lines = [line for line in jobs_proc.stdout.strip().split('\n') if line]
            if len(lines) >= 1:
                return self._echec("FILE D'ATTENTE PLEINE")
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
                return self._echec("IMPRIMANTE ÉTEINTE OU DÉBRANCHÉE")

            if not any(x in out for x in etats_ok):
                return self._echec("IMPRIMANTE HORS LIGNE")

        except Exception:
            return self._echec("ERREUR SYSTÈME CUPS")

        self.last_error = None
        return True

    def send(self, chemin: str, mode: str, verifier: bool = True) -> bool:
        """Envoie à la file correspondante. Retourne True si l'envoi a démarré.

        ``verifier=False`` évite deux appels ``lpstat`` redondants lorsque
        l'appelant vient d'effectuer le contrôle de sécurité.
        """
        nom_file = self._noms.get(mode)
        if not nom_file:
            log_critical(f"Mode imprimante inconnu : {mode}")
            return False
            
        if verifier:
            status = self.is_ready(mode)
            if status is not True:
                log_critical(f"Annulation : {status} (File: {nom_file})")
                return False
            
        try:
            # check=True lève une erreur si la commande échoue
            subprocess.run(["lp", "-d", nom_file, "-o", "fit-to-page", chemin], check=True, capture_output=True)
            log_info(f"🖨️ Impression lancée sur {nom_file}")
            self.last_error = None
            return True
        except subprocess.CalledProcessError as e:
            detail = e.stderr.decode() if e.stderr else str(e)
            self.last_error = f"Erreur commande lp : {detail}"
            log_critical(f"Erreur commande lp : {detail}")
            return False
        except Exception as e:
            self.last_error = f"Erreur système impression : {e}"
            log_critical(f"Erreur système impression : {e}")
            return False


    def purger_file_attente(self) -> None:
        """Purge de manière sécurisée toutes les tâches d'impression CUPS en cours ou bloquées."""
        try:
            subprocess.run(["cancel", "-a"], capture_output=True, text=True, check=True)
            log_info("🗑️ CUPS : Les tâches d'impression résiduelles ont été purgées avec succès.")
        except subprocess.CalledProcessError as e:
            log_critical(f"Impossible de purger la file d'attente d'impression (CUPS) : {e.stderr}")
        except FileNotFoundError:
            log_critical("La commande système Linux 'cancel' est introuvable. Pas de purge CUPS effectuée.")
