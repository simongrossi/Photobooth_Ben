"""test_config_assets.py — résolution actif/défaut des assets kiosque (volet 2)."""
import config


class TestResoudreActif:
    def test_prefere_actif_si_present(self, tmp_path):
        actif = tmp_path / "actif.jpg"
        actif.write_bytes(b"x")
        assert config.resoudre_actif(str(actif), "/defaut.jpg") == str(actif)

    def test_fallback_si_actif_absent(self, tmp_path):
        absent = str(tmp_path / "absent.jpg")
        assert config.resoudre_actif(absent, "/defaut.jpg") == "/defaut.jpg"


class TestConstantesVolet2:
    def test_constantes_presentes(self):
        for nom in ("FILE_BG_ACCUEIL_ACTIF", "POLICE_FICHIER_ACTIF", "PATH_SLIDESHOW_PERSO",
                    "PATH_CORBEILLE", "PATH_ACCUEIL_BIBLIO", "PATH_FONTS_BIBLIO",
                    "BG_ACCUEIL_EFFECTIF", "POLICE_EFFECTIVE"):
            assert hasattr(config, nom), nom
