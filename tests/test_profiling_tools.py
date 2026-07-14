"""Tests des points d'entrée de profilage, sans lancer Pygame."""
import importlib
import sys
from types import SimpleNamespace


def test_cprofile_reste_importable_depuis_la_racine():
    module = importlib.import_module("cProfile")
    assert hasattr(module, "Profile")


def test_profile_app_appelle_main(monkeypatch):
    import profile_app

    appels = []
    monkeypatch.setitem(sys.modules, "Photobooth_start", SimpleNamespace(main=lambda: appels.append(True)))

    profile_app._executer_application()

    assert appels == [True]
