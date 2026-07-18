"""test_config_overrides.py — tests du loader d'overrides config."""
from __future__ import annotations

import json


class TestApplicationOverrides:
    def test_sans_fichier_valeurs_par_defaut(self, tmp_path, monkeypatch):
        monkeypatch.setattr("config.CONFIG_OVERRIDES_PATH", str(tmp_path / "absent.json"))
        import config
        config._appliquer_overrides()
        # Valeurs par défaut (vérifiées ailleurs, juste s'assurer que _appliquer est inerte)
        assert config.TEMPS_DECOMPTE == 5

    def test_override_int_valide(self, tmp_path, monkeypatch):
        path = tmp_path / "config_overrides.json"
        with open(path, "w") as f:
            json.dump({"TEMPS_DECOMPTE": 5}, f)
        import config
        monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(path))
        config._appliquer_overrides()
        assert config.TEMPS_DECOMPTE == 5
        # Remise en état pour ne pas polluer d'autres tests
        config.TEMPS_DECOMPTE = 5

    def test_cle_hors_whitelist_ignoree(self, tmp_path, monkeypatch):
        path = tmp_path / "config_overrides.json"
        with open(path, "w") as f:
            json.dump({"WIDTH": 9999, "TEMPS_DECOMPTE": 3}, f)
        import config
        original_width = config.WIDTH
        monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(path))
        config._appliquer_overrides()
        assert config.WIDTH == original_width  # non surchargé
        assert config.TEMPS_DECOMPTE == 3
        config.TEMPS_DECOMPTE = 1

    def test_mauvais_type_ignore(self, tmp_path, monkeypatch):
        path = tmp_path / "config_overrides.json"
        with open(path, "w") as f:
            json.dump({"TEMPS_DECOMPTE": "pas un int"}, f)
        import config
        monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(path))
        original = config.TEMPS_DECOMPTE
        config._appliquer_overrides()
        assert config.TEMPS_DECOMPTE == original

    def test_fichier_json_corrompu(self, tmp_path, monkeypatch):
        path = tmp_path / "config_overrides.json"
        path.write_text("{invalid json")
        import config
        monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(path))
        # Ne doit pas lever
        config._appliquer_overrides()

    def test_bool_respecte_strictement(self, tmp_path, monkeypatch):
        path = tmp_path / "config_overrides.json"
        # 1 est aussi un int : ne doit PAS être accepté comme bool
        with open(path, "w") as f:
            json.dump({"WATERMARK_ENABLED": 1}, f)
        import config
        monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(path))
        original = config.WATERMARK_ENABLED
        config._appliquer_overrides()
        assert config.WATERMARK_ENABLED == original

    def test_options_kiosque_booleennes(self, tmp_path, monkeypatch):
        path = tmp_path / "config_overrides.json"
        with open(path, "w") as f:
            json.dump({
                "ACTIVER_DIAPORAMA_VEILLE": False,
                "ACTIVER_IMPRESSIONS_MULTIPLES": False,
            }, f)
        import config
        monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(path))
        config._appliquer_overrides()
        assert config.ACTIVER_DIAPORAMA_VEILLE is False
        assert config.ACTIVER_IMPRESSIONS_MULTIPLES is False
        config.ACTIVER_DIAPORAMA_VEILLE = True
        config.ACTIVER_IMPRESSIONS_MULTIPLES = True

    def test_overrides_quota(self, tmp_path, monkeypatch):
        path = tmp_path / "config_overrides.json"
        with open(path, "w") as f:
            json.dump({
                "ACTIVER_QUOTA_IMPRESSIONS": False,
                "QUOTA_IMPRESSIONS_INITIAL": 200,
                "QUOTA_IMPRESSIONS_INCREMENT": 50,
            }, f)
        import config
        monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(path))
        config._appliquer_overrides()
        assert config.ACTIVER_QUOTA_IMPRESSIONS is False
        assert config.QUOTA_IMPRESSIONS_INITIAL == 200
        assert config.QUOTA_IMPRESSIONS_INCREMENT == 50
        config.ACTIVER_QUOTA_IMPRESSIONS = True
        config.QUOTA_IMPRESSIONS_INITIAL = 100
        config.QUOTA_IMPRESSIONS_INCREMENT = 100

    def test_quota_bool_strict(self, tmp_path, monkeypatch):
        path = tmp_path / "config_overrides.json"
        # 1 est aussi un int : ne doit PAS être accepté comme bool
        with open(path, "w") as f:
            json.dump({"ACTIVER_QUOTA_IMPRESSIONS": 1}, f)
        import config
        monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(path))
        original = config.ACTIVER_QUOTA_IMPRESSIONS
        config._appliquer_overrides()
        assert config.ACTIVER_QUOTA_IMPRESSIONS == original

    def test_int_pour_float_tolere(self, tmp_path, monkeypatch):
        path = tmp_path / "config_overrides.json"
        with open(path, "w") as f:
            json.dump({"DELAI_SECURITE": 3}, f)
        import config
        monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(path))
        original = config.DELAI_SECURITE
        config._appliquer_overrides()
        assert config.DELAI_SECURITE == 3.0
        assert isinstance(config.DELAI_SECURITE, float)
        config.DELAI_SECURITE = original
