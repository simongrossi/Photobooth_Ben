"""test_web_backups.py — sauvegardes ZIP des événements terminés."""
from __future__ import annotations

import os
from datetime import datetime

import pytest

from web import backups


@pytest.fixture(autouse=True)
def _dossier(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "PATH_BACKUPS", str(tmp_path / "data" / "backups"))


def _poser(nom: str, contenu: bytes = b"zip") -> str:
    chemin = os.path.join(backups.dossier(), nom)
    with open(chemin, "wb") as fichier:
        fichier.write(contenu)
    return chemin


class TestNommage:
    def test_nom_contient_slug_et_horodatage(self):
        moment = datetime(2026, 8, 24, 21, 5)
        assert backups.nom_pour("mariage-alice-ben", moment) == "mariage-alice-ben__20260824-2105.zip"

    def test_chemin_dans_le_dossier_backups(self):
        chemin = backups.chemin_pour("test")
        assert os.path.dirname(chemin) == backups.dossier()

    def test_slug_a_tirets_reste_lisible(self):
        """Le double underscore sépare : un slug peut contenir des tirets."""
        nom = backups.nom_pour("coupe-du-monde-2026", datetime(2026, 7, 14, 18, 0))
        [sauvegarde] = (_poser(nom), backups.lister())[1]
        assert sauvegarde.slug == "coupe-du-monde-2026"
        assert sauvegarde.horodatage == "20260714-1800"


class TestListing:
    def test_dossier_absent(self, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "PATH_BACKUPS", str(tmp_path / "jamais-cree"))
        assert backups.lister() == []

    def test_plus_recente_en_premier(self):
        _poser("a__20260101-1200.zip")
        recent = _poser("b__20260601-1200.zip")
        os.utime(recent, (2_000_000_000, 2_000_000_000))
        assert [s.slug for s in backups.lister()] == ["b", "a"]

    def test_filtre_par_slug(self):
        _poser("mariage__20260101-1200.zip")
        _poser("anniversaire__20260101-1200.zip")
        assert [s.slug for s in backups.lister("mariage")] == ["mariage"]

    def test_fichiers_etrangers_ignores(self):
        _poser("mariage__20260101-1200.zip")
        _poser("notes.txt")
        _poser("archive-sans-horodatage.zip")
        assert [s.nom for s in backups.lister()] == ["mariage__20260101-1200.zip"]

    def test_date_lisible(self):
        _poser("x__20260824-2105.zip")
        assert backups.lister()[0].date_lisible == "24/08/2026 à 21:05"

    def test_taille_reportee(self):
        _poser("x__20260824-2105.zip", b"y" * 4096)
        assert backups.lister()[0].taille == 4096


class TestSecuriteChemin:
    @pytest.mark.parametrize("nom", [
        "../../../etc/passwd",
        "../raw/photo.jpg",
        "photo.jpg",
        "sans_horodatage.zip",
        "x__20260824-2105.zip.txt",
        "",
    ])
    def test_noms_refuses(self, nom):
        assert backups.resoudre(nom) is None
        assert backups.supprimer(nom) is False

    def test_ne_sort_pas_du_dossier_via_lien(self, tmp_path):
        """Un lien symbolique sortant ne doit pas exposer de fichier externe."""
        externe = tmp_path / "photo_precieuse.jpg"
        externe.write_bytes(b"photo")
        lien = os.path.join(backups.dossier(), "piege__20260101-1200.zip")
        os.symlink(externe, lien)
        assert backups.resoudre("piege__20260101-1200.zip") is None
        assert externe.exists()


class TestSuppression:
    def test_supprime_apres_confirmation(self):
        _poser("mariage__20260101-1200.zip")
        assert backups.supprimer("mariage__20260101-1200.zip") is True
        assert backups.lister() == []

    def test_rien_ne_supprime_sans_confirmation(self):
        """Aucune purge automatique : le listing ne doit jamais rien effacer."""
        chemin = _poser("vieille__20200101-1200.zip")
        os.utime(chemin, (0, 0))  # très ancienne
        for _ in range(3):
            backups.lister()
            backups.dossier()
        assert os.path.exists(chemin)

    def test_absente_renvoie_false(self):
        assert backups.supprimer("jamais__20260101-1200.zip") is False
