"""exports.py — construction d'archives ZIP en tâche de fond, avec progression.

Un « ZIP + brutes » d'événement représente vite plusieurs centaines de photos
et une bonne minute de travail : le navigateur restait alors figé sur une
requête sans le moindre retour. L'archive est donc construite dans un thread
démon pendant que la page de suivi interroge `etat()` toutes les demi-secondes.

Les images sont écrites **sans compression** : JPEG et PNG sont déjà compressés,
le deflate ne gagnait rien et coûtait l'essentiel du temps CPU. Seuls les
fichiers texte (manifeste, CSV) sont compressés.

L'archive est écrite dans `data/cache/exports/`, **pas** dans `/tmp` : un export
« ZIP + brutes » pèse plusieurs Go et `/tmp` est un tmpfs en RAM sur beaucoup
d'installations — l'archive y remplissait la mémoire avant d'échouer. Le
dossier data est sur le même disque que les photos, donc dimensionné pour elles.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field

import config

# Durée de rétention d'une archive terminée : le temps que le navigateur la
# télécharge, plus une marge pour un second essai manuel.
TTL_S = 30 * 60
# Garde-fou disque : au-delà, les tâches les plus anciennes sont purgées même
# si elles n'ont pas atteint le TTL.
MAX_TACHES = 8
# Marge exigée en plus de la taille des photos : en-têtes ZIP, manifeste, et de
# quoi ne pas laisser le disque à zéro (le kiosque doit pouvoir continuer à
# écrire ses photos pendant l'export).
MARGE_DISQUE = 512 * 1024 * 1024

class EspaceInsuffisant(Exception):
    """Pas assez de place sur le disque pour l'archive demandée."""

    def __init__(self, archive: int, disponible: int, marge: int):
        self.archive = archive
        self.disponible = disponible
        self.marge = marge
        super().__init__(
            f"{octets_lisibles(archive)} d'archive + {octets_lisibles(marge)} de marge, "
            f"{octets_lisibles(disponible)} libres sur le disque"
        )


def octets_lisibles(octets: int) -> str:
    """Taille lisible : « 2.7 Go » plutôt que 2899102924."""
    valeur = float(octets)
    for unite in ("o", "Ko", "Mo", "Go"):
        if valeur < 1024 or unite == "Go":
            return f"{valeur:.0f} o" if unite == "o" else f"{valeur:.1f} {unite}"
        valeur /= 1024
    return f"{valeur:.1f} Go"


def dossier_archives() -> str:
    """Dossier de travail des archives, créé au besoin."""
    dossier = os.path.join(config.PATH_DATA, "cache", "exports")
    os.makedirs(dossier, exist_ok=True)
    return dossier


def verifier_espace(fichiers: list[tuple[str, str]], dossier: str) -> int:
    """Vérifie la place disponible et renvoie la taille attendue de l'archive.

    Les images étant stockées telles quelles, la somme des sources est une
    estimation fiable à quelques Ko d'en-têtes près. Échouer ici avec un message
    clair vaut mieux que remplir le disque à mi-parcours.
    """
    requis = 0
    for source, _ in fichiers:
        try:
            requis += os.path.getsize(source)
        except OSError:
            pass
    disponible = shutil.disk_usage(dossier).free
    if requis + MARGE_DISQUE > disponible:
        raise EspaceInsuffisant(requis, disponible, MARGE_DISQUE)
    return requis


_verrou = threading.Lock()
_taches: dict[str, "Tache"] = {}


@dataclass
class Tache:
    """État d'une construction d'archive, lisible depuis n'importe quel thread."""

    id: str
    nom_fichier: str
    libelle: str
    total: int
    retour: str
    # « admin » réserve l'archive au rôle admin ; « lecture » l'ouvre aux
    # viewers, comme la galerie qu'ils peuvent déjà parcourir.
    role_requis: str = "lecture"
    faits: int = 0
    taille_estimee: int = 0
    etat: str = "en_cours"  # en_cours | pret | erreur
    chemin: str | None = None
    chemin_travail: str = ""
    # Destination finale hors dossier de cache : l'archive y est deplacee une
    # fois complete et echappe alors a la purge (cas des sauvegardes).
    destination: str | None = None
    erreur: str | None = None
    cree_le: float = field(default_factory=time.time)
    fini_le: float | None = None

    @property
    def pourcent(self) -> int:
        if self.etat == "pret":
            return 100
        if self.total <= 0:
            return 0
        return min(99, int(self.faits * 100 / self.total))

    @property
    def octets_ecrits(self) -> int:
        """Taille réelle de l'archive en cours d'écriture (0 si pas commencée)."""
        try:
            return os.path.getsize(self.chemin_travail)
        except OSError:
            return 0

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "etat": self.etat,
            "faits": self.faits,
            "total": self.total,
            "pourcent": self.pourcent,
            "nom_fichier": self.nom_fichier,
            "libelle": self.libelle,
            "erreur": self.erreur,
            "taille": octets_lisibles(self.octets_ecrits),
            "taille_estimee": octets_lisibles(self.taille_estimee),
        }


def _purger(maintenant: float | None = None) -> None:
    """Supprime les archives expirées. Appelé sous `_verrou`."""
    maintenant = maintenant if maintenant is not None else time.time()
    expirees = [
        tache_id for tache_id, tache in _taches.items()
        if tache.fini_le is not None and maintenant - tache.fini_le > TTL_S
    ]
    terminees = sorted(
        (t for t in _taches.values() if t.fini_le is not None),
        key=lambda t: t.fini_le or 0,
    )
    surplus = len(_taches) - MAX_TACHES
    for tache in terminees[:max(0, surplus)]:
        expirees.append(tache.id)
    for tache_id in set(expirees):
        tache = _taches.pop(tache_id, None)
        # `destination` : l'archive a quitté le cache (sauvegarde d'événement),
        # elle ne suit plus le cycle de vie de la tâche.
        if tache and tache.chemin and tache.destination is None:
            try:
                os.unlink(tache.chemin)
            except OSError:
                pass
    _purger_orphelines(maintenant)


def _purger_orphelines(maintenant: float) -> None:
    """Supprime les archives sans tâche associée. Appelé sous `_verrou`.

    Un redémarrage du service admin perd le registre en mémoire mais laisse les
    fichiers : sans ce ménage, des archives de plusieurs Go s'accumuleraient
    dans `data/cache/exports/`.
    """
    dossier = os.path.join(config.PATH_DATA, "cache", "exports")
    if not os.path.isdir(dossier):
        return
    connus = {t.chemin for t in _taches.values()} | {t.chemin_travail for t in _taches.values()}
    for entree in os.scandir(dossier):
        if entree.path in connus or not entree.is_file():
            continue
        try:
            if maintenant - entree.stat().st_mtime > TTL_S:
                os.unlink(entree.path)
        except OSError:
            pass


def construire(
    chemin_zip: str,
    fichiers: list[tuple[str, str]],
    extras: dict[str, str] | None = None,
    progression=None,
) -> int:
    """Écrit l'archive et renvoie le nombre de fichiers réellement inclus.

    `fichiers` est une liste de couples (chemin source, nom dans l'archive). Un
    fichier **source** disparu entre le listing et l'écriture est ignoré, mais
    toute erreur d'écriture (disque plein en tête) fait échouer l'export : un
    `except OSError` global produisait sinon une archive tronquée annoncée
    « prête », ce qui est bien pire qu'un échec visible.
    """
    inclus = 0
    with zipfile.ZipFile(chemin_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for nom_archive, contenu in (extras or {}).items():
            archive.writestr(nom_archive, contenu)
        for source, nom_archive in fichiers:
            if os.path.isfile(source):
                archive.write(source, nom_archive, compress_type=zipfile.ZIP_STORED)
                inclus += 1
            if progression is not None:
                progression()
    return inclus


def demarrer(
    nom_fichier: str,
    libelle: str,
    fichiers: list[tuple[str, str]],
    extras: dict[str, str] | None = None,
    retour: str = "/",
    role_requis: str = "lecture",
    destination: str | None = None,
) -> str:
    """Lance la construction en fond et renvoie l'identifiant de suivi.

    Lève `EspaceInsuffisant` si le disque ne peut pas accueillir l'archive —
    l'appelant l'affiche à l'utilisateur plutôt que de lancer un export voué à
    remplir le disque.
    """
    dossier = dossier_archives()
    taille_estimee = verifier_espace(fichiers, dossier)
    tache = Tache(
        id=uuid.uuid4().hex,
        nom_fichier=nom_fichier,
        libelle=libelle,
        total=len(fichiers),
        retour=retour,
        role_requis=role_requis,
        taille_estimee=taille_estimee,
        destination=destination,
    )
    with _verrou:
        # Purge après insertion : la nouvelle tâche compte dans le plafond.
        _taches[tache.id] = tache
        _purger()

    fichier_tmp = tempfile.NamedTemporaryFile(
        dir=dossier, prefix="export-", suffix=".zip", delete=False,
    )
    fichier_tmp.close()
    tache.chemin_travail = fichier_tmp.name

    def _travail():
        try:
            construire(fichier_tmp.name, fichiers, extras, progression=_avancer)
        except Exception as exc:  # noqa: BLE001 — remonté tel quel à la page de suivi
            # Supprimer l'archive partielle AVANT de basculer l'état : un
            # observateur qui voit « erreur » ne doit jamais trouver de fichier
            # tronqué derrière.
            try:
                os.unlink(fichier_tmp.name)
            except OSError:
                pass
            tache.erreur = str(exc)
            tache.fini_le = time.time()
            tache.etat = "erreur"
            return
        if destination is not None:
            # Renommage atomique (même système de fichiers) : la destination
            # n'existe qu'une fois l'archive complète, jamais à moitié écrite.
            try:
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                os.replace(fichier_tmp.name, destination)
                # tempfile crée en 0600 : une sauvegarde doit rester lisible
                # pour la copier (partage réseau, autre compte, gestionnaire
                # de fichiers) sans avoir à passer par root.
                os.chmod(destination, 0o644)
            except OSError as exc:
                try:
                    os.unlink(fichier_tmp.name)
                except OSError:
                    pass
                tache.erreur = str(exc)
                tache.fini_le = time.time()
                tache.etat = "erreur"
                return
        # `etat` en dernier : il sert de barrière pour les lecteurs.
        tache.chemin = destination or fichier_tmp.name
        tache.faits = tache.total
        tache.fini_le = time.time()
        tache.etat = "pret"

    def _avancer():
        tache.faits += 1

    threading.Thread(target=_travail, daemon=True, name=f"export-{tache.id[:8]}").start()
    return tache.id


def etat(tache_id: str) -> Tache | None:
    with _verrou:
        return _taches.get(tache_id)


def attendre(tache_id: str, timeout: float = 30.0) -> Tache | None:
    """Bloque jusqu'à la fin de la tâche (usage tests et scripts)."""
    limite = time.time() + timeout
    while time.time() < limite:
        tache = etat(tache_id)
        if tache is None or tache.etat != "en_cours":
            return tache
        time.sleep(0.01)
    return etat(tache_id)


def oublier(tache_id: str) -> None:
    """Retire une tâche et son archive (utilisé par les tests)."""
    with _verrou:
        tache = _taches.pop(tache_id, None)
    if tache and tache.chemin and tache.destination is None:
        try:
            os.unlink(tache.chemin)
        except OSError:
            pass
