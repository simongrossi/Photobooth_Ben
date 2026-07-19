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

import time
from types import SimpleNamespace

import pytest

import Photobooth_start as pb
from core.session import Etat, SessionState

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
        monkeypatch.setattr(pb, "executer_avec_spinner", lambda fn, msg: "/tmp/x.jpg")
        monkeypatch.setattr(pb.shutil, "move", lambda *a, **k: None)
        session.mode_actuel = "10x15"
        avant = session.id_session_timestamp

        pb._handle_validation_10x15(touche(GAUCHE), session, time.time())

        assert session.photos_validees == []
        assert session.etat is Etat.DECOMPTE
        assert session.id_session_timestamp == avant, (
            "la reprise ne doit pas repartir sur une nouvelle session"
        )

    def test_recommencer_depuis_fin_conserve_lidentifiant(self, session, sans_effets, monkeypatch):
        monkeypatch.setattr(pb, "executer_avec_spinner", lambda fn, msg: "/tmp/x.jpg")
        monkeypatch.setattr(pb.os.path, "exists", lambda p: False)
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

class TestMessageArchivage:
    """Annoncer « Préparation de votre impression » à quelqu'un qui vient
    d'annuler lui fait croire que son annulation n'a pas été prise en compte."""

    def test_constante_distincte(self):
        import config
        assert config.TXT_ARCHIVAGE_EN_COURS
        assert config.TXT_ARCHIVAGE_EN_COURS != config.TXT_PREPARATION_IMP

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
