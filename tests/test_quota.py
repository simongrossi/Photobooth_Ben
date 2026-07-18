"""test_quota.py — tests unitaires de core/quota.py.

Couvre : le compteur persistant de feuilles DNP (chargement, incrément,
déblocage, plancher du restant), la tolérance aux fichiers absents/corrompus,
l'écriture atomique, et la machine de saisie de séquence (SaisieSequence).
Isolation via monkeypatch de PATH_QUOTA vers tmp_path.
"""
from __future__ import annotations

import json
import os

import pytest

from core import quota
from core.quota import SaisieSequence


@pytest.fixture
def isoler_quota(monkeypatch, tmp_path):
    chemin = str(tmp_path / "quota_impressions.json")
    monkeypatch.setattr(quota, "PATH_QUOTA", chemin)
    monkeypatch.setattr(quota, "QUOTA_INITIAL", 100)
    return chemin


def _lire_json(chemin):
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


# --- charger_etat / quota_restant ---


class TestChargerEtat:
    def test_fichier_absent_valeurs_initiales(self, isoler_quota):
        etat = quota.charger_etat()
        assert etat["tirages_total"] == 0
        assert etat["quota"] == 100

    def test_quota_restant_initial(self, isoler_quota):
        assert quota.quota_restant() == 100

    def test_quota_restant_plancher_zero(self, isoler_quota):
        quota.enregistrer_tirage(150)
        assert quota.quota_restant() == 0


# --- enregistrer_tirage ---


class TestEnregistrerTirage:
    def test_incremente_et_persiste(self, isoler_quota):
        etat = quota.enregistrer_tirage(1)
        assert etat["tirages_total"] == 1
        # Relire depuis le disque : la valeur doit être persistée
        assert _lire_json(isoler_quota)["tirages_total"] == 1

    def test_cumule_sur_plusieurs_appels(self, isoler_quota):
        quota.enregistrer_tirage(1)
        quota.enregistrer_tirage(2)
        etat = quota.enregistrer_tirage(1)
        assert etat["tirages_total"] == 4
        assert quota.quota_restant() == 96

    def test_survit_a_une_relance(self, isoler_quota):
        """Le total ne repart jamais à 0 : relire le fichier simule un redémarrage."""
        quota.enregistrer_tirage(7)
        assert quota.charger_etat()["tirages_total"] == 7

    def test_ecrit_derniere_maj(self, isoler_quota):
        etat = quota.enregistrer_tirage(1)
        assert etat["derniere_maj"]

    def test_pas_de_fichier_tmp_residuel(self, isoler_quota):
        quota.enregistrer_tirage(1)
        dossier = os.path.dirname(isoler_quota)
        assert [f for f in os.listdir(dossier) if f.endswith(".tmp")] == []


# --- debloquer ---


class TestDebloquer:
    def test_augmente_le_quota(self, isoler_quota):
        etat = quota.debloquer(100)
        assert etat["quota"] == 200
        assert etat["tirages_total"] == 0
        assert _lire_json(isoler_quota)["quota"] == 200

    def test_cumule_les_deblocages(self, isoler_quota):
        quota.enregistrer_tirage(100)
        assert quota.quota_restant() == 0
        quota.debloquer(100)
        quota.debloquer(100)
        assert quota.quota_restant() == 200


# --- fichier corrompu ---


class TestFichierCorrompu:
    def test_json_invalide_repart_sans_exception(self, isoler_quota):
        with open(isoler_quota, "w", encoding="utf-8") as f:
            f.write("{pas du json")
        etat = quota.charger_etat()
        assert etat["tirages_total"] == 0
        assert etat["quota"] == 100

    def test_fichier_corrompu_est_conserve(self, isoler_quota):
        """Le fichier illisible est renommé .corrompu-<ts> (forensique), jamais écrasé en silence."""
        with open(isoler_quota, "w", encoding="utf-8") as f:
            f.write("{pas du json")
        quota.charger_etat()
        dossier = os.path.dirname(isoler_quota)
        assert any(".corrompu-" in f for f in os.listdir(dossier))

    def test_types_invalides_repartent_sans_exception(self, isoler_quota):
        with open(isoler_quota, "w", encoding="utf-8") as f:
            json.dump({"tirages_total": "beaucoup", "quota": None}, f)
        etat = quota.charger_etat()
        assert etat["tirages_total"] == 0
        assert etat["quota"] == 100


# --- SaisieSequence ---


class TestSaisieSequence:
    SEQ = (103, 100, 109)  # ord('g'), ord('d'), ord('m')

    def test_progression_complete(self):
        s = SaisieSequence(self.SEQ)
        assert s.presser(103) == "en_cours"
        assert s.progression == 1
        assert s.presser(100) == "en_cours"
        assert s.progression == 2
        assert s.presser(109) == "complete"
        assert s.progression == 3

    def test_mauvaise_touche_reset(self):
        s = SaisieSequence(self.SEQ)
        s.presser(103)
        assert s.presser(109) == "reset"
        assert s.progression == 0

    def test_mauvaise_premiere_touche(self):
        s = SaisieSequence(self.SEQ)
        assert s.presser(109) == "reset"
        assert s.progression == 0

    def test_reinitialiser(self):
        s = SaisieSequence(self.SEQ)
        s.presser(103)
        s.reinitialiser()
        assert s.progression == 0
        # La séquence reste utilisable après reset
        assert s.presser(103) == "en_cours"

    def test_reutilisable_apres_complete(self):
        s = SaisieSequence(self.SEQ)
        for touche in self.SEQ:
            s.presser(touche)
        s.reinitialiser()
        assert s.presser(103) == "en_cours"
        assert s.presser(100) == "en_cours"
        assert s.presser(109) == "complete"
