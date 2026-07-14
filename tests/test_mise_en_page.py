"""Tests de la géométrie 10×15 partagée entre admin et moteur de montage."""
import json

import pytest

from core.mise_en_page import (
    MiseEnPage10x15,
    MiseEnPageStrip,
    charger_mise_en_page,
    charger_mise_en_page_strip,
    ecrire_mise_en_page,
    ecrire_mise_en_page_strip,
)


CANVAS = (1800, 1200)
DEFAUT = MiseEnPage10x15(x=250, y=175, largeur=1300, hauteur=866)


def test_mise_en_page_valide_dans_canvas():
    assert DEFAUT.est_valide(CANVAS)
    assert not MiseEnPage10x15(x=1700, y=0, largeur=200, hauteur=100).est_valide(CANVAS)


def test_charge_fichier_valide(tmp_path):
    chemin = tmp_path / "layout.json"
    chemin.write_text(json.dumps({"x": 100, "y": 50, "largeur": 1500, "hauteur": 1000}))

    resultat = charger_mise_en_page(str(chemin), DEFAUT, CANVAS)

    assert resultat == MiseEnPage10x15(x=100, y=50, largeur=1500, hauteur=1000)


@pytest.mark.parametrize("contenu", ["{cassé", "{}", '{"x": -1, "y": 0, "largeur": 10, "hauteur": 10}'])
def test_charge_invalide_retombe_sur_defaut(tmp_path, contenu):
    chemin = tmp_path / "layout.json"
    chemin.write_text(contenu)
    assert charger_mise_en_page(str(chemin), DEFAUT, CANVAS) == DEFAUT


def test_ecriture_atomique_avec_template_id(tmp_path):
    chemin = tmp_path / "data" / "layout.json"

    ecrire_mise_en_page(str(chemin), DEFAUT, CANVAS, template_id=42)

    donnees = json.loads(chemin.read_text())
    assert donnees["template_id"] == 42
    assert donnees["largeur"] == 1300
    assert not chemin.with_suffix(".json.tmp").exists()


def test_ecriture_refuse_zone_hors_canvas(tmp_path):
    invalide = MiseEnPage10x15(x=0, y=0, largeur=2000, hauteur=1200)
    with pytest.raises(ValueError):
        ecrire_mise_en_page(str(tmp_path / "layout.json"), invalide, CANVAS)


def test_charge_et_ecrit_mise_en_page_strip(tmp_path):
    canvas = (600, 1800)
    mise_en_page = MiseEnPageStrip(photos=(
        MiseEnPage10x15(20, 40, 500, 333),
        MiseEnPage10x15(30, 600, 480, 320),
        MiseEnPage10x15(40, 1200, 450, 300),
    ))
    chemin = tmp_path / "data" / "strip.json"

    ecrire_mise_en_page_strip(str(chemin), mise_en_page, canvas, template_id=7)

    assert charger_mise_en_page_strip(str(chemin), mise_en_page, canvas) == mise_en_page
    donnees = json.loads(chemin.read_text())
    assert donnees["format"] == "strip"
    assert donnees["template_id"] == 7
    assert len(donnees["photos"]) == 3


def test_mise_en_page_strip_invalide_retombe_sur_defaut(tmp_path):
    canvas = (600, 1800)
    defaut = MiseEnPageStrip(photos=(DEFAUT, DEFAUT, DEFAUT))
    chemin = tmp_path / "strip.json"
    chemin.write_text(json.dumps({"photos": [{"x": 0, "y": 0, "largeur": 10, "hauteur": 10}]}))

    assert charger_mise_en_page_strip(str(chemin), defaut, canvas) == defaut
