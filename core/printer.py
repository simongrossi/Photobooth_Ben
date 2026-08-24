"""printer.py — gestion des files d'impression CUPS.

Encapsule `lpstat` + `lp` dans un PrinterManager avec vérif d'état et 2 files
(10x15 + strip). Module pur (subprocess uniquement), testable isolément.

Sprint 4.3 + 4.6 : extrait de Photobooth_start.py.
"""
from __future__ import annotations
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from core.logger import log_info, log_critical, log_warning

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

    def _imprimantes_cups(self) -> Optional[dict]:
        """Attributs IPP de toutes les files, ou None si pycups est indisponible."""
        if cups is None:
            return None
        try:
            return cups.Connection().getPrinters()
        except Exception as e:
            log_warning(f"CUPS injoignable via pycups : {e}")
            return None

    def _files_du_meme_device(self, mode: str) -> list[str]:
        """Files CUPS partageant l'imprimante physique du mode demande.

        Les deux files DNP pointent sur la meme DS620 : un job coince dans
        l'une bloque l'autre. Sans pycups on ne peut pas lire `device-uri` — on
        retourne alors toutes les files configurees. C'est le repli prudent :
        en verifier une de trop est sans effet, en oublier une laisse un job
        empoisonne qui replantera l'imprimante."""
        nom_file = self._noms.get(mode)
        if not nom_file:
            return []
        toutes = list(dict.fromkeys(self._noms.values()))
        imprimantes = self._imprimantes_cups()
        if imprimantes is None:
            return toutes
        device = imprimantes.get(nom_file, {}).get("device-uri")
        if not device:
            return [nom_file]
        return [n for n in toutes if imprimantes.get(n, {}).get("device-uri") == device]

    def jobs_en_attente_file(self, nom_file: str) -> Optional[int]:
        """Nombre de jobs CUPS visibles pour UNE file, ou None si inconnu."""
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

    def jobs_en_attente(self, mode: str) -> Optional[int]:
        """Jobs en attente sur l'imprimante physique du mode (toutes ses files).

        Retourne None si AUCUNE file n'a pu etre interrogee : le dashboard
        distingue "file vide" de "file inconnue"."""
        files = self._files_du_meme_device(mode)
        if not files:
            return None
        comptes = [self.jobs_en_attente_file(f) for f in files]
        connus = [c for c in comptes if c is not None]
        if not connus:
            return None
        return sum(connus)

    def diagnostic(self, mode: str) -> EtatImprimante:
        """Etat de l'imprimante physique servant ce mode.

        Lit `printer-state-reasons` via pycups quand il est disponible : ce sont
        des mots-cles IPP normalises, contrairement au texte localise de
        `lpstat`. Sans pycups, repli sur un diagnostic a trois categories."""
        nom_file = self._noms.get(mode)
        if not nom_file:
            return EtatImprimante(pret=False, raison="mode-inconnu", message="MODE INCONNU")

        files = self._files_du_meme_device(mode)
        jobs = sum(self.jobs_en_attente_file(f) or 0 for f in files)

        imprimantes = self._imprimantes_cups()
        if imprimantes is None:
            return self._diagnostic_lpstat(nom_file, jobs)

        raison = ""
        desactivee = False
        tirages: Optional[int] = None
        for f in files:
            attrs = imprimantes.get(f, {})
            if attrs.get("printer-state") == ETAT_IPP_ARRETE:
                desactivee = True
            for r in attrs.get("printer-state-reasons") or []:
                if r and r != "none" and not raison:
                    raison = r
            if tirages is None:
                tirages = tirages_restants_depuis_marker(attrs.get("marker-message", ""))

        if raison:
            message = message_pour_raison(raison)
        elif desactivee:
            message = "FILE D'IMPRESSION ARRÊTÉE"
        elif jobs:
            message = "TIRAGE EN ATTENTE"
        else:
            message = ""

        return EtatImprimante(
            pret=not (raison or desactivee or jobs),
            raison=raison,
            message=message,
            file_desactivee=desactivee,
            jobs=jobs,
            tirages_restants=tirages,
        )

    def _diagnostic_lpstat(self, nom_file: str, jobs: int) -> EtatImprimante:
        """Repli sans pycups : trois categories seulement.

        Le texte de `lpstat` est localise, on ne pretend pas a un diagnostic
        fin — juste a ne pas etre moins bon que le code historique."""
        try:
            resultat = subprocess.run(
                ["lpstat", "-p", nom_file], capture_output=True, text=True, timeout=2
            )
            sortie = resultat.stdout.lower()
        except Exception:
            return EtatImprimante(
                pret=False, raison="cups-injoignable",
                message="ERREUR SYSTÈME CUPS", jobs=jobs,
            )

        if any(x in sortie for x in ("paused", "en pause", "disabled", "désactivée")):
            return EtatImprimante(
                pret=False, raison="paused", message="FILE D'IMPRESSION ARRÊTÉE",
                file_desactivee=True, jobs=jobs,
            )

        etats_ok = ("idle", "enabled", "activée", "printing", "inoccupée")
        if not any(x in sortie for x in etats_ok):
            return EtatImprimante(
                pret=False, raison="offline", message="IMPRIMANTE HORS LIGNE", jobs=jobs,
            )

        if jobs:
            return EtatImprimante(pret=False, message="TIRAGE EN ATTENTE", jobs=jobs)

        return EtatImprimante(pret=True)

    def _commande_cups(self, cmd: list[str], libelle: str) -> bool:
        """Lance une commande CUPS, journalise le resultat, ne leve jamais."""
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            log_info(f"CUPS : {libelle} OK")
            return True
        except subprocess.CalledProcessError as e:
            log_critical(f"CUPS : echec {libelle} : {e.stderr}")
        except FileNotFoundError:
            log_critical(f"CUPS : commande '{cmd[0]}' introuvable ({libelle})")
        except Exception as e:
            log_critical(f"CUPS : erreur {libelle} : {e}")
        return False

    def _attendre_imprimante(self, mode: str, delai_max_s: float) -> None:
        """Attend que la DS620 reponde, au plus `delai_max_s`.

        Apres un changement de rouleau, l'imprimante met une vingtaine de
        secondes a relire le ribbon. Reactiver la file avant qu'elle reponde
        relance un job qui echoue aussitot."""
        echeance = time.monotonic() + delai_max_s
        while time.monotonic() < echeance:
            raison = normaliser_raison(self.diagnostic(mode).raison)
            if raison not in ("connecting-to-device", "timed-out"):
                return
            time.sleep(1.0)
        log_warning(f"Imprimante toujours injoignable apres {delai_max_s:.0f} s")

    def reamorcer(self, mode: str, delai_max_s: float = 30.0) -> EtatImprimante:
        """Purge les jobs puis reactive toutes les files de l'imprimante.

        L'ORDRE EST LE CORRECTIF. `cupsenable` seul redispatche immediatement
        le job qui a provoque l'erreur ; il echoue de nouveau et CUPS
        redesactive la file. C'est exactement la boucle vecue en evenement, que
        ni le redemarrage du PC ni plusieurs « Demarrer l'imprimante » n'ont
        cassee.

        Les deux files DNP partageant une seule DS620, elles sont traitees
        ensemble : en reamorcer une seule laisse l'autre replanter l'imprimante.
        """
        files = self._files_du_meme_device(mode)
        if not files:
            return EtatImprimante(pret=False, raison="mode-inconnu", message="MODE INCONNU")

        log_info(f"🔧 Reamorcage de {', '.join(files)}...")

        # 1. Purger d'abord — sinon l'etape 3 relance le job en echec.
        for nom_file in files:
            self._commande_cups(["cancel", "-a", nom_file], f"purge de {nom_file}")

        # 2. Laisser a la DS620 le temps de repondre apres un changement de media.
        self._attendre_imprimante(mode, delai_max_s)

        # 3. Reactiver, files vides.
        for nom_file in files:
            self._commande_cups(["cupsenable", nom_file], f"reactivation de {nom_file}")
            self._commande_cups(["cupsaccept", nom_file], f"reouverture de {nom_file}")

        etat = self.diagnostic(mode)
        log_info(f"Reamorcage termine : {etat.message or 'imprimante prete'}")
        return etat

    def is_ready(self, mode: str):
        """True si prete, sinon une chaine decrivant le probleme.

        Mince enveloppe autour de `diagnostic()` : le contrat historique est
        conserve pour Photobooth_start.py et web/routes/dashboard.py."""
        etat = self.diagnostic(mode)
        if etat.pret:
            self.last_error = None
            return True
        return self._echec(etat.message)

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
