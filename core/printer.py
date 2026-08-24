"""printer.py — gestion des files d'impression CUPS.

Encapsule `lpstat` + `lp` dans un PrinterManager avec vérif d'état et 2 files
(10x15 + strip). Module pur (subprocess uniquement), testable isolément.

Sprint 4.3 + 4.6 : extrait de Photobooth_start.py.
"""
from __future__ import annotations
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

from core.logger import log_info, log_critical

try:
    import cups  # type: ignore
except ImportError:  # CI et macOS de dev : le diagnostic bascule sur lpstat
    cups = None  # type: ignore


# --- Diagnostic IPP -------------------------------------------------------
#
# CUPS expose la cause reelle d'un blocage dans `printer-state-reasons`, sous
# forme de mots-cles normalises et NON localises — contrairement au texte de
# `lpstat`, qui depend de la langue du systeme. Les mots-cles portent un
# suffixe de gravite (`-error`, `-warning`, `-report`) qu'on retire avant de
# chercher la correspondance.

_SUFFIXES_GRAVITE = ("-error", "-warning", "-report")

_MESSAGES_RAISONS = {
    "media-empty": "PAPIER ÉPUISÉ — recharger le bac",
    "media-needed": "PAPIER ÉPUISÉ — recharger le bac",
    "media-jam": "BOURRAGE PAPIER",
    "marker-supply-empty": "RIBBON ÉPUISÉ",
    "marker-supply-low": "RIBBON BIENTÔT ÉPUISÉ",
    "cover-open": "CAPOT OUVERT",
    "door-open": "CAPOT OUVERT",
    "connecting-to-device": "IMPRIMANTE ÉTEINTE OU DÉBRANCHÉE",
    "timed-out": "IMPRIMANTE ÉTEINTE OU DÉBRANCHÉE",
    "paused": "FILE D'IMPRESSION ARRÊTÉE",
}

# Etat IPP `printer-state` : 3 = idle, 4 = processing, 5 = stopped.
ETAT_IPP_ARRETE = 5

# marker-message de Gutenprint : "228 native prints remaining on 6x4 (PC) media".
# Chaine produite en C par le backend, donc non traduite.
_RE_TIRAGES = re.compile(r"(\d+)\s+native prints remaining", re.IGNORECASE)


def normaliser_raison(raison: str) -> str:
    """Retire le suffixe de gravite d'un mot-cle IPP."""
    for suffixe in _SUFFIXES_GRAVITE:
        if raison.endswith(suffixe):
            return raison[: -len(suffixe)]
    return raison


def message_pour_raison(raison: str) -> str:
    """Traduit un mot-cle IPP en message affichable a l'animateur.

    Une raison inconnue est affichee telle quelle : un code brut lisible vaut
    mieux qu'un message generique qui induirait en erreur."""
    return _MESSAGES_RAISONS.get(normaliser_raison(raison), f"Imprimante : {raison}")


def tirages_restants_depuis_marker(marker_message: str) -> Optional[int]:
    """Nombre de tirages restants extrait du marker-message Gutenprint.

    Retourne None si le format change : l'alerte devient alors inerte plutot
    que fausse."""
    if not marker_message:
        return None
    trouve = _RE_TIRAGES.search(marker_message)
    return int(trouve.group(1)) if trouve else None


@dataclass
class EtatImprimante:
    """Photo instantanee de l'imprimante physique (pas d'une seule file CUPS).

    Les deux files DNP partagent une meme DS620 : raisonner par file laisse
    passer un job coince dans l'autre, qui replantera l'imprimante."""

    pret: bool
    raison: str = ""              # mot-cle IPP brut, "" si aucun
    message: str = ""             # texte affichable, "" si prete
    file_desactivee: bool = False
    jobs: int = 0                 # cumule sur toutes les files du peripherique
    tirages_restants: Optional[int] = None


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
        """Purge manuellement les jobs des seules files DNP configurées.

        Cette opération ne doit pas être lancée automatiquement au démarrage :
        un job peut encore être en cours de finalisation après la sortie du tirage.
        """
        for nom_file in dict.fromkeys(self._noms.values()):
            try:
                subprocess.run(
                    ["cancel", "-a", nom_file],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                log_info(f"🗑️ CUPS : file {nom_file} purgée avec succès.")
            except subprocess.CalledProcessError as e:
                log_critical(
                    f"Impossible de purger la file {nom_file} (CUPS) : {e.stderr}"
                )
            except FileNotFoundError:
                log_critical(
                    "La commande système Linux 'cancel' est introuvable. "
                    "Pas de purge CUPS effectuée."
                )
                break
