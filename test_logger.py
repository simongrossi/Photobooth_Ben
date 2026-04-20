"""test_logger.py — tests unitaires du wrapper de logging.

Valide `log_error` (wrapper legacy avec détection de niveau depuis emojis).
Les 3 helpers nommés (`log_info`/`log_warning`/`log_critical`) sont testés
transitivement par les autres modules.
"""
import logging

from core import logger


class TestLogError:
    def test_niveau_info_par_defaut(self, caplog):
        with caplog.at_level(logging.INFO, logger="photobooth"):
            logger.log_error("message banal")
        assert any("message banal" in r.message and r.levelno == logging.INFO
                   for r in caplog.records)

    def test_niveau_error_sur_cross(self, caplog):
        with caplog.at_level(logging.ERROR, logger="photobooth"):
            logger.log_error("❌ erreur critique")
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_niveau_warning_sur_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="photobooth"):
            logger.log_error("⚠️ attention")
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_non_string_ne_crashe_pas(self, capsys):
        # input non-string : la branche except attrape, print sur stdout
        logger.log_error(None)  # type: ignore[arg-type]
