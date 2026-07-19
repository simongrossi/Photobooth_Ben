"""ecrans.py — registre des écrans du kiosque et résolution de leurs assets.

Répond à une question que rien ne permettait de poser jusqu'ici : *quel fichier
chaque écran affiche-t-il réellement ?* L'admin activait un fond et devait
croire sur parole que le kiosque le prendrait — sans voir que certains écrans
chargeaient encore un chemin codé en dur.

Trois rôles :

1. **Registre déclaratif** (`REGISTRE`) : la liste des écrans, avec pour chacun
   son asset de fond et les clés de `config` qu'on peut éditer. C'est la source
   unique de la page « Écrans » de l'admin — pas de table de libellés parallèle
   à maintenir en double.
2. **Résolution d'assets** (`resoudre_assets`) : appelle `config.resoudre_actif`,
   la fonction que le kiosque utilise lui-même. Admin et kiosque lisent le même
   disque avec le même code, donc l'inventaire ne peut pas mentir.
3. **Détection de divergence** (`empreinte_config`, `lire_etat_kiosque`) : le
   kiosque résout ses assets à l'import et n'a aucune mémoire partagée avec le
   process web. Il dépose son empreinte au boot ; l'admin la compare à
   l'empreinte du disque pour afficher « redémarrage requis » à bon escient.

Règles d'import : ce module importe `config` uniquement. Jamais `ui/*`, jamais
`Photobooth_start` — il doit rester importable par `web/*` comme par le kiosque.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import config

ETAT_KIOSQUE_PATH = config.PATH_ETAT_KIOSQUE
HEARTBEAT_INTERVALLE_S = config.INTERVALLE_HEARTBEAT_KIOSQUE_S
HEARTBEAT_EXPIRE_S = config.EXPIRATION_HEARTBEAT_KIOSQUE_S
_etat_write_lock = threading.Lock()

# Origines possibles d'un asset résolu, du plus spécifique au plus générique.
ORIGINE_ACTIF = "actif"
ORIGINE_HERITE = "herite"
ORIGINE_DEFAUT = "defaut"
ORIGINE_ABSENT = "absent"
ORIGINE_SANS_FOND = "sans_fond"

LIBELLES_ORIGINE = {
    ORIGINE_ACTIF: "Activé depuis l'admin",
    ORIGINE_HERITE: "Hérité du fond d'accueil",
    ORIGINE_DEFAUT: "Défaut versionné",
    # Distinguer les deux est le cœur de l'inventaire : « pas d'image par
    # conception » et « image attendue mais introuvable » se ressemblent à
    # l'écran et n'appellent pas du tout la même action.
    ORIGINE_ABSENT: "Fichier introuvable — couleur de secours",
    ORIGINE_SANS_FOND: "Aucun fond — aplat de couleur",
}

# Natures de champ, pour le regroupement dans le formulaire d'édition.
TEXTE, DUREE, TAILLE, POSITION, BASCULE = "texte", "duree", "taille", "position", "bascule"
COULEUR = "couleur"


@dataclass(frozen=True)
class ChampEditable:
    """Une clé de `config` éditable depuis l'admin.

    Porte son propre libellé et son aide : ajouter un champ au registre suffit,
    il n'y a pas de table de métadonnées à synchroniser ailleurs.
    """

    cle: str
    libelle: str
    nature: str
    aide: str = ""
    unite: str = ""

    @property
    def bornes(self) -> Optional[tuple]:
        """(type, mini, maxi) depuis la whitelist de config, ou None si absente."""
        return config._ECRANS_OVERRIDES_WHITELIST.get(self.cle)

    @property
    def defaut(self):
        """Valeur actuellement en vigueur dans `config` (override compris)."""
        return getattr(config, self.cle, None)


@dataclass(frozen=True)
class Ecran:
    """Un écran du kiosque et ce qu'on peut y régler."""

    id: str
    libelle: str
    description: str
    champs: tuple[ChampEditable, ...] = field(default_factory=tuple)
    # Nom de l'attribut `config` portant le chemin du fond, ou None si l'écran
    # n'affiche pas d'image (l'écran d'erreur est un aplat de couleur).
    attribut_fond: Optional[str] = None
    # Nom de l'attribut `config` portant la cible « activable » correspondante.
    attribut_fond_actif: Optional[str] = None

    def champs_par_nature(self, nature: str) -> tuple[ChampEditable, ...]:
        return tuple(c for c in self.champs if c.nature == nature)


@dataclass(frozen=True)
class AssetResolu:
    """Le fichier qu'un écran affichera réellement au prochain démarrage."""

    ecran_id: str
    chemin: Optional[str]
    origine: str
    existe: bool
    taille_octets: int = 0
    mtime_ns: int = 0

    @property
    def libelle_origine(self) -> str:
        return LIBELLES_ORIGINE.get(self.origine, self.origine)

    @property
    def nom_fichier(self) -> str:
        return os.path.basename(self.chemin) if self.chemin else ""


# ========================================================================================
# --- Registre des écrans ---
# ========================================================================================

REGISTRE: tuple[Ecran, ...] = (
    Ecran(
        id="accueil",
        libelle="Accueil",
        description="Écran d'attente principal : choix entre grand format et bandelettes.",
        attribut_fond="BG_ACCUEIL_EFFECTIF",
        attribut_fond_actif="FILE_BG_ACCUEIL_ACTIF",
        champs=(
            ChampEditable("BANDEAU_ACCUEIL", "Bandeau — accueil", TEXTE,
                          "Texte du bandeau noir tant qu'aucun format n'est sélectionné."),
            ChampEditable("BANDEAU_10X15", "Bandeau — grand format", TEXTE,
                          "Affiché quand le grand format est sélectionné."),
            ChampEditable("BANDEAU_STRIP", "Bandeau — bandelettes", TEXTE,
                          "Affiché quand les bandelettes sont sélectionnées."),
            ChampEditable("MODE_10x15", "Libellé grand format", TEXTE,
                          "Texte sous l'icône de gauche."),
            ChampEditable("MODE_STRIP", "Libellé bandelettes", TEXTE,
                          "Texte sous l'icône de droite."),
            ChampEditable("TAILLE_TITRE_ACCUEIL", "Taille des titres", TAILLE, unite="px"),
            ChampEditable("TAILLE_TEXTE_BOUTON", "Taille des libellés de mode", TAILLE, unite="px"),
            ChampEditable("TAILLE_TEXTE_BANDEAU", "Taille du bandeau", TAILLE, unite="px"),
            ChampEditable("BANDEAU_HAUTEUR", "Hauteur du bandeau", POSITION, unite="px"),
            ChampEditable("BANDEAU_ALPHA", "Opacité du bandeau", POSITION,
                          "0 = invisible, 255 = noir opaque."),
            ChampEditable("LARGEUR_ICONE_10X15", "Largeur icône grand format", TAILLE, unite="px"),
            ChampEditable("LARGEUR_ICONE_STRIP", "Largeur icône bandelettes", TAILLE, unite="px"),
            ChampEditable("OFFSET_DROITE_10X15", "Décalage icône grand format", POSITION,
                          "Positif = vers la droite.", unite="px"),
            ChampEditable("OFFSET_DROITE_STRIP", "Décalage icône bandelettes", POSITION,
                          "Positif = vers la droite.", unite="px"),
            ChampEditable("MARGE_ACCUEIL", "Écart entre les deux icônes", POSITION, unite="px"),
            ChampEditable("ZOOM_FACTOR", "Agrandissement à la sélection", TAILLE,
                          "1.0 = aucun effet, 1.15 = +15 %."),
            ChampEditable("BANDEAU_COULEUR", "Couleur du bandeau", COULEUR),
            ChampEditable("COULEUR_TEXTE_REPOS", "Libellé non sélectionné", COULEUR),
            ChampEditable("COULEUR_TEXTE_OFF", "Libellé sélectionné — creux", COULEUR,
                          "Le libellé sélectionné pulse entre cette teinte et la suivante."),
            ChampEditable("COULEUR_TEXTE_ON", "Libellé sélectionné — crête", COULEUR),
            ChampEditable("COULEUR_SLIDESHOW_INVITATION", "Invitation du diaporama", COULEUR),
        ),
    ),
    Ecran(
        id="boutons",
        libelle="Boutons et actions",
        description=(
            "Palette commune à tous les écrans à boutons : validation, fin, choix "
            "du nombre de copies et déblocage du quota. Modifier une couleur ici "
            "la change partout — c'est voulu : un bouton « annuler » doit avoir "
            "le même rouge sur tous les écrans."
        ),
        champs=(
            ChampEditable("COULEUR_TEXTE_G", "Bouton gauche — reprendre / retour", COULEUR),
            ChampEditable("COULEUR_TEXTE_M", "Bouton milieu — valider / imprimer", COULEUR),
            ChampEditable("COULEUR_TEXTE_D", "Bouton droit — annuler / supprimer", COULEUR),
            ChampEditable("COULEUR_TEXTE_INACTIF", "Option indisponible", COULEUR,
                          "Par exemple « + » quand le quota restant est atteint."),
        ),
    ),
    Ecran(
        id="decompte",
        libelle="Décompte",
        description="Compte à rebours avant chaque déclenchement, avec les chevrons animés.",
        champs=(
            ChampEditable("TAILLE_DECOMPTE", "Taille des chiffres", TAILLE, unite="px"),
            ChampEditable("DUREE_FLASH_BLANC", "Flash blanc avant capture", DUREE, unite="s"),
            ChampEditable("TEXTE_PHOTO_COUNT", "Libellé du compteur", TEXTE,
                          "Précède « 1/3 » en mode bandelettes."),
            ChampEditable("STRIP_FILIGRANE_ENABLED", "Filigrane photos restantes", BASCULE,
                          "Grand chiffre en fond pendant le décompte des bandelettes."),
            ChampEditable("STRIP_FILIGRANE_ALPHA", "Opacité du filigrane", POSITION,
                          "0 = invisible. 50 est déjà très discret."),
            ChampEditable("STRIP_FILIGRANE_TAILLE", "Taille du filigrane", TAILLE, unite="px"),
            ChampEditable("COULEUR_DECOMPTE", "Chiffres du décompte", COULEUR),
            ChampEditable("COULEUR_SOURIEZ", "Message « souriez »", COULEUR),
            ChampEditable("COULEUR_COMPTEUR_STRIP", "Compteur photo N/3", COULEUR),
            ChampEditable("COULEUR_BURST_TEXTE", "Décompte du mode rafale", COULEUR),
        ),
    ),
    Ecran(
        id="validation",
        libelle="Validation",
        description="Aperçu juste après la prise de vue : reprendre, valider ou abandonner.",
        attribut_fond="BG_ACCUEIL_EFFECTIF",
        attribut_fond_actif="FILE_BG_ACCUEIL_ACTIF",
        champs=(
            ChampEditable("TXT_VALID_REPRENDRE_10X15", "Reprendre — grand format", TEXTE),
            ChampEditable("TXT_VALID_VALIDER_10X15", "Valider — grand format", TEXTE),
            ChampEditable("TXT_VALID_ACCUEIL_10X15", "Abandonner — grand format", TEXTE),
            ChampEditable("TXT_VALID_REPRENDRE_STRIP", "Reprendre — bandelettes", TEXTE),
            ChampEditable("TXT_VALID_VALIDER_STRIP", "Valider — bandelettes", TEXTE),
            ChampEditable("TXT_VALID_ACCUEIL_STRIP", "Abandonner — bandelettes", TEXTE),
            ChampEditable("TXT_CONFIRM_ABANDON_1", "Confirmation d'abandon — titre", TEXTE),
            ChampEditable("TXT_CONFIRM_ABANDON_2", "Confirmation d'abandon — consigne", TEXTE),
            ChampEditable("DUREE_CONFIRM_ABANDON", "Fenêtre de confirmation", DUREE,
                          "Délai pour appuyer une seconde fois et confirmer l'abandon.", "s"),
            ChampEditable("TXT_BURST_COUNTDOWN", "Enchaînement automatique", TEXTE,
                          "Affiché entre deux photos quand le mode rafale est actif."),
            ChampEditable("DECALAGE_Y_PREVISU_10X15", "Décalage aperçu — grand format", POSITION,
                          "Négatif = vers le haut.", "px"),
            ChampEditable("DECALAGE_Y_PREVISU_STRIPS", "Décalage aperçu — bandelettes", POSITION,
                          "Négatif = vers le haut.", "px"),
            ChampEditable("COULEUR_ABANDON_TITRE", "Confirmation d'abandon — titre", COULEUR),
            ChampEditable("COULEUR_ABANDON_CONSIGNE", "Confirmation d'abandon — consigne", COULEUR),
        ),
    ),
    Ecran(
        id="fin",
        libelle="Fin de session",
        description="Montage final : imprimer, recommencer ou revenir à l'accueil.",
        attribut_fond="BG_ACCUEIL_EFFECTIF",
        attribut_fond_actif="FILE_BG_ACCUEIL_ACTIF",
        champs=(
            ChampEditable("TXT_BOUTON_IMPRIMER", "Bouton imprimer", TEXTE),
            ChampEditable("TXT_BOUTON_REPRENDRE", "Bouton recommencer", TEXTE),
            ChampEditable("TXT_BOUTON_SUPPRIMER", "Bouton retour accueil", TEXTE),
            ChampEditable("TXT_IMPRESSION_ECHEC", "Échec d'impression — titre", TEXTE),
            ChampEditable("TXT_IMPRESSION_SANS", "Échec — terminer sans imprimer", TEXTE),
            ChampEditable("TXT_IMPRESSION_REESSAYER", "Échec — réessayer", TEXTE),
            ChampEditable("TXT_IMPRESSION_AIDE", "Échec — appeler l'animateur", TEXTE),
            ChampEditable("TXT_IMPRESSION_AIDE_MESSAGE", "Échec — message d'aide", TEXTE),
            ChampEditable("DECALAGE_Y_MONTAGE_FINAL_STRIP", "Décalage du montage bandelettes",
                          POSITION, "Négatif = vers le haut.", "px"),
        ),
    ),
    Ecran(
        id="transition",
        libelle="Transition et impression",
        description=(
            "Écrans d'attente : annulation d'une photo, reprise, préparation et "
            "attente d'impression. Sans fond dédié, reprend le fond d'accueil."
        ),
        attribut_fond="BG_TRANSITION_EFFECTIF",
        attribut_fond_actif="FILE_BG_TRANSITION_ACTIF",
        champs=(
            ChampEditable("TXT_PREPARATION_IMP", "Message de préparation", TEXTE,
                          "Affiché pendant la génération du montage à imprimer."),
            ChampEditable("TXT_ENVOI_IMPRIMANTE", "Message pendant l'envoi", TEXTE),
            ChampEditable("TXT_IMPRESSION_ENVOYEE", "Confirmation d'envoi", TEXTE),
            ChampEditable("TAILLE_TEXTE_IMP_COURANT", "Taille du message", TAILLE, unite="px"),
            ChampEditable("TAILLE_COMPTEUR_IMP", "Taille du compteur", TAILLE, unite="px"),
            ChampEditable("COULEUR_FOND_LOADER", "Couleur de secours (sans image)", COULEUR,
                          "Utilisée si aucun fond n'est disponible."),
            ChampEditable("COULEUR_IMPRESSION_TEXTE", "Texte d'attente", COULEUR),
        ),
    ),
    Ecran(
        id="camera",
        libelle="Connexion appareil photo",
        description="Écran de démarrage pendant l'initialisation USB de l'appareil.",
        champs=(
            ChampEditable("TXT_SPLASH_CAMERA", "Message de connexion", TEXTE),
            ChampEditable("TXT_SPLASH_CAMERA_OK", "Message de succès", TEXTE),
            ChampEditable("TXT_SPLASH_CAMERA_FAIL", "Message d'échec", TEXTE),
            ChampEditable("TIMEOUT_SPLASH_CAMERA", "Délai maximum d'attente", DUREE, unite="s"),
            ChampEditable("COULEUR_SPLASH_ATTENTE", "Message de connexion", COULEUR),
            ChampEditable("COULEUR_SPLASH_OK", "Message de succès", COULEUR),
            ChampEditable("COULEUR_SPLASH_ECHEC", "Message d'échec", COULEUR),
        ),
    ),
    Ecran(
        id="erreur",
        libelle="Erreur",
        description="Écran rouge affiché en cas d'échec de capture ou d'impression.",
        champs=(
            ChampEditable("TXT_ERREUR_CAPTURE", "Échec de capture", TEXTE),
            ChampEditable("TXT_ERREUR_IMPRIMANTE", "Imprimante indisponible", TEXTE),
            ChampEditable("TAILLE_TEXTE_ALERTE", "Taille du message", TAILLE, unite="px"),
            ChampEditable("DUREE_ECRAN_ERREUR", "Disparition automatique", DUREE, unite="s"),
            ChampEditable("COULEUR_ERREUR_FOND", "Fond de l'écran", COULEUR),
            ChampEditable("COULEUR_ERREUR_TEXTE", "Texte du message", COULEUR),
            ChampEditable("COULEUR_ERREUR_INDICE", "Consigne en bas d'écran", COULEUR),
        ),
    ),
)

PAR_ID = {e.id: e for e in REGISTRE}


def ecran(ecran_id: str) -> Optional[Ecran]:
    """L'écran d'identifiant donné, ou None."""
    return PAR_ID.get(ecran_id)


def tous_les_champs() -> tuple[ChampEditable, ...]:
    return tuple(champ for e in REGISTRE for champ in e.champs)


# ========================================================================================
# --- Résolution des assets ---
# ========================================================================================

def _decrire(ecran_obj: Ecran) -> AssetResolu:
    """Détermine le fichier de fond réellement utilisé par un écran."""
    if ecran_obj.attribut_fond is None:
        return AssetResolu(ecran_obj.id, None, ORIGINE_SANS_FOND, False)

    chemin = getattr(config, ecran_obj.attribut_fond, None)
    if not chemin or not os.path.exists(chemin):
        return AssetResolu(ecran_obj.id, chemin, ORIGINE_ABSENT, False)

    actif = getattr(config, ecran_obj.attribut_fond_actif, None) if ecran_obj.attribut_fond_actif else None
    if actif and os.path.realpath(chemin) == os.path.realpath(actif):
        origine = ORIGINE_ACTIF
    elif os.path.realpath(chemin) == os.path.realpath(config.BG_ACCUEIL_EFFECTIF) \
            and ecran_obj.attribut_fond != "BG_ACCUEIL_EFFECTIF":
        # Le fond de transition retombe sur celui de l'accueil : le dire
        # explicitement, sinon l'admin croit à un fond dédié.
        origine = ORIGINE_HERITE
    else:
        origine = ORIGINE_DEFAUT

    stat = os.stat(chemin)
    return AssetResolu(
        ecran_id=ecran_obj.id, chemin=chemin, origine=origine, existe=True,
        taille_octets=stat.st_size, mtime_ns=stat.st_mtime_ns,
    )


def resoudre_assets() -> dict[str, AssetResolu]:
    """Le fond réellement utilisé par chaque écran, indexé par identifiant."""
    return {e.id: _decrire(e) for e in REGISTRE}


# ========================================================================================
# --- Overrides d'écran (data/ecrans_overrides.json) ---
# ========================================================================================

def charger_overrides(chemin: Optional[str] = None) -> dict:
    """Overrides d'écran actuellement sur disque. {} si absent ou illisible."""
    chemin = chemin or config.ECRANS_OVERRIDES_PATH
    if not os.path.exists(chemin):
        return {}
    try:
        with open(chemin, encoding="utf-8") as f:
            donnees = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return donnees if isinstance(donnees, dict) else {}


def ecrire_overrides(overrides: dict, chemin: Optional[str] = None) -> None:
    """Écrit atomiquement les overrides, après filtrage par la whitelist.

    Une clé inconnue ou une valeur hors bornes n'est jamais écrite : le fichier
    sur disque reste toujours applicable tel quel par le kiosque.
    """
    chemin = chemin or config.ECRANS_OVERRIDES_PATH
    propres = {}
    for cle, valeur in overrides.items():
        validee = config.valeur_ecran_valide(cle, valeur)
        if validee is None:
            continue
        borne = config._ECRANS_OVERRIDES_WHITELIST.get(cle)
        if borne and borne[0] is config.Couleur:
            # Réécrire en #rrggbb : `valeur_ecran_valide` renvoie un tuple RGB
            # (ce dont pygame a besoin), mais JSON n'a pas de tuple et un
            # [r, g, b] serait illisible et pénible à corriger à la main.
            propres[cle] = config.Couleur.vers_hexa(validee)
        else:
            propres[cle] = validee

    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    temporaire = chemin + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as f:
        json.dump(propres, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temporaire, chemin)


def reinitialiser_overrides(chemin: Optional[str] = None) -> bool:
    """Supprime le fichier d'overrides d'écran. True s'il existait.

    Ne touche jamais `config_overrides.json` : les deux fichiers se réinitialisent
    indépendamment.
    """
    chemin = chemin or config.ECRANS_OVERRIDES_PATH
    if not os.path.exists(chemin):
        return False
    os.remove(chemin)
    return True


# ========================================================================================
# --- Empreinte et état du kiosque ---
# ========================================================================================

def empreinte_config() -> str:
    """SHA-256 de tout ce qui change l'apparence du kiosque.

    Couvre les deux fichiers d'overrides et l'identité de chaque asset résolu
    (chemin + mtime + taille), de sorte que remplacer un fond par un autre
    fichier de même nom change bien l'empreinte.
    """
    assets = resoudre_assets()
    materiel = {
        "config_overrides": config._lire_json_dict(config.CONFIG_OVERRIDES_PATH),
        "ecrans_overrides": charger_overrides(),
        "assets": {
            a.ecran_id: [a.chemin, a.origine, a.existe, a.taille_octets, a.mtime_ns]
            for a in assets.values()
        },
    }
    canonique = json.dumps(materiel, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonique.encode("utf-8")).hexdigest()


def _ecrire_etat_atomique(etat: dict, chemin: str) -> None:
    """Écrit l'état sous verrou, sans jamais faire tomber le kiosque."""
    try:
        dossier = os.path.dirname(chemin)
        if dossier:
            os.makedirs(dossier, exist_ok=True)
        temporaire = chemin + ".tmp"
        with _etat_write_lock:
            with open(temporaire, "w", encoding="utf-8") as f:
                json.dump(etat, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(temporaire, chemin)
    except (OSError, TypeError, ValueError):
        pass


def ecrire_etat_kiosque(chemin: Optional[str] = None) -> dict:
    """Dépose l'empreinte de la config chargée. Appelé au boot du kiosque.

    C'est le seul canal par lequel l'admin sait ce que le kiosque a réellement
    en mémoire : les deux process ne partagent rien d'autre que le disque.
    Toute erreur d'écriture est absorbée — ne jamais empêcher un démarrage.
    """
    chemin = chemin or ETAT_KIOSQUE_PATH
    maintenant = time.time()
    etat = {
        "version": 2,
        "boot_ts": maintenant,
        "heartbeat_ts": maintenant,
        "pid": os.getpid(),
        "empreinte": empreinte_config(),
        "online": True,
        "etat": "DEMARRAGE",
        "session_active": False,
    }
    _ecrire_etat_atomique(etat, chemin)
    return etat


def ecrire_heartbeat_kiosque(
    instantane: dict,
    chemin: Optional[str] = None,
    *,
    boot_ts: Optional[float] = None,
    empreinte: Optional[str] = None,
) -> dict:
    """Publie atomiquement l'état runtime fourni par le kiosque."""
    chemin = chemin or ETAT_KIOSQUE_PATH
    precedent = lire_etat_kiosque(chemin) or {}
    maintenant = time.time()
    etat = {
        "version": 2,
        "boot_ts": boot_ts or precedent.get("boot_ts") or maintenant,
        "heartbeat_ts": maintenant,
        "pid": os.getpid(),
        "empreinte": empreinte or precedent.get("empreinte") or empreinte_config(),
        "online": True,
        **instantane,
    }
    _ecrire_etat_atomique(etat, chemin)
    return etat


def lire_etat_kiosque(chemin: Optional[str] = None) -> Optional[dict]:
    """État déposé par le kiosque à son dernier boot, ou None."""
    chemin = chemin or ETAT_KIOSQUE_PATH
    if not os.path.exists(chemin):
        return None
    try:
        with open(chemin, encoding="utf-8") as f:
            etat = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return etat if isinstance(etat, dict) else None


def heartbeat_est_frais(
    etat: Optional[dict] = None,
    *,
    maintenant: Optional[float] = None,
    expiration_s: float = HEARTBEAT_EXPIRE_S,
) -> bool:
    """True si l'état runtime est récent et indique un kiosque en ligne."""
    etat = etat if etat is not None else lire_etat_kiosque()
    if not etat or not etat.get("online"):
        return False
    try:
        age = (maintenant or time.time()) - float(etat["heartbeat_ts"])
    except (KeyError, TypeError, ValueError):
        return False
    return -1.0 <= age <= expiration_s


def session_kiosque_active(etat: Optional[dict] = None) -> bool:
    """True uniquement pour une session confirmée par un heartbeat frais."""
    etat = etat if etat is not None else lire_etat_kiosque()
    return bool(heartbeat_est_frais(etat) and etat.get("session_active"))


class HeartbeatKiosque:
    """Publie un instantané runtime périodique depuis un thread daemon."""

    def __init__(
        self,
        fournisseur: Callable[[], dict],
        chemin: Optional[str] = None,
        intervalle_s: float = HEARTBEAT_INTERVALLE_S,
    ) -> None:
        self.fournisseur = fournisseur
        self.chemin = chemin or ETAT_KIOSQUE_PATH
        self.intervalle_s = intervalle_s
        self.boot_ts = time.time()
        self.empreinte = empreinte_config()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _instantane(self) -> dict:
        try:
            instantane = self.fournisseur()
            return instantane if isinstance(instantane, dict) else {}
        except Exception:
            return {"etat": "INCONNU", "session_active": False}

    def publier(self) -> dict:
        return ecrire_heartbeat_kiosque(
            self._instantane(),
            self.chemin,
            boot_ts=self.boot_ts,
            empreinte=self.empreinte,
        )

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.publier()
        self._thread = threading.Thread(
            target=self._boucle,
            daemon=True,
            name="kiosque-heartbeat",
        )
        self._thread.start()

    def _boucle(self) -> None:
        while not self._stop.wait(self.intervalle_s):
            self.publier()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.intervalle_s + 0.5))
        final = self._instantane()
        final.update({"online": False, "etat": "ARRETE", "session_active": False})
        ecrire_heartbeat_kiosque(
            final,
            self.chemin,
            boot_ts=self.boot_ts,
            empreinte=self.empreinte,
        )


def redemarrage_requis() -> Optional[bool]:
    """True si le disque a divergé de ce que le kiosque a chargé.

    None quand on ne peut pas savoir (kiosque jamais démarré depuis l'ajout de
    cet état, ou fichier illisible) — l'admin affiche alors « inconnu » plutôt
    qu'une alerte trompeuse.
    """
    etat = lire_etat_kiosque()
    if not etat or "empreinte" not in etat:
        return None
    return etat["empreinte"] != empreinte_config()
