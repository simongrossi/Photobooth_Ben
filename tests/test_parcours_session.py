"""test_parcours_session.py — identité de session et confirmation d'abandon.

`Photobooth_start` s'importe sans pygame (les imports matériels sont en
try/except), et les codes de touches sont de simples entiers : les handlers
d'événements sont donc testables en CI, sans écran ni caméra.

Deux invariants du parcours invité :

- **Une session = un identifiant.** Une reprise ne doit jamais ouvrir une
  seconde session : sinon les statistiques comptent deux passages là où un seul
  invité s'est présenté, et les fichiers d'une même session portent deux
  horodatages différents.
- **Un abandon se confirme.** Le bouton d'abandon jouxte celui de validation ;
  un appui unique ne doit pas détruire des photos sans recours.
"""
from __future__ import annotations

import inspect
import time
from types import SimpleNamespace

import pytest

import Photobooth_start as pb
from core.session import (
    Etat,
    SessionState,
    avertissement_liberation,
    secondes_avant_liberation,
    session_a_liberer,
)

GAUCHE = pb.TOUCHE_GAUCHE
DROITE = pb.TOUCHE_DROITE
MILIEU = pb.TOUCHE_MILIEU


def touche(code: int) -> SimpleNamespace:
    """Événement pygame minimal : les handlers ne lisent que `.key`."""
    return SimpleNamespace(key=code)


@pytest.fixture
def session() -> SessionState:
    s = SessionState()
    s.mode_actuel = "strips"
    s.etat = Etat.VALIDATION
    s.id_session_timestamp = "2026-07-19_14h30_00"
    s.photos_validees = ["p1.jpg"]
    return s


@pytest.fixture
def sans_effets(monkeypatch):
    """Neutralise ce qui sort du process (journalisation, fin de session).

    Fournit aussi un pygame minimal : les handlers appellent `event.clear()`
    pour purger la file, et le module est absent en CI.
    """
    appels = {"termine": [], "actions": []}
    monkeypatch.setattr(pb, "_journaliser_action",
                        lambda action, **kw: appels["actions"].append(action))
    monkeypatch.setattr(pb, "terminer_session_et_revenir_accueil",
                        lambda issue: appels["termine"].append(issue))
    if pb.pygame is None:
        monkeypatch.setattr(
            pb, "pygame",
            SimpleNamespace(event=SimpleNamespace(clear=lambda: None)),
        )
    return appels


# ========================================================================================
# --- Confirmation d'abandon en mode bandelettes ---
# ========================================================================================

class TestAbandonStripDoubleConfirmation:
    """Le strip abandonnait au premier appui, contrairement au 10x15 et à FIN.

    C'est le mode où l'invité a le plus à perdre : jusqu'à trois photos déjà
    prises, effacées par une pression sur le bouton voisin de « valider ».
    """

    def test_premier_appui_narme_que_la_fenetre(self, session, sans_effets):
        pb._handle_validation_strips(touche(DROITE), session, time.time())
        assert sans_effets["termine"] == [], "la session ne doit pas être terminée au 1er appui"
        assert session.abandon_confirm_until > time.time()
        assert "abandon_requested" in sans_effets["actions"]

    def test_second_appui_confirme(self, session, sans_effets):
        maintenant = time.time()
        pb._handle_validation_strips(touche(DROITE), session, maintenant)
        pb._handle_validation_strips(touche(DROITE), session, maintenant)
        assert sans_effets["termine"] == ["abandoned"]
        assert "abandon_confirmed" in sans_effets["actions"]

    def test_fenetre_expiree_rearme_au_lieu_dabandonner(self, session, sans_effets):
        """Hésiter puis réappuyer plus tard ne doit pas abandonner d'un coup."""
        session.abandon_confirm_until = time.time() - 0.01  # fenêtre échue
        pb._handle_validation_strips(touche(DROITE), session, time.time())
        assert sans_effets["termine"] == []
        assert session.abandon_confirm_until > time.time()

    def test_duree_de_la_fenetre_configurable(self, session, sans_effets):
        avant = time.time()
        pb._handle_validation_strips(touche(DROITE), session, avant)
        attendu = avant + pb.DUREE_CONFIRM_ABANDON
        assert session.abandon_confirm_until == pytest.approx(attendu, abs=0.5)

    def test_les_autres_boutons_restent_immediats(self, session, sans_effets):
        """Seul l'abandon demande confirmation ; reprendre et valider non."""
        pb._handle_validation_strips(touche(GAUCHE), session, time.time())
        assert session.etat is Etat.DECOMPTE
        assert session.photos_validees == [], "reprendre dépile la dernière photo"


class TestParitéAvecLesAutresEcrans:
    """Les trois écrans qui proposent l'abandon doivent se comporter pareil."""

    def _premier_appui(self, handler, session, sans_effets, avec_ecoule):
        session.abandon_confirm_until = 0.0
        maintenant = time.time()
        if avec_ecoule:
            handler(touche(DROITE), session, maintenant, 999.0)
        else:
            handler(touche(DROITE), session, maintenant)
        return sans_effets["termine"], session.abandon_confirm_until

    def test_validation_strip_arme_sans_terminer(self, session, sans_effets):
        termine, fenetre = self._premier_appui(
            pb._handle_validation_strips, session, sans_effets, avec_ecoule=False)
        assert termine == [] and fenetre > time.time()

    def test_validation_10x15_arme_sans_terminer(self, session, sans_effets):
        session.mode_actuel = "10x15"
        termine, fenetre = self._premier_appui(
            pb._handle_validation_10x15, session, sans_effets, avec_ecoule=False)
        assert termine == [] and fenetre > time.time()

    def test_fin_arme_sans_terminer(self, session, sans_effets):
        session.etat = Etat.FIN
        termine, fenetre = self._premier_appui(
            pb.handle_fin_event, session, sans_effets, avec_ecoule=True)
        assert termine == [] and fenetre > time.time()


# ========================================================================================
# --- Identité de session à travers les reprises ---
# ========================================================================================

class TestIdentifiantDeSession:
    """L'identifiant était (ré)généré quand `photos_validees` était vide.

    Or une reprise vide cette liste sans terminer la session : chaque reprise
    ouvrait donc une seconde session, avec un second `session_start` et un
    second horodatage pour un seul et même invité.
    """

    def test_condition_basee_sur_lidentifiant_pas_sur_les_photos(self):
        """Garde de non-régression sur la condition elle-même.

        Le corps de `render_decompte` n'est pas exécutable sans pygame ; on
        vérifie donc la condition dans le source, avec un message qui explique
        quoi ne pas réintroduire.
        """
        import inspect
        source = inspect.getsource(pb.render_decompte)
        assert "if not session.id_session_timestamp:" in source, (
            "l'identifiant de session doit dépendre de son absence, pas de "
            "`len(photos_validees) == 0` : une reprise vide la liste sans "
            "terminer la session et ouvrirait un second session_start"
        )
        assert "if len(session.photos_validees) == 0:" not in source

    def test_reprise_10x15_conserve_lidentifiant(self, session, sans_effets, monkeypatch):
        """« Reprendre » vide les photos : l'identifiant doit survivre."""
        # L'archivage part en tâche de fond : on le neutralise pour garder le
        # test hermétique (sinon un vrai thread tente un montage PIL).
        monkeypatch.setattr(pb, "archiver_en_arriere_plan", lambda *a, **k: None)
        session.mode_actuel = "10x15"
        avant = session.id_session_timestamp

        pb._handle_validation_10x15(touche(GAUCHE), session, time.time())

        assert session.photos_validees == []
        assert session.etat is Etat.DECOMPTE
        assert session.id_session_timestamp == avant, (
            "la reprise ne doit pas repartir sur une nouvelle session"
        )

    def test_recommencer_depuis_fin_conserve_lidentifiant(self, session, sans_effets, monkeypatch):
        monkeypatch.setattr(pb, "archiver_en_arriere_plan", lambda *a, **k: None)
        session.etat = Etat.FIN
        avant = session.id_session_timestamp

        pb.handle_fin_event(touche(GAUCHE), session, time.time(), 999.0)

        assert session.photos_validees == []
        assert session.id_session_timestamp == avant

    def test_reprise_strip_conserve_lidentifiant(self, session, sans_effets):
        session.photos_validees = ["p1.jpg"]
        avant = session.id_session_timestamp
        pb._handle_validation_strips(touche(GAUCHE), session, time.time())
        assert session.photos_validees == []
        assert session.id_session_timestamp == avant

    def test_fin_de_session_libere_lidentifiant(self):
        """Sur ce nouveau critère, `reset_pour_accueil` devient le seul point
        qui autorise une nouvelle session — il doit bien vider l'identifiant."""
        s = SessionState()
        s.id_session_timestamp = "2026-07-19_14h30_00"
        s.reset_pour_accueil()
        assert s.id_session_timestamp == ""


# ========================================================================================
# --- Message affiché pendant l'archivage ---
# ========================================================================================

class TestErreurCaptureRecuperable:
    """Un raté ponctuel de l'appareil renvoyait l'invité à l'accueil après 4 s
    d'écran rouge, sans explication ni recours : il devait tout reprendre depuis
    le choix du format. La session reste maintenant ouverte."""

    def _session_en_echec(self):
        s = SessionState()
        s.mode_actuel = "10x15"
        s.etat = Etat.VALIDATION
        s.id_session_timestamp = "2026-07-19_14h30_00"
        s.erreur_capture = True
        return s

    def test_la_capture_ratee_ne_termine_plus_la_session(self):
        """Garde sur `render_decompte`, non exécutable sans pygame."""
        source = inspect.getsource(pb.render_decompte)
        assert "session.erreur_capture = True" in source, (
            "un échec de capture doit ouvrir un état récupérable"
        )
        assert 'terminer_session_et_revenir_accueil("capture_failed")' not in source, (
            "la session ne doit plus être terminée d'office : l'invité choisit"
        )
        assert "ecran_erreur(" not in source, (
            "l'écran bloquant de 4 s est remplacé par un état actionnable"
        )

    def test_reessayer_relance_le_decompte(self, sans_effets):
        s = self._session_en_echec()
        pb._handle_erreur_capture(touche(MILIEU), s, time.time())
        assert s.etat is Etat.DECOMPTE
        assert s.erreur_capture is False
        assert sans_effets["termine"] == [], "réessayer ne termine pas la session"

    def test_reessayer_conserve_lidentifiant(self, sans_effets):
        """Sinon un simple raté matériel compterait comme deux passages."""
        s = self._session_en_echec()
        avant = s.id_session_timestamp
        pb._handle_erreur_capture(touche(MILIEU), s, time.time())
        assert s.id_session_timestamp == avant

    @pytest.mark.parametrize("bouton", ["GAUCHE", "DROITE"])
    def test_les_deux_autres_boutons_rentrent(self, sans_effets, bouton):
        s = self._session_en_echec()
        pb._handle_erreur_capture(touche(GAUCHE if bouton == "GAUCHE" else DROITE),
                                  s, time.time())
        assert sans_effets["termine"] == ["capture_failed"]

    def test_le_dispatcher_donne_la_priorite_a_lerreur(self, sans_effets):
        """Il n'y a pas de photo à valider : le parcours normal n'a aucun sens."""
        s = self._session_en_echec()
        pb.handle_validation_event(touche(MILIEU), s, time.time(), 999.0)
        assert s.etat is Etat.DECOMPTE, "doit passer par _handle_erreur_capture"

    def test_letat_est_remis_a_zero_en_fin_de_session(self):
        s = self._session_en_echec()
        s.reset_pour_accueil()
        assert s.erreur_capture is False


class TestLiberationSessionInactive:
    """Un invité qui s'en va bloquait la borne indéfiniment sur son écran : le
    suivant voyait sa photo et ne pouvait rien lancer. C'est aussi un problème
    de vie privée, le portrait restant affiché sans limite."""

    def _session(self, etat=Etat.VALIDATION, activite=1000.0):
        s = SessionState()
        s.etat = etat
        s.last_activity_ts = activite
        return s

    def test_pas_de_liberation_avant_le_delai(self):
        s = self._session()
        assert not session_a_liberer(s, maintenant=1000.0 + 10, delai=90.0)

    def test_liberation_apres_le_delai(self):
        s = self._session()
        assert session_a_liberer(s, maintenant=1000.0 + 91, delai=90.0)

    def test_liberation_pile_au_delai(self):
        s = self._session()
        assert session_a_liberer(s, maintenant=1000.0 + 90, delai=90.0)

    @pytest.mark.parametrize("etat", [Etat.ACCUEIL, Etat.DECOMPTE])
    def test_etats_non_liberables(self, etat):
        """L'accueil n'a rien à libérer, et le décompte se termine tout seul —
        interrompre une capture en cours serait absurde."""
        s = self._session(etat=etat)
        assert not session_a_liberer(s, maintenant=1000.0 + 9999, delai=90.0)

    @pytest.mark.parametrize("etat", [Etat.VALIDATION, Etat.FIN])
    def test_etats_liberables(self, etat):
        s = self._session(etat=etat)
        assert session_a_liberer(s, maintenant=1000.0 + 91, delai=90.0)

    def test_delai_nul_desactive_la_liberation(self):
        """Doit rester débrayable : une borne surveillée n'en a pas besoin."""
        s = self._session()
        assert not session_a_liberer(s, maintenant=1000.0 + 99999, delai=0.0)
        assert secondes_avant_liberation(s, maintenant=1000.0, delai=0.0) is None

    def test_activite_jamais_horodatee(self):
        """`last_activity_ts` à 0 = on ne sait pas, donc on ne libère pas."""
        s = self._session(activite=0.0)
        assert not session_a_liberer(s, maintenant=99999.0, delai=90.0)

    def test_activite_repousse_lecheance(self):
        s = self._session()
        assert session_a_liberer(s, maintenant=1000.0 + 91, delai=90.0)
        s.last_activity_ts = 1000.0 + 91          # l'invité appuie sur un bouton
        assert not session_a_liberer(s, maintenant=1000.0 + 92, delai=90.0)


class TestAvertissementAvantLiberation:
    """Sans compte à rebours, l'écran se viderait sans explication au milieu de
    ce que l'invité regarde."""

    def _session(self):
        s = SessionState()
        s.etat = Etat.VALIDATION
        s.last_activity_ts = 1000.0
        return s

    def test_rien_a_afficher_au_debut(self):
        """Prévenir trop tôt met une pression inutile sur quelqu'un qui
        regarde simplement sa photo."""
        s = self._session()
        assert avertissement_liberation(s, maintenant=1000.0 + 10, delai=90.0, fenetre=15.0) is None

    def test_affiche_dans_la_fenetre(self):
        s = self._session()
        restant = avertissement_liberation(s, maintenant=1000.0 + 80, delai=90.0, fenetre=15.0)
        assert restant == 10

    def test_jamais_zero_ni_negatif(self):
        """Afficher « dans 0 s » pendant une frame serait disgracieux."""
        s = self._session()
        restant = avertissement_liberation(s, maintenant=1000.0 + 89.6, delai=90.0, fenetre=15.0)
        assert restant is not None and restant >= 1

    def test_rien_apres_expiration(self):
        s = self._session()
        assert avertissement_liberation(s, maintenant=1000.0 + 95, delai=90.0, fenetre=15.0) is None

    def test_rien_si_etat_non_liberable(self):
        s = self._session()
        s.etat = Etat.ACCUEIL
        assert avertissement_liberation(s, maintenant=1000.0 + 85, delai=90.0, fenetre=15.0) is None


class TestBranchementBoucleePrincipale:
    """La boucle principale n'est pas exécutable sans pygame : on vérifie que le
    branchement existe et qu'il journalise une issue distincte."""

    def test_boucle_interroge_la_fonction_pure(self):
        import inspect
        source = inspect.getsource(pb.main)
        assert "session_a_liberer(session)" in source, (
            "la boucle principale doit interroger core.session pour libérer une "
            "session inactive"
        )
        assert '"idle_timeout"' in source

    def test_issue_distincte_des_abandons(self):
        """Un départ n'est pas un abandon volontaire : les stats doivent les
        distinguer, sinon un écran incompréhensible passe pour du désintérêt."""
        import stats
        source = inspect.getsource(stats.calculer_stats)
        assert "idle_timeout" in source

    def test_avertissement_dessine_sur_les_deux_ecrans(self):
        import inspect
        for fonction in (pb.render_validation, pb.render_fin):
            source = inspect.getsource(fonction)
            assert "_dessiner_avertissement_idle" in source, fonction.__name__


class TestArchivageEnArrierePlan:
    """Reprendre une photo imposait d'attendre la fabrication complète d'un
    montage en qualité d'impression — filigrane, grain et sauvegarde comprises —
    que l'invité ne verrait jamais. Les dossiers d'archive restent alimentés
    (la galerie admin les expose), mais hors du chemin critique."""

    def test_aucun_spinner_sur_les_chemins_darchivage(self):
        """Plus aucune attente à annoncer : la constante dédiée a disparu."""
        import config
        assert not hasattr(config, "TXT_ARCHIVAGE_EN_COURS"), (
            "constante morte : plus aucun écran d'archivage n'est affiché"
        )

    def test_entrees_recopiees_avant_le_thread(self, monkeypatch, tmp_path):
        """L'appelant vide `photos_validees` juste après : sans copie, le thread
        travaillerait sur une liste vidée sous ses pieds.

        Le générateur est bloqué jusqu'à ce que la liste d'origine soit vidée :
        sans ce verrou le test passerait par simple chance, le thread ayant fini
        avant l'appelant.
        """
        import threading
        vidage_fait = threading.Event()
        vues = {}

        class FauxGenerateur:
            @staticmethod
            def final(photos, id_session):
                assert vidage_fait.wait(timeout=5), "l'appelant n'a pas vidé la liste"
                vues["photos"] = list(photos)
                chemin = tmp_path / "montage.jpg"
                chemin.write_bytes(b"x")
                return str(chemin)

        monkeypatch.setattr(pb, "MontageGenerator10x15", FauxGenerateur)
        photos = ["a.jpg", "b.jpg"]
        fil = pb.archiver_en_arriere_plan(
            "10x15", photos, "2026-07-19_23h00_00", str(tmp_path / "arch"), "retake",
        )
        photos.clear()          # ce que fait l'appelant immédiatement après
        vidage_fait.set()
        fil.join(timeout=5)
        assert vues["photos"] == ["a.jpg", "b.jpg"]

    def test_archive_deposee_dans_le_bon_dossier(self, monkeypatch, tmp_path):
        class FauxGenerateur:
            @staticmethod
            def final(photos, id_session):
                chemin = tmp_path / "montage.jpg"
                chemin.write_bytes(b"x")
                return str(chemin)

        monkeypatch.setattr(pb, "MontageGenerator10x15", FauxGenerateur)
        dossier = tmp_path / "arch"
        fil = pb.archiver_en_arriere_plan(
            "10x15", ["a.jpg"], "2026-07-19_23h00_00", str(dossier), "retake",
        )
        fil.join(timeout=5)
        assert (dossier / "retake_2026-07-19_23h00_00.jpg").exists()

    def test_echec_darchivage_silencieux(self, monkeypatch, tmp_path):
        """L'invité a déjà repris la main : une archive ratée ne doit jamais
        remonter jusqu'à lui."""
        class GenerateurQuiPlante:
            @staticmethod
            def final(photos, id_session):
                raise OSError("disque plein")

        monkeypatch.setattr(pb, "MontageGenerator10x15", GenerateurQuiPlante)
        fil = pb.archiver_en_arriere_plan(
            "10x15", ["a.jpg"], "id", str(tmp_path / "arch"), "retake",
        )
        fil.join(timeout=5)   # ne doit pas lever

    def test_sans_photo_aucun_thread(self):
        assert pb.archiver_en_arriere_plan("10x15", [], "id", "/tmp", "retake") is None

    def test_sans_identifiant_aucun_thread(self):
        assert pb.archiver_en_arriere_plan("10x15", ["a.jpg"], "", "/tmp", "retake") is None

    def test_mode_strips_utilise_le_bon_generateur(self, monkeypatch, tmp_path):
        appels = []
        monkeypatch.setattr(pb, "MontageGeneratorStrip",
                            type("G", (), {"final": staticmethod(
                                lambda p, i: appels.append("strip") or "")}))
        fil = pb.archiver_en_arriere_plan("strips", ["a.jpg"], "id", str(tmp_path), "retake")
        fil.join(timeout=5)
        assert appels == ["strip"]

    def test_plus_aucun_spinner_dans_les_handlers(self):
        """Le montage d'archive ne doit plus bloquer l'invité."""
        for nom in ("_handle_validation_10x15", "handle_fin_event"):
            source = inspect.getsource(getattr(pb, nom))
            assert "executer_avec_spinner" not in source, (
                f"{nom} fait encore attendre l'invité pour une archive"
            )
            assert "archiver_en_arriere_plan" in source, nom

    @pytest.mark.parametrize("handler", ["_handle_validation_10x15", "handle_fin_event"])
    def test_chemins_dabandon_nannoncent_pas_une_impression(self, handler):
        import inspect
        source = inspect.getsource(getattr(pb, handler))
        assert "TXT_PREPARATION_IMP" not in source, (
            f"{handler} archive une photo abandonnée ou reprise : il ne doit pas "
            "annoncer une préparation d'impression"
        )

    def test_impression_reelle_garde_son_message(self):
        import inspect
        source = inspect.getsource(pb.traiter_impression_session)
        assert "TXT_PREPARATION_IMP" in source, (
            "la vraie impression doit conserver son message d'attente"
        )


# ========================================================================================
# --- Interaction rafale × confirmation d'abandon ---
# ========================================================================================

class TestRafaleSuspenduePendantConfirmation:
    """En mode rafale, l'auto-validation partait même avec une confirmation
    armée : l'invité appuyait sur annuler, hésitait, et la borne enchaînait sur
    la photo suivante — l'annulation était perdue sans trace."""

    def test_auto_validation_suspendue(self):
        import inspect
        source = inspect.getsource(pb.render_validation)
        assert "abandon_arme" in source
        assert "and not abandon_arme" in source, (
            "l'auto-validation rafale doit être suspendue tant qu'une "
            "confirmation d'abandon est armée"
        )
