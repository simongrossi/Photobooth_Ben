"""test_web_exports.py — construction différée des archives ZIP et suivi de progression."""
from __future__ import annotations

import os
import pathlib
import zipfile

import pytest

from web import exports


class _Usage:
    """Faux retour de shutil.disk_usage pour simuler un disque plein."""

    def __init__(self, free):
        self.free = free
        self.total = free
        self.used = 0


@pytest.fixture(autouse=True)
def _dossier_data(tmp_path, monkeypatch):
    """Isole data/cache/exports/ : aucun test n'écrit dans le vrai data/."""
    import config
    monkeypatch.setattr(config, "PATH_DATA", str(tmp_path / "data"))


@pytest.fixture
def fichiers(tmp_path):
    sources = []
    for i in range(3):
        chemin = tmp_path / f"photo_{i}.jpg"
        chemin.write_bytes(b"\xff\xd8\xff" + b"x" * 100)
        sources.append((str(chemin), f"photos/10x15/photo_{i}.jpg"))
    return sources


def _echouer(*args, **kwargs):
    raise OSError(28, "No space left on device")


@pytest.fixture(autouse=True)
def _taches_propres():
    yield
    for tache_id in list(exports._taches):
        exports.oublier(tache_id)


class TestNonDestruction:
    """L'export ne doit JAMAIS toucher aux photos : il ne fait que les lire."""

    def test_la_purge_ne_touche_qu_au_dossier_exports(self, tmp_path, fichiers):
        import config

        # Reproduit l'arborescence data/ avec des photos partout, toutes vieilles
        # (donc « expirées » du point de vue du TTL) pour maximiser le risque.
        photos = []
        for sous in ("raw", "print/print_10x15", "print/print_strip",
                     "skipped/skipped_deleted", "corbeille/10x15", "temp", "cache/thumbs"):
            dossier = tmp_path / "data" / sous
            dossier.mkdir(parents=True, exist_ok=True)
            photo = dossier / "photo_precieuse.jpg"
            photo.write_bytes(b"\xff\xd8 photo irremplacable")
            os.utime(photo, (0, 0))
            photos.append(photo)

        # Une vraie orpheline dans le dossier d'exports, elle doit disparaître.
        orpheline = pathlib.Path(exports.dossier_archives()) / "export-vieille.zip"
        orpheline.write_bytes(b"zip")
        os.utime(orpheline, (0, 0))

        exports.demarrer("declencheur.zip", "", fichiers)

        assert not orpheline.exists(), "l'orpheline aurait dû être purgée"
        for photo in photos:
            assert photo.exists(), f"PHOTO SUPPRIMÉE : {photo.relative_to(tmp_path)}"
        assert config.PATH_DATA == str(tmp_path / "data")

    def test_les_sources_survivent_a_la_construction(self, tmp_path, fichiers):
        exports.attendre(exports.demarrer("a.zip", "", fichiers))
        for source, _ in fichiers:
            assert os.path.isfile(source), "l'archivage ne doit pas déplacer les sources"

    def test_les_sources_survivent_a_un_echec(self, tmp_path, fichiers, monkeypatch):
        monkeypatch.setattr(exports, "construire", _echouer)
        exports.attendre(exports.demarrer("a.zip", "", fichiers))
        for source, _ in fichiers:
            assert os.path.isfile(source)


class TestDestination:
    """Archive déplacée vers un emplacement stable (cas des sauvegardes)."""

    def test_archive_deplacee_vers_la_destination(self, tmp_path, fichiers):
        cible = str(tmp_path / "backups" / "evenement.zip")
        tache = exports.attendre(exports.demarrer("evenement.zip", "", fichiers, destination=cible))
        assert tache.etat == "pret"
        assert tache.chemin == cible
        assert os.path.isfile(cible)
        assert not os.path.exists(tache.chemin_travail), "le fichier de travail doit avoir été renommé"
        with zipfile.ZipFile(cible) as archive:
            assert len(archive.namelist()) == 3

    def test_destination_lisible_pour_copie(self, tmp_path, fichiers):
        """tempfile crée en 0600 ; une sauvegarde doit rester copiable."""
        cible = str(tmp_path / "backups" / "evenement.zip")
        exports.attendre(exports.demarrer("e.zip", "", fichiers, destination=cible))
        assert oct(os.stat(cible).st_mode)[-3:] == "644"

    def test_destination_impossible_remonte_en_erreur(self, tmp_path, fichiers, monkeypatch):
        def _refus(*args, **kwargs):
            raise OSError(13, "Permission denied")

        monkeypatch.setattr(exports.os, "replace", _refus)
        cible = str(tmp_path / "backups" / "evenement.zip")
        tache = exports.attendre(exports.demarrer("e.zip", "", fichiers, destination=cible))
        assert tache.etat == "erreur"
        assert "Permission denied" in tache.erreur
        assert not os.path.exists(cible)
        assert not os.path.exists(tache.chemin_travail), "pas de fichier de travail abandonné"

    def test_purge_epargne_une_archive_a_destination(self, tmp_path, fichiers):
        cible = str(tmp_path / "backups" / "evenement.zip")
        tache_id = exports.demarrer("e.zip", "", fichiers, destination=cible)
        exports.attendre(tache_id)
        exports.etat(tache_id).fini_le -= exports.TTL_S + 1
        exports.demarrer("declencheur.zip", "", [])  # déclenche la purge
        assert exports.etat(tache_id) is None, "la tâche doit être oubliée"
        assert os.path.isfile(cible), "mais la sauvegarde doit survivre"

    def test_oublier_epargne_une_archive_a_destination(self, tmp_path, fichiers):
        cible = str(tmp_path / "backups" / "evenement.zip")
        tache_id = exports.demarrer("e.zip", "", fichiers, destination=cible)
        exports.attendre(tache_id)
        exports.oublier(tache_id)
        assert os.path.isfile(cible)


class TestEspaceDisque:
    def test_refuse_si_le_disque_ne_suit_pas(self, fichiers, monkeypatch):
        """Échouer tout de suite vaut mieux que remplir le disque à mi-parcours."""
        monkeypatch.setattr(exports.shutil, "disk_usage", lambda _: _Usage(1000))
        with pytest.raises(exports.EspaceInsuffisant) as echec:
            exports.demarrer("a.zip", "", fichiers)
        assert echec.value.disponible == 1000
        # Le message distingue la taille de l'archive de la marge exigée.
        assert "d'archive" in str(echec.value) and "de marge" in str(echec.value)

    def test_estimation_egale_a_la_somme_des_sources(self, fichiers, tmp_path):
        attendu = sum(os.path.getsize(src) for src, _ in fichiers)
        assert exports.verifier_espace(fichiers, str(tmp_path)) == attendu

    def test_source_manquante_ignoree_dans_l_estimation(self, fichiers, tmp_path):
        fichiers.append((str(tmp_path / "absent.jpg"), "photos/raw/absent.jpg"))
        attendu = sum(os.path.getsize(src) for src, _ in fichiers if os.path.isfile(src))
        assert exports.verifier_espace(fichiers, str(tmp_path)) == attendu

    def test_archive_ecrite_dans_data_pas_dans_tmp(self, fichiers):
        """/tmp est un tmpfs en RAM sur beaucoup d'installations."""
        chemin = exports.attendre(exports.demarrer("a.zip", "", fichiers)).chemin
        assert os.path.join("data", "cache", "exports") in chemin


class TestOctetsLisibles:
    @pytest.mark.parametrize("octets, attendu", [
        (512, "512 o"), (1536, "1.5 Ko"), (1536 * 1024, "1.5 Mo"), (2_930_000_000, "2.7 Go"),
    ])
    def test_formats(self, octets, attendu):
        assert exports.octets_lisibles(octets) == attendu


class TestConstruire:
    def test_ecrit_fichiers_et_extras(self, tmp_path, fichiers):
        zip_path = tmp_path / "sortie.zip"
        inclus = exports.construire(str(zip_path), fichiers, {"manifest.json": "{}"})
        assert inclus == 3
        with zipfile.ZipFile(zip_path) as archive:
            assert "manifest.json" in archive.namelist()
            assert len([n for n in archive.namelist() if n.startswith("photos/")]) == 3

    def test_images_stockees_sans_compression(self, tmp_path, fichiers):
        """Le deflate ne gagne rien sur du JPEG et coûte l'essentiel du temps CPU."""
        zip_path = tmp_path / "sortie.zip"
        exports.construire(str(zip_path), fichiers, {"manifest.json": "{}"})
        with zipfile.ZipFile(zip_path) as archive:
            assert archive.getinfo("photos/10x15/photo_0.jpg").compress_type == zipfile.ZIP_STORED
            assert archive.getinfo("manifest.json").compress_type == zipfile.ZIP_DEFLATED

    def test_fichier_disparu_ignore(self, tmp_path, fichiers):
        fichiers.append((str(tmp_path / "jamais.jpg"), "photos/raw/jamais.jpg"))
        zip_path = tmp_path / "sortie.zip"
        assert exports.construire(str(zip_path), fichiers) == 3

    def test_erreur_d_ecriture_propagee_et_non_avalee(self, tmp_path, fichiers, monkeypatch):
        """Régression : un disque plein produisait une archive tronquée annoncée « prête ».

        L'ancien `except OSError: pass` traitait « disque plein » comme un
        fichier source manquant, et l'export finissait à 100 % avec une archive
        incomplète — le pire des cas pour l'utilisateur.
        """
        vraie_ecriture = zipfile.ZipFile.write

        def _disque_plein(self, source, nom_archive=None, **kw):
            if "photo_1" in str(source):
                raise OSError(28, "No space left on device")
            return vraie_ecriture(self, source, nom_archive, **kw)

        monkeypatch.setattr(zipfile.ZipFile, "write", _disque_plein)
        with pytest.raises(OSError, match="No space left"):
            exports.construire(str(tmp_path / "sortie.zip"), fichiers)

    def test_progression_appelee_par_fichier(self, tmp_path, fichiers):
        appels = []
        exports.construire(str(tmp_path / "s.zip"), fichiers, progression=lambda: appels.append(1))
        assert len(appels) == 3


class TestTache:
    def test_cycle_complet(self, fichiers):
        tache_id = exports.demarrer("archive.zip", "3 images", fichiers)
        tache = exports.attendre(tache_id)
        assert tache.etat == "pret"
        assert tache.faits == tache.total == 3
        assert tache.pourcent == 100
        assert os.path.isfile(tache.chemin)

    def test_pourcent_plafonne_avant_la_fin(self):
        tache = exports.Tache(id="x", nom_fichier="a.zip", libelle="", total=10, retour="/")
        tache.faits = 10
        assert tache.pourcent == 99  # « pret » seul autorise 100 %
        tache.total = 0
        assert tache.pourcent == 0

    def test_etat_serialisable(self, fichiers):
        tache_id = exports.demarrer("archive.zip", "3 images", fichiers)
        exports.attendre(tache_id)
        etat = exports.etat(tache_id).as_dict()
        assert etat["etat"] == "pret"
        assert etat["nom_fichier"] == "archive.zip"
        assert etat["erreur"] is None

    def test_archive_partielle_supprimee_en_cas_d_echec(self, fichiers, monkeypatch):
        monkeypatch.setattr(exports, "construire", _echouer)
        tache = exports.attendre(exports.demarrer("a.zip", "", fichiers))
        assert tache.etat == "erreur"
        assert not os.path.exists(tache.chemin_travail)
        assert tache.chemin is None

    def test_orphelines_purgees(self, fichiers, tmp_path):
        """Un redémarrage du service perd le registre mais laisse les fichiers."""
        dossier = exports.dossier_archives()
        orpheline = os.path.join(dossier, "export-orpheline.zip")
        with open(orpheline, "wb") as f:
            f.write(b"x")
        os.utime(orpheline, (0, 0))  # vieille de bien plus que le TTL
        exports.demarrer("a.zip", "", [])
        assert not os.path.exists(orpheline)

    def test_erreur_de_construction_remontee(self, fichiers, monkeypatch):
        monkeypatch.setattr(exports, "construire", lambda *a, **k: (_ for _ in ()).throw(OSError("disque plein")))
        tache = exports.attendre(exports.demarrer("a.zip", "", fichiers))
        assert tache.etat == "erreur"
        assert "disque plein" in tache.erreur

    def test_role_requis_par_defaut_lecture(self, fichiers):
        assert exports.etat(exports.demarrer("a.zip", "", fichiers)).role_requis == "lecture"
        tache_id = exports.demarrer("b.zip", "", fichiers, role_requis="admin")
        assert exports.etat(tache_id).role_requis == "admin"

    def test_tache_inconnue(self):
        assert exports.etat("inexistante") is None

    def test_purge_des_archives_expirees(self, fichiers):
        tache_id = exports.demarrer("archive.zip", "", fichiers)
        chemin = exports.attendre(tache_id).chemin
        exports.etat(tache_id).fini_le -= exports.TTL_S + 1
        exports.demarrer("autre.zip", "", [])  # toute création déclenche la purge
        assert exports.etat(tache_id) is None
        assert not os.path.exists(chemin)

    def test_plafond_de_taches_conservees(self, fichiers):
        ids = [exports.demarrer(f"a{i}.zip", "", fichiers) for i in range(exports.MAX_TACHES + 3)]
        for tache_id in ids:
            exports.attendre(tache_id)
        exports.demarrer("declencheur.zip", "", [])
        assert len(exports._taches) <= exports.MAX_TACHES
        assert exports.etat(ids[-1]) is not None  # les plus récentes survivent
