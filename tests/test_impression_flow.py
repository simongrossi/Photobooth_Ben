"""Régressions du flux impression fiable et récupérable."""
from __future__ import annotations

from types import SimpleNamespace

import Photobooth_start as app
from core.session import Etat, SessionState


def _session_avec_montage(tmp_path, impressions_restantes=1):
    montage = tmp_path / "montage.jpg"
    montage.write_bytes(b"jpeg factice")
    return SessionState(
        etat=Etat.FIN,
        mode_actuel="10x15",
        photos_validees=["photo.jpg"],
        id_session_timestamp="session-test",
        chemin_impression=str(montage),
        impressions_restantes=impressions_restantes,
    )


def _isoler_runtime_impression(monkeypatch):
    sons = []
    messages = []
    tirages = []
    monkeypatch.setattr(app, "ACTIVER_IMPRESSION", True)
    monkeypatch.setattr(app, "ACTIVER_IMPRESSIONS_MULTIPLES", False)
    monkeypatch.setattr(app, "ecrire_performance", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "ecran_attente_impression", lambda tache: tache.join(timeout=2))
    monkeypatch.setattr(app, "jouer_son", sons.append)
    monkeypatch.setattr(
        app,
        "afficher_message_plein_ecran",
        lambda message, **kwargs: messages.append(message),
    )
    monkeypatch.setattr(app.quota_mgr, "enregistrer_tirage", tirages.append)
    monkeypatch.setattr(app.time, "sleep", lambda _duree: None)
    monkeypatch.setattr(app.printer_mgr, "is_ready", lambda _mode: True)
    monkeypatch.setattr(app, "dernier_tirage_reussi_ts", None)
    monkeypatch.setattr(app, "dernier_tirage_reussi_mode", None)
    return sons, messages, tirages


def test_succes_attend_le_worker_avant_declarer_printed(tmp_path, monkeypatch):
    session = _session_avec_montage(tmp_path)
    sons, messages, tirages = _isoler_runtime_impression(monkeypatch)
    appels = []

    def envoyer(chemin, mode, verifier=False):
        appels.append((chemin, mode, verifier))
        return True

    monkeypatch.setattr(app.printer_mgr, "send", envoyer)

    assert app.traiter_impression_session(session) == "printed"
    assert len(appels) == 1
    assert tirages == [1]
    assert sons == ["success"]
    assert messages == [app.config.TXT_IMPRESSION_ENVOYEE]
    assert session.impressions_restantes == 0
    assert session.erreur_impression is False
    assert session.impression_en_cours is False
    assert app.dernier_tirage_reussi_ts is not None
    assert app.dernier_tirage_reussi_mode == "10x15"


def test_echec_partiel_ne_rejoue_que_les_feuilles_restantes(tmp_path, monkeypatch):
    session = _session_avec_montage(tmp_path, impressions_restantes=2)
    sons, messages, tirages = _isoler_runtime_impression(monkeypatch)
    resultats = iter((True, False))
    appels = []

    def envoyer_echec(chemin, mode, verifier=False):
        appels.append(chemin)
        ok = next(resultats)
        if not ok:
            app.printer_mgr.last_error = "DNP débranchée"
        return ok

    monkeypatch.setattr(app.printer_mgr, "send", envoyer_echec)

    assert app.traiter_impression_session(session) == "print_failed"
    assert session.erreur_impression is True
    assert session.message_erreur_impression == "DNP débranchée"
    assert session.impressions_restantes == 1
    assert tirages == [1]
    assert sons == []
    assert messages == []

    monkeypatch.setattr(
        app.printer_mgr,
        "send",
        lambda chemin, mode, verifier=False: appels.append(chemin) or True,
    )
    assert app.traiter_impression_session(session) == "printed"
    assert len(appels) == 3  # deux au premier essai, une seule au retry
    assert tirages == [1, 1]
    assert sons == ["success"]
    assert session.impressions_restantes == 0
    assert session.erreur_impression is False


def test_echec_depuis_fin_conserve_la_session(tmp_path, monkeypatch):
    session = _session_avec_montage(tmp_path)
    terminaisons = []
    monkeypatch.setattr(app, "_journaliser_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_verifier_quota_ou_debloquer", lambda _session: True)

    def echouer(session_courante):
        session_courante.erreur_impression = True
        session_courante.message_erreur_impression = "hors ligne"
        return "print_failed"

    monkeypatch.setattr(app, "traiter_impression_session", echouer)
    monkeypatch.setattr(
        app,
        "terminer_session_et_revenir_accueil",
        terminaisons.append,
    )
    monkeypatch.setattr(app, "pygame", SimpleNamespace(event=SimpleNamespace(clear=lambda: None)))

    app.handle_fin_event(
        SimpleNamespace(key=app.TOUCHE_MILIEU),
        session,
        maintenant=10.0,
        ecoule=10.0,
    )

    assert terminaisons == []
    assert session.etat is Etat.FIN
    assert session.mode_actuel == "10x15"
    assert session.erreur_impression is True


def test_actions_apres_echec_terminer_reessayer_et_aide(tmp_path, monkeypatch):
    session = _session_avec_montage(tmp_path)
    session.erreur_impression = True
    terminaisons = []
    messages = []
    actions = []
    monkeypatch.setattr(
        app,
        "_journaliser_action",
        lambda action, **details: actions.append(action),
    )
    monkeypatch.setattr(
        app,
        "terminer_session_et_revenir_accueil",
        terminaisons.append,
    )
    monkeypatch.setattr(
        app,
        "afficher_message_plein_ecran",
        lambda message, **kwargs: messages.append(message),
    )
    monkeypatch.setattr(app.time, "sleep", lambda _duree: None)

    app._handle_erreur_impression(
        SimpleNamespace(key=app.TOUCHE_DROITE), session, maintenant=10.0
    )
    assert messages == [app.config.TXT_IMPRESSION_AIDE_MESSAGE]
    assert session.erreur_impression is True

    app._handle_erreur_impression(
        SimpleNamespace(key=app.TOUCHE_GAUCHE), session, maintenant=11.0
    )
    assert terminaisons == ["print_failed"]
    assert actions == ["print_help_requested", "finish_without_print"]


def test_reessayer_reamorce_si_file_desactivee(tmp_path, monkeypatch):
    """Le cas de l'incident : la file est désactivée. RÉESSAYER doit la purger
    et la réactiver AVANT de relancer, sinon le job en échec repart et
    replante l'imprimante."""
    from core.printer import EtatImprimante

    session = _session_avec_montage(tmp_path)
    session.erreur_impression = True
    appels = []

    monkeypatch.setattr(app, "_journaliser_action", lambda action, **d: None)
    monkeypatch.setattr(app, "_verifier_quota_ou_debloquer", lambda _s: True)
    monkeypatch.setattr(
        app, "pygame", SimpleNamespace(event=SimpleNamespace(clear=lambda: None))
    )
    monkeypatch.setattr(app, "terminer_session_et_revenir_accueil", lambda _issue: None)
    monkeypatch.setattr(
        app.printer_mgr, "diagnostic",
        lambda _mode: EtatImprimante(
            pret=False, raison="media-empty-error",
            message="PAPIER ÉPUISÉ — recharger le bac", file_desactivee=True,
        ),
    )
    monkeypatch.setattr(
        app.printer_mgr, "reamorcer",
        lambda _mode, *a, **kw: appels.append("reamorcer") or EtatImprimante(pret=True),
    )
    monkeypatch.setattr(app, "executer_avec_spinner", lambda fonction, _msg: fonction())
    monkeypatch.setattr(
        app, "traiter_impression_session",
        lambda _s: appels.append("impression") or "printed",
    )

    app._handle_erreur_impression(
        SimpleNamespace(key=app.TOUCHE_MILIEU), session, maintenant=12.0
    )

    assert appels == ["reamorcer", "impression"]


def test_reessayer_ne_reamorce_pas_si_file_saine(tmp_path, monkeypatch):
    """Pas de purge gratuite quand la file va bien : on perdrait un job en cours."""
    from core.printer import EtatImprimante

    session = _session_avec_montage(tmp_path)
    session.erreur_impression = True
    appels = []

    monkeypatch.setattr(app, "_journaliser_action", lambda action, **d: None)
    monkeypatch.setattr(app, "_verifier_quota_ou_debloquer", lambda _s: True)
    monkeypatch.setattr(
        app, "pygame", SimpleNamespace(event=SimpleNamespace(clear=lambda: None))
    )
    monkeypatch.setattr(app, "terminer_session_et_revenir_accueil", lambda _issue: None)
    monkeypatch.setattr(app.printer_mgr, "diagnostic",
                        lambda _mode: EtatImprimante(pret=True))
    monkeypatch.setattr(app.printer_mgr, "reamorcer",
                        lambda _mode, *a, **kw: appels.append("reamorcer"))
    monkeypatch.setattr(
        app, "traiter_impression_session",
        lambda _s: appels.append("impression") or "printed",
    )

    app._handle_erreur_impression(
        SimpleNamespace(key=app.TOUCHE_MILIEU), session, maintenant=12.0
    )

    assert appels == ["impression"]
