# Fiabilisation de l'impression DNP DS620 — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qu'un manque de papier redevienne un incident de 30 secondes — recharger, appuyer sur RÉESSAYER — au lieu d'une panne nécessitant clavier, interface CUPS et plusieurs redémarrages.

**Architecture:** `core/printer.py` gagne un diagnostic basé sur les mots-clés IPP lus via `pycups` (repli `lpstat`), raisonne par **imprimante physique** et non par file CUPS, et sait réarmer une file dans le bon ordre (`cancel -a` **puis** `cupsenable`). Le kiosque affiche enfin la cause réelle, réarme via la touche RÉESSAYER existante, et prévient quand le papier s'épuise. Un script de déploiement dédié empêche CUPS de désactiver les files.

**Tech Stack:** Python 3, `pycups` (optionnel, pattern `try/except ImportError`), `subprocess` pour les commandes CUPS, pygame côté rendu, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-gestion-impression-dnp-design.md`

---

## Contexte pour l'ingénieur

Trois faits vérifiés sur la machine cible que tu ne devineras pas en lisant le code :

1. **`DNP_10x15` et `DNP_STRIP` pointent sur la même imprimante physique**
   (`gutenprint53+usb://dnp-ds620/DS6X54003557`). Un job coincé dans une file
   bloque l'autre. Le code actuel l'ignore.
2. **`pycups` est installé et fonctionne** sur la machine cible, mais **pas en
   CI ni sur le Mac de dev**. Tout code qui l'utilise doit dégrader proprement.
3. **`cupsenable` seul ne répare rien** : il redispatche le job en échec, qui
   replante l'imprimante. `cancel -a` doit venir **avant**. C'est le cœur du
   correctif — plusieurs tests le verrouillent explicitement.

Contraintes du projet (voir `CLAUDE.md`) : code et commits en **français** ;
`core/` ne doit jamais importer `ui/` ni `Photobooth_start` ; `ruff check .`
doit rester propre ; couverture `fail_under = 75`.

Le repo est sur `main` et propre. **Crée une branche avant le premier commit :**

```bash
git checkout -b impression-fiabilisation-dnp
```

---

## Structure des fichiers

| Fichier | Rôle | Action |
|---|---|---|
| `core/printer.py` | Diagnostic IPP, groupement par périphérique, réarmement | Modifier |
| `core/monitoring.py` | `MediaMonitor` — tirages restants, même pattern que `DiskMonitor` | Modifier |
| `config.py` | 3 réglages + 2 textes, whitelists et validation | Modifier |
| `Photobooth_start.py` | Affichage de la cause, RÉESSAYER réparateur, bandeau papier | Modifier |
| `deploy/configurer_cups.sh` | Politique CUPS `retry-job`, idempotent, autonome | Créer |
| `tests/test_printer.py` | Diagnostic, groupement, ordre du réarmement | Modifier |
| `tests/test_monitoring.py` | `MediaMonitor` | Modifier |
| `tests/test_impression_flow.py` | RÉESSAYER déclenche le réarmement | Modifier |
| `docs/CONFIG.md`, `docs/RUNBOOK.md`, `docs/DEPLOYMENT.md`, `docs/CHANGELOG.md` | Documentation | Modifier |

`core/printer.py` reste un module pur (`subprocess` + `pycups` optionnel), donc
entièrement testable en CI. `Photobooth_start.py` n'est pas testable en CI par
conception — ses tâches se vérifient par `ruff` et par un essai sur la machine.

---

## Task 1 : Afficher la cause réelle de l'erreur à l'écran

C'est le correctif le plus rentable du plan, et il est indépendant du reste.
`session.message_erreur_impression` est déjà calculé et loggé — il n'est
affiché nulle part. L'écran ne montre que « IMPRESSION NON ENVOYÉE », ce qui
oblige l'animateur à sortir du kiosque pour comprendre.

**Files:**
- Modify: `Photobooth_start.py:1539-1547` et `Photobooth_start.py:1634-1642`

- [ ] **Step 1 : Repérer les deux blocs identiques**

```bash
grep -n "TXT_IMPRESSION_ECHEC" Photobooth_start.py
```

Attendu : deux occurrences (~1540 et ~1635), dans deux fonctions de rendu
différentes, avec un bloc de code **strictement identique**.

- [ ] **Step 2 : Ajouter la ligne de cause sous le titre, aux deux endroits**

Le bloc actuel, présent deux fois :

```python
    elif session.erreur_impression:
        _dessiner_texte_centre_avec_garde(
            screen,
            config.TXT_IMPRESSION_ECHEC,
            font_alerte,
            config.COULEUR_ABANDON_TITRE,
            15,
            int(WIDTH * 0.8),
        )
```

Devient, aux deux endroits (utilise `replace_all`) :

```python
    elif session.erreur_impression:
        _dessiner_texte_centre_avec_garde(
            screen,
            config.TXT_IMPRESSION_ECHEC,
            font_alerte,
            config.COULEUR_ABANDON_TITRE,
            15,
            int(WIDTH * 0.8),
        )
        # La cause précise était calculée et loggée, mais jamais montrée :
        # l'animateur devait sortir du kiosque pour la connaître.
        if session.message_erreur_impression:
            _dessiner_texte_centre_avec_garde(
                screen,
                session.message_erreur_impression,
                font_bandeau,
                config.COULEUR_ABANDON_CONSIGNE,
                15 + font_alerte.get_height() + 8,
                int(WIDTH * 0.8),
            )
```

Attention : le second bloc (~1635) est précédé d'un `if` et non d'un `elif`.
Vérifie le contexte avant de remplacer ; adapte le mot-clé sans toucher au
reste.

- [ ] **Step 3 : Vérifier que le lint passe**

Run: `ruff check .`
Expected: `All checks passed!`

- [ ] **Step 4 : Vérifier la non-régression de la suite**

Run: `pytest -q`
Expected: 312 tests passés (aucun ne couvre le rendu pygame, on vérifie juste
qu'on n'a rien cassé à l'import).

- [ ] **Step 5 : Commit**

```bash
git add Photobooth_start.py
git commit -m "impression: afficher la cause reelle de l'echec sur l'ecran d'erreur"
```

---

## Task 2 : Réparer un test existant cassé

`tests/test_printer.py` contient un test vide de sens : `test_printing`
assertionne `result`, qui est le module `unittest.result` importé par erreur en
tête de fichier. Le test passe toujours, quoi qu'il arrive. On nettoie avant de
beaucoup modifier ce fichier.

**Files:**
- Modify: `tests/test_printer.py:8` et `tests/test_printer.py:62-66`

- [ ] **Step 1 : Constater que le test est vacant**

```bash
sed -n '8p;62,66p' tests/test_printer.py
```

Attendu : l'import `from unittest import result` et un `assert result is True or
result not in [...]` qui ne teste jamais la valeur de retour de `is_ready`.

- [ ] **Step 2 : Supprimer l'import parasite**

Retirer la ligne :

```python
from unittest import result
```

- [ ] **Step 3 : Corriger le test**

```python
    def test_printing(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "printer DNP_STRIP now printing job-42"
        ))
        assert mgr.is_ready("strips") is True
```

- [ ] **Step 4 : Vérifier**

Run: `pytest tests/test_printer.py -q`
Expected: tous les tests passent. Si `test_printing` échoue, c'est que le mock
renvoie la même sortie pour `lpstat -o` (jobs) et `lpstat -p` (état) : utilise
alors le dispatcher `_dispatch` déjà présent dans `test_reset_a_none_si_pret`.

- [ ] **Step 5 : Commit**

```bash
git add tests/test_printer.py
git commit -m "tests: reparer test_printing qui n'assertait rien"
```

---

## Task 3 : Table des raisons IPP et dataclass `EtatImprimante`

**Files:**
- Modify: `core/printer.py`
- Test: `tests/test_printer.py`

- [ ] **Step 1 : Écrire les tests qui échouent**

À ajouter à la fin de `tests/test_printer.py` :

```python
from core.printer import EtatImprimante, message_pour_raison, tirages_restants_depuis_marker


class TestMessagePourRaison:
    def test_papier_vide(self):
        assert message_pour_raison("media-empty") == "PAPIER ÉPUISÉ — recharger le bac"

    def test_suffixe_error_ignore(self):
        """Les mots-clés IPP portent des suffixes -error/-warning/-report."""
        assert message_pour_raison("media-empty-error") == "PAPIER ÉPUISÉ — recharger le bac"

    def test_suffixe_warning_ignore(self):
        assert message_pour_raison("media-jam-warning") == "BOURRAGE PAPIER"

    def test_suffixe_report_ignore(self):
        assert message_pour_raison("cover-open-report") == "CAPOT OUVERT"

    def test_imprimante_debranchee(self):
        assert message_pour_raison("connecting-to-device") == "IMPRIMANTE ÉTEINTE OU DÉBRANCHÉE"

    def test_raison_inconnue_affichee_brute(self):
        """Mieux vaut un code brut lisible qu'un message générique faux."""
        assert message_pour_raison("wedged") == "Imprimante : wedged"


class TestTiragesRestants:
    def test_message_gutenprint(self):
        msg = "228 native prints remaining on 6x4 (PC) media"
        assert tirages_restants_depuis_marker(msg) == 228

    def test_format_inattendu_renvoie_none(self):
        """Format changé → alerte inerte plutôt que fausse."""
        assert tirages_restants_depuis_marker("ribbon OK") is None

    def test_message_vide(self):
        assert tirages_restants_depuis_marker("") is None


class TestEtatImprimante:
    def test_defauts(self):
        etat = EtatImprimante(pret=True)
        assert etat.raison == ""
        assert etat.message == ""
        assert etat.file_desactivee is False
        assert etat.jobs == 0
        assert etat.tirages_restants is None
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `pytest tests/test_printer.py -q`
Expected: FAIL — `ImportError: cannot import name 'EtatImprimante' from 'core.printer'`

- [ ] **Step 3 : Implémenter dans `core/printer.py`**

Remplacer l'en-tête d'imports du module par :

```python
from __future__ import annotations
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from core.logger import log_info, log_critical, log_warning

try:
    import cups  # type: ignore
except ImportError:  # CI, macOS de dev : le diagnostic bascule sur lpstat
    cups = None  # type: ignore
```

Puis, avant la classe `PrinterManager` :

```python
# --- Diagnostic IPP -------------------------------------------------------
#
# CUPS expose la cause réelle d'un blocage dans `printer-state-reasons`, sous
# forme de mots-clés normalisés et NON localisés — contrairement au texte de
# `lpstat`, qui dépend de la langue du système. Les mots-clés portent un
# suffixe de gravité (`-error`, `-warning`, `-report`) qu'on retire avant de
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

# État IPP `printer-state` : 3 = idle, 4 = processing, 5 = stopped.
ETAT_IPP_ARRETE = 5

# marker-message de Gutenprint : "228 native prints remaining on 6x4 (PC) media".
# Chaîne produite en C par le backend, non traduite.
_RE_TIRAGES = re.compile(r"(\d+)\s+native prints remaining", re.IGNORECASE)


def normaliser_raison(raison: str) -> str:
    """Retire le suffixe de gravité d'un mot-clé IPP."""
    for suffixe in _SUFFIXES_GRAVITE:
        if raison.endswith(suffixe):
            return raison[: -len(suffixe)]
    return raison


def message_pour_raison(raison: str) -> str:
    """Traduit un mot-clé IPP en message affichable à l'animateur.

    Une raison inconnue est affichée telle quelle : un code brut lisible vaut
    mieux qu'un message générique qui induirait en erreur."""
    return _MESSAGES_RAISONS.get(normaliser_raison(raison), f"Imprimante : {raison}")


def tirages_restants_depuis_marker(marker_message: str) -> Optional[int]:
    """Nombre de tirages restants extrait du marker-message Gutenprint.

    Retourne None si le format change : l'alerte devient alors inerte plutôt
    que fausse."""
    if not marker_message:
        return None
    trouve = _RE_TIRAGES.search(marker_message)
    return int(trouve.group(1)) if trouve else None


@dataclass
class EtatImprimante:
    """Photo instantanée de l'imprimante physique (pas d'une seule file CUPS)."""

    pret: bool
    raison: str = ""              # mot-clé IPP brut, "" si aucun
    message: str = ""             # texte affichable, "" si prête
    file_desactivee: bool = False
    jobs: int = 0                 # cumulé sur toutes les files du périphérique
    tirages_restants: Optional[int] = None
```

- [ ] **Step 4 : Vérifier que les tests passent**

Run: `pytest tests/test_printer.py -q && ruff check .`
Expected: PASS + `All checks passed!`

- [ ] **Step 5 : Commit**

```bash
git add core/printer.py tests/test_printer.py
git commit -m "impression: table des raisons IPP et dataclass EtatImprimante"
```

---

## Task 4 : Raisonner par imprimante physique, pas par file CUPS

C'est la cause des réparations « à moitié » pendant l'incident : réarmer une
file laissait l'autre avec son job empoisonné, qui replantait la DS620.

**Files:**
- Modify: `core/printer.py`
- Test: `tests/test_printer.py`

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
class FakeCups:
    """Faux module pycups. Même rôle que FakeSerial dans tests/test_arduino.py."""

    def __init__(self, imprimantes):
        self._imprimantes = imprimantes

    def Connection(self):  # noqa: N802 — on imite l'API pycups
        return self

    def getPrinters(self):  # noqa: N802
        return self._imprimantes


DEUX_FILES_MEME_DS620 = {
    "DNP_10x15": {
        "device-uri": "gutenprint53+usb://dnp-ds620/DS6X54003557",
        "printer-state": 3,
        "printer-state-reasons": ["none"],
        "marker-message": "228 native prints remaining on 6x4 (PC) media",
    },
    "DNP_STRIP": {
        "device-uri": "gutenprint53+usb://dnp-ds620/DS6X54003557",
        "printer-state": 3,
        "printer-state-reasons": ["none"],
        "marker-message": "228 native prints remaining on 6x4 (PC) media",
    },
}


class TestGroupementParPeripherique:
    def test_files_partageant_le_device(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", FakeCups(DEUX_FILES_MEME_DS620))
        assert sorted(mgr._files_du_meme_device("10x15")) == ["DNP_10x15", "DNP_STRIP"]

    def test_devices_distincts_ne_sont_pas_groupes(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", FakeCups({
            "DNP_10x15": {"device-uri": "usb://dnp-ds620/A", "printer-state": 3,
                          "printer-state-reasons": ["none"]},
            "DNP_STRIP": {"device-uri": "cups-pdf:/", "printer-state": 3,
                          "printer-state-reasons": ["none"]},
        }))
        assert mgr._files_du_meme_device("10x15") == ["DNP_10x15"]

    def test_sans_pycups_repli_conservateur(self, mgr, monkeypatch):
        """Sans pycups on ne peut pas savoir : on groupe, quitte à vérifier
        une file de trop. L'inverse laisserait un job empoisonné en place."""
        monkeypatch.setattr(printer, "cups", None)
        assert sorted(mgr._files_du_meme_device("10x15")) == ["DNP_10x15", "DNP_STRIP"]

    def test_mode_inconnu(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", FakeCups(DEUX_FILES_MEME_DS620))
        assert mgr._files_du_meme_device("xxx") == []
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `pytest tests/test_printer.py::TestGroupementParPeripherique -q`
Expected: FAIL — `AttributeError: 'PrinterManager' object has no attribute '_files_du_meme_device'`

- [ ] **Step 3 : Implémenter dans `PrinterManager`**

```python
    def _imprimantes_cups(self) -> Optional[dict]:
        """Attributs IPP de toutes les files, ou None si pycups indisponible."""
        if cups is None:
            return None
        try:
            return cups.Connection().getPrinters()
        except Exception as e:
            log_warning(f"CUPS injoignable via pycups : {e}")
            return None

    def _files_du_meme_device(self, mode: str) -> list[str]:
        """Files CUPS partageant l'imprimante physique du mode demandé.

        Les deux files DNP pointent sur la même DS620 : un job coincé dans
        l'une bloque l'autre. Sans pycups on ne peut pas lire `device-uri` —
        on retourne alors toutes les files configurées. C'est le repli sûr :
        vérifier une file de trop est sans effet, en oublier une laisse un job
        empoisonné qui replantera l'imprimante."""
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
```

- [ ] **Step 4 : Vérifier**

Run: `pytest tests/test_printer.py -q && ruff check .`
Expected: PASS + `All checks passed!`

- [ ] **Step 5 : Commit**

```bash
git add core/printer.py tests/test_printer.py
git commit -m "impression: grouper les files CUPS par imprimante physique"
```

---

## Task 5 : `diagnostic()` et `is_ready()` réécrit par-dessus

**Files:**
- Modify: `core/printer.py`
- Test: `tests/test_printer.py`

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
def _cups_avec(raison="none", etat=3, marker="228 native prints remaining on 6x4 (PC) media"):
    """Deux files sur la même DS620, dans l'état demandé."""
    attrs = {
        "device-uri": "gutenprint53+usb://dnp-ds620/DS6X54003557",
        "printer-state": etat,
        "printer-state-reasons": [raison],
        "marker-message": marker,
    }
    return FakeCups({"DNP_10x15": dict(attrs), "DNP_STRIP": dict(attrs)})


class TestDiagnostic:
    def test_imprimante_prete(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", _cups_avec())
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(""))
        etat = mgr.diagnostic("10x15")
        assert etat.pret is True
        assert etat.message == ""
        assert etat.tirages_restants == 228

    def test_papier_vide(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", _cups_avec(raison="media-empty-error", etat=5))
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(""))
        etat = mgr.diagnostic("10x15")
        assert etat.pret is False
        assert etat.message == "PAPIER ÉPUISÉ — recharger le bac"
        assert etat.file_desactivee is True

    def test_file_arretee_sans_raison(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", _cups_avec(etat=5))
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(""))
        etat = mgr.diagnostic("10x15")
        assert etat.file_desactivee is True
        assert etat.message == "FILE D'IMPRESSION ARRÊTÉE"

    def test_jobs_cumules_sur_les_deux_files(self, mgr, monkeypatch):
        """Un strip coincé doit bloquer un 10x15 : même imprimante."""
        monkeypatch.setattr(printer, "cups", _cups_avec())
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "DNP_10x15-42 photobooth 1024\n"
        ))
        etat = mgr.diagnostic("10x15")
        assert etat.jobs == 2          # une ligne par file, deux files
        assert etat.pret is False
        assert etat.message == "TIRAGE EN ATTENTE"

    def test_marker_illisible_tirages_none(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", _cups_avec(marker="ribbon OK"))
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(""))
        assert mgr.diagnostic("10x15").tirages_restants is None

    def test_mode_inconnu(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", _cups_avec())
        etat = mgr.diagnostic("xxx")
        assert etat.pret is False
        assert etat.message == "MODE INCONNU"


class TestReplisSansPycups:
    """Sans pycups, on retombe sur le diagnostic grossier historique."""

    def test_idle_est_pret(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", None)

        def _dispatch(cmd, **kw):
            if "-o" in cmd:
                return SimpleNamespace(stdout="", stderr="", returncode=0)
            return SimpleNamespace(stdout="printer DNP_10x15 is idle. enabled",
                                   stderr="", returncode=0)

        monkeypatch.setattr(printer.subprocess, "run", _dispatch)
        assert mgr.diagnostic("10x15").pret is True

    def test_disabled_detecte(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", None)

        def _dispatch(cmd, **kw):
            if "-o" in cmd:
                return SimpleNamespace(stdout="", stderr="", returncode=0)
            return SimpleNamespace(stdout="printer DNP_10x15 disabled since lundi",
                                   stderr="", returncode=0)

        monkeypatch.setattr(printer.subprocess, "run", _dispatch)
        etat = mgr.diagnostic("10x15")
        assert etat.file_desactivee is True
        assert etat.pret is False
```

Mets aussi à jour le test existant `TestLastError::test_file_pleine_memorise`,
dont le message change volontairement — un job en attente n'est plus une file
saturée mais un tirage qui attend du papier :

```python
    def test_file_pleine_memorise(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", None)
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "DNP_10x15-42 photobooth 1024 ..."
        ))
        assert mgr.is_ready("10x15") == "TIRAGE EN ATTENTE"
        assert mgr.last_error == "TIRAGE EN ATTENTE"
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `pytest tests/test_printer.py -q`
Expected: FAIL — `AttributeError: 'PrinterManager' object has no attribute 'diagnostic'`

- [ ] **Step 3 : Implémenter**

Renomme d'abord la méthode existante `jobs_en_attente` en
`jobs_en_attente_file`, qui garde son corps actuel inchangé mais prend un **nom
de file** au lieu d'un mode :

```python
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
        """Jobs en attente sur l'imprimante physique du mode (toutes files)."""
        files = self._files_du_meme_device(mode)
        if not files:
            return None
        return sum(self.jobs_en_attente_file(f) or 0 for f in files)
```

Puis ajoute le diagnostic et remplace intégralement `is_ready` :

```python
    def diagnostic(self, mode: str) -> EtatImprimante:
        """État de l'imprimante physique servant ce mode.

        Lit `printer-state-reasons` via pycups quand il est disponible : ce
        sont des mots-clés IPP normalisés, contrairement au texte localisé de
        `lpstat`. Sans pycups, repli sur un diagnostic à trois catégories."""
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
        """Repli sans pycups : trois catégories seulement.

        Le texte de `lpstat` est localisé, on ne prétend pas à un diagnostic
        fin — juste à ne pas être moins bon que le code historique."""
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

    def is_ready(self, mode: str):
        """True si prête, sinon une chaîne décrivant le problème.

        Mince enveloppe autour de `diagnostic()` : le contrat historique est
        conservé pour `Photobooth_start.py` et `web/routes/dashboard.py`."""
        etat = self.diagnostic(mode)
        if etat.pret:
            self.last_error = None
            return True
        return self._echec(etat.message)
```

- [ ] **Step 4 : Vérifier**

Run: `pytest tests/test_printer.py tests/test_web_app.py -q && ruff check .`
Expected: PASS + `All checks passed!`

Si `tests/test_web_app.py` échoue, c'est que `_pastille_imprimante`
(`web/routes/dashboard.py:93`) reçoit un compte de jobs cumulé sur deux files
au lieu d'une. C'est le comportement voulu ; ajuste l'attente du test.

- [ ] **Step 5 : Commit**

```bash
git add core/printer.py tests/test_printer.py tests/test_web_app.py
git commit -m "impression: diagnostic IPP par imprimante, is_ready devient une enveloppe"
```

---

## Task 6 : `reamorcer()` — purger **puis** réactiver

Le cœur du correctif. L'ordre est verrouillé par un test : `cupsenable` d'abord
redispatcherait le job en échec, qui replanterait l'imprimante.

**Files:**
- Modify: `core/printer.py`
- Test: `tests/test_printer.py`

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
class TestReamorcer:
    @staticmethod
    def _tracer(monkeypatch):
        """Enregistre l'ordre exact des commandes CUPS lancées."""
        appels = []

        def _run(cmd, **kw):
            appels.append(list(cmd))
            if "-o" in cmd:
                return SimpleNamespace(stdout="", stderr="", returncode=0)
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        monkeypatch.setattr(printer.subprocess, "run", _run)
        monkeypatch.setattr(printer.time, "sleep", lambda _s: None)
        return appels

    def test_cancel_avant_cupsenable(self, mgr, monkeypatch):
        """LE test du correctif. Réactiver avant de purger relance le job en
        échec, qui redésactive la file — c'est la boucle vécue en événement."""
        monkeypatch.setattr(printer, "cups", _cups_avec(raison="media-empty-error", etat=5))
        appels = self._tracer(monkeypatch)

        mgr.reamorcer("10x15", delai_max_s=0.0)

        index_cancel = next(i for i, c in enumerate(appels) if c[0] == "cancel")
        index_enable = next(i for i, c in enumerate(appels) if c[0] == "cupsenable")
        assert index_cancel < index_enable

    def test_traite_les_deux_files(self, mgr, monkeypatch):
        """Réarmer une seule file laissait l'autre replanter l'imprimante."""
        monkeypatch.setattr(printer, "cups", _cups_avec(raison="media-empty-error", etat=5))
        appels = self._tracer(monkeypatch)

        mgr.reamorcer("10x15", delai_max_s=0.0)

        purgees = {c[2] for c in appels if c[0] == "cancel"}
        reactivees = {c[1] for c in appels if c[0] == "cupsenable"}
        assert purgees == {"DNP_10x15", "DNP_STRIP"}
        assert reactivees == {"DNP_10x15", "DNP_STRIP"}

    def test_ne_touche_aucune_file_hors_dnp(self, mgr, monkeypatch):
        """La machine héberge une dizaine d'imprimantes de bureau."""
        monkeypatch.setattr(printer, "cups", _cups_avec(raison="media-empty-error", etat=5))
        appels = self._tracer(monkeypatch)

        mgr.reamorcer("10x15", delai_max_s=0.0)

        cibles = {c[-1] for c in appels if c[0] in ("cancel", "cupsenable", "cupsaccept")}
        assert cibles <= {"DNP_10x15", "DNP_STRIP"}

    def test_attente_bornee(self, mgr, monkeypatch):
        """Imprimante injoignable : on abandonne, on ne boucle pas."""
        monkeypatch.setattr(printer, "cups", _cups_avec(raison="connecting-to-device"))
        self._tracer(monkeypatch)

        faux_temps = {"t": 0.0}
        monkeypatch.setattr(printer.time, "monotonic", lambda: faux_temps["t"])

        def _dormir(_s):
            faux_temps["t"] += 1.0

        monkeypatch.setattr(printer.time, "sleep", _dormir)

        mgr.reamorcer("10x15", delai_max_s=5.0)
        assert faux_temps["t"] <= 6.0

    def test_mode_inconnu(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", _cups_avec())
        self._tracer(monkeypatch)
        assert mgr.reamorcer("xxx").message == "MODE INCONNU"
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `pytest tests/test_printer.py::TestReamorcer -q`
Expected: FAIL — `AttributeError: 'PrinterManager' object has no attribute 'reamorcer'`

- [ ] **Step 3 : Implémenter**

```python
    def _commande_cups(self, cmd: list[str], libelle: str) -> bool:
        """Lance une commande CUPS, journalise, ne lève jamais."""
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            log_info(f"CUPS : {libelle} OK")
            return True
        except subprocess.CalledProcessError as e:
            log_critical(f"CUPS : échec {libelle} : {e.stderr}")
        except FileNotFoundError:
            log_critical(f"CUPS : commande '{cmd[0]}' introuvable ({libelle})")
        except Exception as e:
            log_critical(f"CUPS : erreur {libelle} : {e}")
        return False

    def _attendre_imprimante(self, mode: str, delai_max_s: float) -> None:
        """Attend que la DS620 réponde, au plus `delai_max_s`.

        Après un changement de rouleau, l'imprimante met une vingtaine de
        secondes à relire le ribbon. Réactiver la file avant qu'elle réponde
        relance un job qui échoue aussitôt."""
        echeance = time.monotonic() + delai_max_s
        while time.monotonic() < echeance:
            raison = normaliser_raison(self.diagnostic(mode).raison)
            if raison not in ("connecting-to-device", "timed-out"):
                return
            time.sleep(1.0)
        log_warning(f"Imprimante toujours injoignable après {delai_max_s:.0f} s")

    def reamorcer(self, mode: str, delai_max_s: float = 30.0) -> EtatImprimante:
        """Purge les jobs puis réactive toutes les files de l'imprimante.

        L'ORDRE EST LE CORRECTIF. `cupsenable` seul redispatche immédiatement
        le job qui a provoqué l'erreur ; il échoue de nouveau et CUPS
        redésactive la file. C'est exactement la boucle vécue en événement,
        que ni le redémarrage du PC ni plusieurs « Démarrer l'imprimante »
        n'ont cassée.

        Les deux files DNP partageant une seule DS620, elles sont traitées
        ensemble : en réarmer une seule laisse l'autre replanter l'imprimante.
        """
        files = self._files_du_meme_device(mode)
        if not files:
            return EtatImprimante(pret=False, raison="mode-inconnu", message="MODE INCONNU")

        log_info(f"🔧 Réamorçage de {', '.join(files)}...")

        # 1. Purger d'abord — sinon l'étape 3 relance le job en échec.
        for nom_file in files:
            self._commande_cups(["cancel", "-a", nom_file], f"purge de {nom_file}")

        # 2. Laisser à la DS620 le temps de répondre après un changement de média.
        self._attendre_imprimante(mode, delai_max_s)

        # 3. Réactiver, files vides.
        for nom_file in files:
            self._commande_cups(["cupsenable", nom_file], f"réactivation de {nom_file}")
            self._commande_cups(["cupsaccept", nom_file], f"réouverture de {nom_file}")

        etat = self.diagnostic(mode)
        log_info(f"Réamorçage terminé : {etat.message or 'imprimante prête'}")
        return etat
```

- [ ] **Step 4 : Vérifier**

Run: `pytest tests/test_printer.py -q && ruff check .`
Expected: PASS + `All checks passed!`

- [ ] **Step 5 : Commit**

```bash
git add core/printer.py tests/test_printer.py
git commit -m "impression: reamorcer() purge les files avant de les reactiver"
```

---

## Task 7 : Réglages et textes dans `config.py`

**Files:**
- Modify: `config.py`
- Test: `tests/test_config_overrides.py`

- [ ] **Step 1 : Ajouter les réglages après le bloc température (`config.py:461`)**

```python
# --- Monitoring média imprimante (tirages restants) ---
# Gutenprint remonte "N native prints remaining" dans marker-message. On
# prévient l'animateur avant la panne sèche plutôt que de la subir en pleine
# soirée. Si le backend ne remonte rien, l'alerte est inerte silencieusement.
SEUIL_TIRAGES_RESTANTS     = 20
INTERVALLE_CHECK_MEDIA_S   = 120.0

# --- Réamorçage d'une file CUPS désactivée ---
# Attente maximale que la DS620 réponde après un changement de rouleau, avant
# de réactiver la file. Réactiver trop tôt relance un job qui échoue aussitôt.
DELAI_REAMORCAGE_S         = 30.0
```

- [ ] **Step 2 : Ajouter les textes après `TXT_IMPRESSION_AIDE_MESSAGE` (`config.py:417`)**

```python
TXT_REAMORCAGE          = "Réarmement de l'imprimante..."
TXT_ALERTE_PAPIER       = "PAPIER BIENTÔT ÉPUISÉ"
```

- [ ] **Step 3 : Déclarer les surcharges admin**

Dans `_CONFIG_OVERRIDES_WHITELIST` (`config.py:554`), après
`"SEUIL_TEMP_CRITIQUE_C": float,` :

```python
    "SEUIL_TIRAGES_RESTANTS": int,
    "INTERVALLE_CHECK_MEDIA_S": float,
    "DELAI_REAMORCAGE_S": float,
```

Dans `_CONFIG_OVERRIDES_BOURNES` (`config.py:580`), après
`"SEUIL_TEMP_CRITIQUE_C": (10.0, 100.0),` :

```python
    "SEUIL_TIRAGES_RESTANTS": (0, 10000),
    "INTERVALLE_CHECK_MEDIA_S": (10.0, 3600.0),
    "DELAI_REAMORCAGE_S": (5.0, 120.0),
```

Dans `_ECRANS_OVERRIDES_WHITELIST` (`config.py:659`), après
`"TXT_IMPRESSION_AIDE_MESSAGE": (str, 1, _LONG_TEXTE_MAX),` :

```python
    "TXT_REAMORCAGE": (str, 1, _LONG_TEXTE_MAX),
    "TXT_ALERTE_PAPIER": (str, 1, _LONG_TEXTE_MAX),
```

- [ ] **Step 4 : Ajouter la validation dans `_valider_config()` (`config.py:935`)**

Après `assert INTERVALLE_CHECK_TEMP_S > 0` :

```python
    assert SEUIL_TIRAGES_RESTANTS >= 0, f"SEUIL_TIRAGES_RESTANTS invalide : {SEUIL_TIRAGES_RESTANTS}"
    assert INTERVALLE_CHECK_MEDIA_S > 0, f"INTERVALLE_CHECK_MEDIA_S invalide : {INTERVALLE_CHECK_MEDIA_S}"
    assert DELAI_REAMORCAGE_S > 0, f"DELAI_REAMORCAGE_S invalide : {DELAI_REAMORCAGE_S}"
```

- [ ] **Step 5 : Vérifier**

Run: `python3 -c "import config; print(config.SEUIL_TIRAGES_RESTANTS, config.DELAI_REAMORCAGE_S)" && pytest tests/test_config_overrides.py -q && ruff check .`
Expected: `20 30.0`, puis PASS + `All checks passed!`

- [ ] **Step 6 : Documenter et commiter**

Ajoute les trois réglages et les deux textes à `docs/CONFIG.md`, dans les
sections correspondantes, avec leurs bornes.

```bash
git add config.py docs/CONFIG.md
git commit -m "config: seuil de tirages restants, intervalle media et delai de reamorcage"
```

---

## Task 8 : RÉESSAYER réarme la file

Aucun bouton nouveau : le boîtier n'en a que trois, tous déjà utilisés sur
l'écran d'erreur. L'appui sur RÉESSAYER vaut confirmation humaine que le papier
est rechargé — rien ne se répare automatiquement.

**Files:**
- Modify: `Photobooth_start.py:1755-1768` (`_handle_erreur_impression`)
- Test: `tests/test_impression_flow.py`

- [ ] **Step 1 : Écrire le test qui échoue**

À ajouter dans `tests/test_impression_flow.py`, en suivant le style des tests
existants du fichier (`monkeypatch` sur `app.printer_mgr`) :

```python
def test_reessayer_reamorce_si_file_desactivee(monkeypatch, session):
    """Le cas de l'incident : la file est désactivée, RÉESSAYER doit la purger
    et la réactiver avant de relancer, sinon le job en échec repart et
    replante l'imprimante."""
    from core.printer import EtatImprimante

    appels = []
    monkeypatch.setattr(
        app.printer_mgr, "diagnostic",
        lambda _mode: EtatImprimante(pret=False, raison="media-empty-error",
                                     message="PAPIER ÉPUISÉ — recharger le bac",
                                     file_desactivee=True),
    )
    monkeypatch.setattr(
        app.printer_mgr, "reamorcer",
        lambda _mode, **kw: appels.append("reamorcer") or EtatImprimante(pret=True),
    )
    monkeypatch.setattr(app, "traiter_impression_session",
                        lambda _s: appels.append("impression") or "printed")
    monkeypatch.setattr(app, "executer_avec_spinner", lambda f, _msg: f())
    monkeypatch.setattr(app, "terminer_session_et_revenir_accueil", lambda _issue: None)
    monkeypatch.setattr(app, "_verifier_quota_ou_debloquer", lambda _s: True)

    session.erreur_impression = True
    app._handle_erreur_impression(
        SimpleNamespace(key=app.TOUCHE_MILIEU), session, time.time()
    )

    assert appels == ["reamorcer", "impression"]


def test_reessayer_ne_reamorce_pas_si_file_saine(monkeypatch, session):
    """Pas de purge gratuite quand la file va bien : on perdrait un job en cours."""
    from core.printer import EtatImprimante

    appels = []
    monkeypatch.setattr(app.printer_mgr, "diagnostic",
                        lambda _mode: EtatImprimante(pret=True))
    monkeypatch.setattr(app.printer_mgr, "reamorcer",
                        lambda _mode, **kw: appels.append("reamorcer"))
    monkeypatch.setattr(app, "traiter_impression_session",
                        lambda _s: appels.append("impression") or "printed")
    monkeypatch.setattr(app, "terminer_session_et_revenir_accueil", lambda _issue: None)
    monkeypatch.setattr(app, "_verifier_quota_ou_debloquer", lambda _s: True)

    session.erreur_impression = True
    app._handle_erreur_impression(
        SimpleNamespace(key=app.TOUCHE_MILIEU), session, time.time()
    )

    assert appels == ["impression"]
```

Vérifie les imports en tête du fichier de test (`SimpleNamespace`, `time`) et
la fixture `session` : reprends exactement celles déjà utilisées par les tests
voisins plutôt que d'en créer de nouvelles.

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `pytest tests/test_impression_flow.py -q -k reessayer`
Expected: FAIL — `reamorcer` n'est jamais appelé, `appels == ["impression"]`
dans les deux tests.

- [ ] **Step 3 : Implémenter**

Dans `Photobooth_start.py`, ajoute `DELAI_REAMORCAGE_S` à l'import de `config`
en tête de fichier, puis remplace la branche `TOUCHE_MILIEU` de
`_handle_erreur_impression` :

```python
    if event.key == TOUCHE_MILIEU:
        _journaliser_action(
            "retry_print",
            remaining_copies=session.impressions_restantes,
        )
        if not _verifier_quota_ou_debloquer(session):
            session.dernier_clic_time = maintenant
            pygame.event.clear()
            return

        # L'appui vaut confirmation que le papier est rechargé. On purge la
        # file AVANT de la réactiver : sinon le job en échec repart et
        # redésactive l'imprimante (la boucle vécue en événement).
        etat = printer_mgr.diagnostic(session.mode_actuel)
        if etat.file_desactivee:
            _journaliser_action("printer_reset", raison=etat.raison)
            executer_avec_spinner(
                lambda: printer_mgr.reamorcer(session.mode_actuel, DELAI_REAMORCAGE_S),
                config.TXT_REAMORCAGE,
            )

        issue = traiter_impression_session(session)
        pygame.event.clear()
        if issue != "print_failed":
            terminer_session_et_revenir_accueil(issue)
        session.dernier_clic_time = maintenant
        return
```

`executer_avec_spinner` est déjà disponible : c'est une globale déclarée
`Photobooth_start.py:445` et affectée par `_initialiser_runtime()`. Rien à
importer.

- [ ] **Step 4 : Vérifier**

Run: `pytest tests/test_impression_flow.py -q && ruff check .`
Expected: PASS + `All checks passed!`

- [ ] **Step 5 : Commit**

```bash
git add Photobooth_start.py tests/test_impression_flow.py
git commit -m "impression: la touche REESSAYER rearme la file CUPS desactivee"
```

---

## Task 9 : `MediaMonitor` — surveiller les tirages restants

**Files:**
- Modify: `core/monitoring.py`
- Test: `tests/test_monitoring.py`

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
from core.monitoring import MediaMonitor


class FauxPrinter:
    def __init__(self, tirages):
        self.tirages = tirages
        self.appels = 0

    def diagnostic(self, _mode):
        self.appels += 1
        return SimpleNamespace(tirages_restants=self.tirages)


class TestMediaMonitor:
    def test_au_dessus_du_seuil(self):
        mon = MediaMonitor(FauxPrinter(228), "10x15", seuil_tirages=20, intervalle_s=0.0)
        mon.tick()
        assert mon.critique is False
        assert mon.tirages_restants == 228

    def test_sous_le_seuil(self):
        mon = MediaMonitor(FauxPrinter(12), "10x15", seuil_tirages=20, intervalle_s=0.0)
        mon.tick()
        assert mon.critique is True

    def test_seuil_atteint_exactement(self):
        mon = MediaMonitor(FauxPrinter(20), "10x15", seuil_tirages=20, intervalle_s=0.0)
        mon.tick()
        assert mon.critique is True

    def test_warning_une_seule_fois(self, monkeypatch):
        """Même contrat que DiskMonitor : log à la transition uniquement."""
        warnings = []
        monkeypatch.setattr("core.monitoring.log_warning", lambda m: warnings.append(m))
        mon = MediaMonitor(FauxPrinter(5), "10x15", seuil_tirages=20, intervalle_s=0.0)
        mon.tick()
        mon.tick()
        assert len(warnings) == 1

    def test_rate_limite(self):
        faux = FauxPrinter(228)
        mon = MediaMonitor(faux, "10x15", seuil_tirages=20, intervalle_s=120.0)
        mon.tick(maintenant=1000.0)
        mon.tick(maintenant=1001.0)
        assert faux.appels == 1

    def test_inerte_si_backend_muet(self):
        """marker-message illisible → ni alerte ni fausse information."""
        mon = MediaMonitor(FauxPrinter(None), "10x15", seuil_tirages=20, intervalle_s=0.0)
        mon.tick()
        assert mon.critique is False
        assert mon.tirages_restants is None

    def test_ignore_pendant_une_impression(self):
        """Ne pas interroger CUPS pendant un envoi."""
        faux = FauxPrinter(228)
        mon = MediaMonitor(faux, "10x15", seuil_tirages=20, intervalle_s=0.0)
        mon.tick(occupe=True)
        assert faux.appels == 0

    def test_exception_avalee(self, monkeypatch):
        class PrinterCasse:
            def diagnostic(self, _mode):
                raise RuntimeError("CUPS injoignable")

        warnings = []
        monkeypatch.setattr("core.monitoring.log_warning", lambda m: warnings.append(m))
        mon = MediaMonitor(PrinterCasse(), "10x15", seuil_tirages=20, intervalle_s=0.0)
        mon.tick()
        assert mon.critique is False
        assert len(warnings) == 1
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `pytest tests/test_monitoring.py -q -k Media`
Expected: FAIL — `ImportError: cannot import name 'MediaMonitor'`

- [ ] **Step 3 : Implémenter, après `TempMonitor` dans `core/monitoring.py`**

```python
class MediaMonitor:
    """Monitore les tirages restants sur l'imprimante, expose un flag critique.

    Même pattern que DiskMonitor et TempMonitor : `tick()` rate-limité, flag
    `critique`, warning loggé à la seule transition OK→critique.

    Le PrinterManager est injecté (duck-typing sur `.diagnostic(mode)`) pour
    que `core/monitoring.py` n'ait pas à importer `core/printer.py`.

    Si le backend ne remonte pas de nombre de tirages, `tirages_restants` reste
    None et le monitor est inerte silencieusement — comme TempMonitor hors
    Raspberry Pi.

    Usage :
        media = MediaMonitor(printer_mgr, "10x15", seuil_tirages=20, intervalle_s=120)
        while running:
            media.tick(occupe=session.impression_en_cours)
            if media.critique:
                afficher_bandeau_alerte(media.tirages_restants)
    """

    def __init__(self, printer_mgr, mode: str, seuil_tirages: int,
                 intervalle_s: float) -> None:
        self.printer_mgr = printer_mgr
        self.mode = mode
        self.seuil_tirages = seuil_tirages
        self.intervalle_s = intervalle_s
        self._dernier_check_ts: float = 0.0
        self.critique: bool = False
        self.tirages_restants: Optional[int] = None

    def tick(self, maintenant: Optional[float] = None, occupe: bool = False) -> None:
        """Check périodique. `occupe=True` (impression en cours) court-circuite
        le check pour ne pas interroger CUPS pendant un envoi."""
        if occupe:
            return
        if maintenant is None:
            maintenant = time.time()
        if maintenant - self._dernier_check_ts < self.intervalle_s:
            return
        self._dernier_check_ts = maintenant
        try:
            etat = self.printer_mgr.diagnostic(self.mode)
        except Exception as e:
            log_warning(f"Check média périodique échoué : {e}")
            return

        self.tirages_restants = etat.tirages_restants
        if self.tirages_restants is None:
            self.critique = False
            return

        etait_critique = self.critique
        self.critique = self.tirages_restants <= self.seuil_tirages
        if self.critique and not etait_critique:
            log_warning(
                f"Papier bientôt épuisé : {self.tirages_restants} tirages restants "
                f"(seuil : {self.seuil_tirages})"
            )
```

Mets à jour le docstring du module en tête de `core/monitoring.py` pour y
mentionner `MediaMonitor` aux côtés de `DiskMonitor` et `TempMonitor`.

- [ ] **Step 4 : Vérifier**

Run: `pytest tests/test_monitoring.py -q && ruff check .`
Expected: PASS + `All checks passed!`

- [ ] **Step 5 : Commit**

```bash
git add core/monitoring.py tests/test_monitoring.py
git commit -m "monitoring: MediaMonitor pour les tirages restants sur la DNP"
```

---

## Task 10 : Bandeau d'alerte papier sur l'accueil

**Files:**
- Modify: `Photobooth_start.py` (imports, instanciation ~`:508`, `_render_accueil_normal` ~`:1156`, `render_accueil` ~`:1177`)

- [ ] **Step 1 : Importer les nouveaux réglages et le monitor**

Ajoute `SEUIL_TIRAGES_RESTANTS` et `INTERVALLE_CHECK_MEDIA_S` à l'import de
`config`, et `MediaMonitor` à l'import existant depuis `core.monitoring`
(`Photobooth_start.py:297`).

- [ ] **Step 2 : Déclarer et instancier la globale**

Les monitors sont des globales déclarées au niveau module puis affectées dans
`_initialiser_runtime()`. Trois endroits à toucher.

Après `Photobooth_start.py:328` (déclaration module, à côté de `disk_monitor`) :

```python
media_monitor: "MediaMonitor | None" = None
```

Dans la liste `global` de `_initialiser_runtime()` (`Photobooth_start.py:447`),
ajouter `media_monitor` :

```python
    global arduino_ctrl, disk_monitor, temp_monitor, media_monitor, BANDEAU_CACHE, session, running
```

Puis, après l'instanciation de `temp_monitor` (~`:512`) :

```python
    media_monitor = MediaMonitor(
        printer_mgr, "10x15",
        seuil_tirages=SEUIL_TIRAGES_RESTANTS,
        intervalle_s=INTERVALLE_CHECK_MEDIA_S,
    )
```

Le mode `"10x15"` est arbitraire et sans conséquence : les deux files partagent
la même DS620, donc le même niveau de média.

- [ ] **Step 3 : Déclencher le check dans `render_accueil` (~`:1177`)**

```python
    disk_monitor.tick()
    temp_monitor.tick()
    media_monitor.tick(occupe=session.impression_en_cours)
```

- [ ] **Step 4 : Ajouter le troisième bandeau**

Dans `_render_accueil_normal`, à la suite du bandeau température, en réutilisant
l'accumulateur `y_alerte` déjà en place. Le bandeau température ne l'incrémente
pas aujourd'hui car il était le dernier — ajoute `y_alerte += alerte_h` à la fin
de son bloc, puis :

```python
    if media_monitor.critique and media_monitor.tirages_restants is not None:
        alerte = pygame.Surface((WIDTH, alerte_h), pygame.SRCALPHA)
        alerte.fill((200, 160, 20, 220))
        screen.blit(alerte, (0, y_alerte))
        txt_alerte = font_bandeau.render(
            f"⚠ {config.TXT_ALERTE_PAPIER} — {media_monitor.tirages_restants} tirages restants",
            True, (255, 255, 255),
        )
        screen.blit(
            txt_alerte,
            (WIDTH // 2 - txt_alerte.get_width() // 2,
             y_alerte + (alerte_h - txt_alerte.get_height()) // 2),
        )
```

- [ ] **Step 5 : Vérifier**

Run: `pytest -q && ruff check .`
Expected: PASS + `All checks passed!`

- [ ] **Step 6 : Commit**

```bash
git add Photobooth_start.py
git commit -m "accueil: bandeau d'alerte quand le papier arrive en fin de rouleau"
```

---

## Task 11 : Script de configuration CUPS

Script **autonome** plutôt qu'une étape de `install.sh` : la machine de
production est un mini-PC x86 démarré par autostart XFCE, où `install.sh`
(systemd) n'est pas exécuté.

**Files:**
- Create: `deploy/configurer_cups.sh`

- [ ] **Step 1 : Écrire le script**

```bash
#!/usr/bin/env bash
# configurer_cups.sh — empêche CUPS de désactiver les files DNP sur erreur.
#
# À lancer UNE FOIS sur la machine du photobooth :
#   sudo ./deploy/configurer_cups.sh
#
# Idempotent : relançable sans risque.
#
# Pourquoi : par défaut CUPS applique ErrorPolicy=stop-printer. Une panne de
# papier désactive la file ET y laisse le job. Au rechargement, réactiver la
# file redispatche ce job, qui échoue de nouveau et redésactive la file.
# Avec retry-job, la file reste active et le tirage repart tout seul dès que
# le papier revient.

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
```

- [ ] **Step 2 : Rendre exécutable et vérifier la syntaxe**

```bash
chmod +x deploy/configurer_cups.sh && bash -n deploy/configurer_cups.sh
```

Expected: aucune sortie (syntaxe valide). Ne lance **pas** le script depuis le
Mac de dev : il n'y a ni les files DNP ni CUPS configuré.

- [ ] **Step 3 : Commit**

```bash
git add deploy/configurer_cups.sh
git commit -m "deploy: script de configuration CUPS retry-job pour les files DNP"
```

---

## Task 12 : Documentation

**Files:**
- Modify: `docs/RUNBOOK.md:129`, `docs/DEPLOYMENT.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- [ ] **Step 1 : Corriger le runbook**

La ligne 129 décrit aujourd'hui la manipulation manuelle que ce travail
supprime (`lpstat -o` → `cancel -a` → relancer). Remplace-la par :

```markdown
| Photo prise mais imprimante silencieuse | File CUPS bloquée | Appuyer sur RÉESSAYER : le kiosque purge la file et la réactive. La cause exacte s'affiche à l'écran. |
| Message « PAPIER ÉPUISÉ » | Fin de rouleau | Charger le rouleau, éteindre/rallumer la DS620, attendre 30 s, puis RÉESSAYER. |
| Réarmement impossible | Utilisateur hors du groupe `lpadmin` | `sudo usermod -aG lpadmin photobooth` puis relancer `sudo ./deploy/configurer_cups.sh` |
```

Ajoute aussi, dans la section diagnostic, la commande qui donne la cause brute :

```bash
ipptool -tv ipp://localhost/printers/DNP_10x15 get-printer-attributes.test | grep -iE "printer-state|marker"
```

- [ ] **Step 2 : Compléter `docs/DEPLOYMENT.md`**

Nouvelle étape d'installation : lancer `sudo ./deploy/configurer_cups.sh` une
fois par machine, en expliquant qu'elle est indépendante de `install.sh` (qui
ne concerne que les cibles systemd) et qu'elle exige l'appartenance à `lpadmin`.

- [ ] **Step 3 : Mettre à jour `docs/ARCHITECTURE.md`**

Documente que `core/printer.py` raisonne désormais par **imprimante physique**
(les deux files DNP partagent une DS620) et que `pycups` est une dépendance
optionnelle de plus, au même titre que `gphoto2` et `pyserial`.

- [ ] **Step 4 : Ajouter l'entrée `docs/CHANGELOG.md`**

Résume : diagnostic IPP de la cause réelle, affichage de cette cause à l'écran,
réarmement par la touche RÉESSAYER, alerte de fin de rouleau, politique CUPS
`retry-job`.

- [ ] **Step 5 : Vérification finale complète**

```bash
pytest --cov --cov-report=term-missing && ruff check .
```

Expected: tous les tests passent, couverture ≥ 75 %, `All checks passed!`.
`core/printer.py` doit monter en couverture — c'est du code pur, vise ≥ 87 %
comme demandé par `CLAUDE.md` pour le nouveau code.

- [ ] **Step 6 : Commit**

```bash
git add docs/
git commit -m "docs: fiabilisation de l'impression DNP (runbook, deploiement, changelog)"
```

---

## Validation sur la machine cible

Les tests CI ne peuvent pas couvrir le matériel. À faire sur le mini-PC avant
le prochain événement, dans cet ordre :

- [ ] Lancer `sudo ./deploy/configurer_cups.sh`, vérifier qu'il sort en succès.
- [ ] Vérifier la politique : `lpstat -l -p DNP_10x15 | grep -i policy` doit
      montrer `retry-job`.
- [ ] **Test à blanc du réarmement** : `sudo cupsdisable DNP_10x15`, lancer une
      impression depuis le kiosque, vérifier que l'écran affiche
      « FILE D'IMPRESSION ARRÊTÉE », appuyer sur RÉESSAYER, vérifier que le
      tirage sort.
- [ ] **Test panne de papier** : retirer le rouleau, lancer une impression,
      vérifier le message « PAPIER ÉPUISÉ — recharger le bac », recharger,
      appuyer sur RÉESSAYER.
- [ ] **Vérifier l'hypothèse `marker-levels`** : noter le nombre de tirages
      affiché avant et après un changement de rouleau, sans imprimer entre les
      deux. Si le compteur ne remonte pas seul, l'alerte de fin de rouleau
      restera bloquée à sa dernière valeur jusqu'au premier tirage — à noter
      dans le runbook, sans conséquence sur le réarmement.
- [ ] **Caler `DELAI_REAMORCAGE_S`** : chronométrer le temps réel entre le
      rallumage de la DS620 et sa disponibilité. Ajuster les 30 s par défaut.
- [ ] **Vérifier l'accumulation** : laisser deux sessions tenter d'imprimer
      sans papier, confirmer qu'au plus un ou deux jobs s'accumulent grâce au
      garde-fou « tirage en attente ».
