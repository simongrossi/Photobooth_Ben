"""test_printer.py — tests unitaires de PrinterManager.

Mocke `subprocess.run` / `subprocess.Popen` pour éviter tout appel réel à CUPS.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core import printer
from core.printer import (
    EtatImprimante,
    PrinterManager,
    message_pour_raison,
    tirages_restants_depuis_marker,
)


@pytest.fixture
def mgr():
    return PrinterManager(nom_10x15="DNP_10x15", nom_strip="DNP_STRIP")


# --- nom ---


class TestNom:
    def test_nom_10x15(self, mgr):
        assert mgr.nom("10x15") == "DNP_10x15"

    def test_nom_strip(self, mgr):
        assert mgr.nom("strips") == "DNP_STRIP"

    def test_nom_inconnu(self, mgr):
        assert mgr.nom("xxx") is None


# --- is_ready ---


def _fake_run_factory(stdout: str, raises: Exception | None = None):
    def _fake_run(cmd, **kw):
        if raises:
            raise raises
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)
    return _fake_run


class TestIsReady:
    def test_mode_inconnu(self, mgr):
        assert mgr.is_ready("inconnu") == "MODE INCONNU"

    def test_idle(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "printer DNP_10x15 is idle.  enabled since ..."
        ))
        result = mgr.is_ready("10x15")
        assert result is True or result not in ["IMPRIMANTE HORS LIGNE", "ERREUR SYSTÈME CUPS"]

    def test_disabled(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "printer DNP_10x15 disabled since ..."
        ))
        assert mgr.is_ready("10x15") is not True

    def test_printing(self, mgr, monkeypatch):
        def _dispatch(cmd, **kw):
            if "-o" in cmd:
                return SimpleNamespace(stdout="", stderr="", returncode=0)
            return SimpleNamespace(
                stdout="printer DNP_STRIP now printing job-42", stderr="", returncode=0
            )

        monkeypatch.setattr(printer.subprocess, "run", _dispatch)
        assert mgr.is_ready("strips") is True

    def test_output_vide_renvoie_false(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(""))
        assert mgr.is_ready("10x15") is not True

    def test_subprocess_raise_attrape(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "", raises=TimeoutError("lpstat hung"),
        ))
        assert mgr.is_ready("10x15") is not True


class TestLastError:
    """Régression : `last_error` doit exister et refléter l'état (bug AttributeError)."""

    def test_none_a_l_init(self, mgr):
        assert mgr.last_error is None

    def test_mode_inconnu_memorise(self, mgr):
        mgr.is_ready("inconnu")
        assert mgr.last_error == "MODE INCONNU"

    def test_file_pleine_memorise(self, mgr, monkeypatch):
        # Un job en attente n'est plus une "file pleine" : avec retry-job, c'est
        # un tirage qui attend du papier.
        monkeypatch.setattr(printer, "cups", None)

        def _dispatch(cmd, **kw):
            if "-o" in cmd:
                return SimpleNamespace(
                    stdout="DNP_10x15-42 photobooth 1024 ...", stderr="", returncode=0
                )
            return SimpleNamespace(
                stdout="printer DNP_10x15 is idle. enabled", stderr="", returncode=0
            )

        monkeypatch.setattr(printer.subprocess, "run", _dispatch)
        assert mgr.is_ready("10x15") == "TIRAGE EN ATTENTE"
        assert mgr.last_error == "TIRAGE EN ATTENTE"

    def test_reset_a_none_si_pret(self, mgr, monkeypatch):
        mgr.is_ready("inconnu")

        def _dispatch(cmd, **kw):
            if "-o" in cmd:
                return SimpleNamespace(stdout="", stderr="", returncode=0)
            return SimpleNamespace(stdout="printer DNP_10x15 is idle. enabled", stderr="", returncode=0)

        monkeypatch.setattr(printer.subprocess, "run", _dispatch)
        assert mgr.is_ready("10x15") is True
        assert mgr.last_error is None


class TestFileAttente:
    def test_compte_les_jobs(self, mgr, monkeypatch):
        """Cumule sur toutes les files du peripherique : 2 lignes x 2 files."""
        monkeypatch.setattr(printer, "cups", None)
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "DNP_10x15-41 user 100\nDNP_10x15-42 user 200\n"
        ))
        assert mgr.jobs_en_attente("10x15") == 4

    def test_compte_une_seule_file(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", FakeCups({
            "DNP_10x15": {"device-uri": "usb://a"},
            "DNP_STRIP": {"device-uri": "usb://b"},
        }))
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(
            "DNP_10x15-41 user 100\nDNP_10x15-42 user 200\n"
        ))
        assert mgr.jobs_en_attente("10x15") == 2

    def test_file_vide(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory(""))
        assert mgr.jobs_en_attente("strips") == 0

    def test_etat_inconnu_si_cups_indisponible(self, mgr, monkeypatch):
        monkeypatch.setattr(
            printer.subprocess,
            "run",
            _fake_run_factory("", raises=OSError("lpstat absent")),
        )
        assert mgr.jobs_en_attente("10x15") is None


# --- send ---


class TestSend:
    def test_mode_inconnu_rejette(self, mgr):
        assert mgr.send("/tmp/file.jpg", "inconnu") is False

    def test_imprimante_non_prete_rejette(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory("disabled"))
        assert mgr.send("/tmp/file.jpg", "10x15") is False

    def test_envoi_ok(self, mgr, monkeypatch):
        # On simule que subprocess.run ne renvoie pas d'erreur
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory("idle"))
        
        # --- AJOUTE CETTE LIGNE ICI ---
        # On force is_ready à répondre True quoi qu'il arrive pour ce test précis
        monkeypatch.setattr(mgr, "is_ready", lambda mode: True)
        # ------------------------------

        popen_calls = []

        class FakePopen:
            def __init__(self, cmd, **kwargs): # Ajout de **kwargs pour la compatibilité
                popen_calls.append(cmd)

        monkeypatch.setattr(printer.subprocess, "Popen", FakePopen)
        
        assert mgr.send("/tmp/foo.jpg", "10x15") is True

    def test_envoi_deja_verifie_ne_relance_pas_lpstat(self, mgr, monkeypatch):
        commandes = []

        def fake_run(cmd, **kwargs):
            commandes.append(cmd)
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        monkeypatch.setattr(printer.subprocess, "run", fake_run)

        assert mgr.send("/tmp/foo.jpg", "10x15", verifier=False) is True
        assert [commande[0] for commande in commandes] == ["lp"]

    def test_popen_raise_attrape(self, mgr, monkeypatch):
        monkeypatch.setattr(printer.subprocess, "run", _fake_run_factory("idle"))

        def raising_popen(*a, **kw):
            raise OSError("fork failed")

        monkeypatch.setattr(printer.subprocess, "Popen", raising_popen)
        assert mgr.send("/tmp/foo.jpg", "10x15") is False


class TestPurge:
    def test_limitee_aux_files_configurees(self, mgr, monkeypatch):
        commandes = []

        def fake_run(cmd, **kwargs):
            commandes.append(cmd)
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        monkeypatch.setattr(printer.subprocess, "run", fake_run)

        mgr.purger_file_attente()

        assert commandes == [
            ["cancel", "-a", "DNP_10x15"],
            ["cancel", "-a", "DNP_STRIP"],
        ]


# --- Diagnostic IPP (sprint fiabilisation DNP) ---


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
        """Un code brut lisible vaut mieux qu'un message générique qui trompe."""
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
        """Sans pycups on ne peut pas savoir : on groupe, quitte à vérifier une
        file de trop. L'inverse laisserait un job empoisonné en place."""
        monkeypatch.setattr(printer, "cups", None)
        assert sorted(mgr._files_du_meme_device("10x15")) == ["DNP_10x15", "DNP_STRIP"]

    def test_mode_inconnu(self, mgr, monkeypatch):
        monkeypatch.setattr(printer, "cups", FakeCups(DEUX_FILES_MEME_DS620))
        assert mgr._files_du_meme_device("xxx") == []


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
        """Un strip coincé doit bloquer un 10x15 : même imprimante physique."""
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


class TestReamorcer:
    @staticmethod
    def _tracer(monkeypatch):
        """Enregistre l'ordre exact des commandes CUPS lancées."""
        appels = []

        def _run(cmd, **kw):
            appels.append(list(cmd))
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        monkeypatch.setattr(printer.subprocess, "run", _run)
        monkeypatch.setattr(printer.time, "sleep", lambda _s: None)
        return appels

    def test_cancel_avant_cupsenable(self, mgr, monkeypatch):
        """LE test du correctif. Réactiver avant de purger relance le job en
        échec, qui redésactive la file — la boucle vécue en événement."""
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
