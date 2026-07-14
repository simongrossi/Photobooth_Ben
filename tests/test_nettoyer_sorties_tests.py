"""Tests du nettoyage réversible des sorties techniques dans data/print."""
from pathlib import Path

from nettoyer_sorties_tests import deplacer_sorties_tests, lister_sorties_tests


def test_liste_uniquement_sorties_techniques(tmp_path):
    print_dir = tmp_path / "print"
    strip = print_dir / "print_strip"
    strip.mkdir(parents=True)
    mire = strip / "montage_strip_test_session_CLEAN.jpg"
    vraie = strip / "montage_strip_2026-07-14_18h30_12_CLEAN.jpg"
    mire.write_bytes(b"test")
    vraie.write_bytes(b"photo")

    assert lister_sorties_tests(str(print_dir)) == [str(mire)]


def test_deplace_en_conservant_arborescence(tmp_path):
    print_dir = tmp_path / "print"
    ready = print_dir / "print_strip" / "READY_TO_PRINT"
    ready.mkdir(parents=True)
    source = ready / "montage_strip_strip_wm_READY_TO_PRINT.jpg"
    source.write_bytes(b"test")
    corbeille = tmp_path / "corbeille"

    destinations = deplacer_sorties_tests(
        [str(source)], path_print=str(print_dir), path_corbeille=str(corbeille),
    )

    assert not source.exists()
    destination = Path(destinations[0])
    assert destination.exists()
    assert destination.relative_to(corbeille) == Path(
        "sorties_tests/print_strip/READY_TO_PRINT/montage_strip_strip_wm_READY_TO_PRINT.jpg"
    )


def test_necrase_pas_un_fichier_deja_deplace(tmp_path):
    print_dir = tmp_path / "print"
    print_dir.mkdir()
    source = print_dir / "mire.jpg"
    source.write_bytes(b"nouveau")
    corbeille = tmp_path / "corbeille"
    destination = corbeille / "sorties_tests" / "mire.jpg"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"ancien")

    destinations = deplacer_sorties_tests(
        [str(source)], path_print=str(print_dir), path_corbeille=str(corbeille),
    )

    assert Path(destinations[0]).name == "mire_2.jpg"
    assert destination.read_bytes() == b"ancien"
