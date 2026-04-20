"""logger.py — configuration du logging standard avec rotation.

Module self-contained : crée le dossier logs/ au besoin, configure le logger
`photobooth` (fichier + console), expose `log_error()` compatible avec le code
historique (détection auto du niveau depuis les emojis en début de message).

Sprint 5.1 + 4.6 : extrait de Photobooth_start.py pour pouvoir être importé
par camera.py / printer.py / session.py sans dépendance circulaire.
"""
import logging
import logging.handlers
import os

# Crée le dossier logs si besoin — ce module peut être importé avant le bootstrap
# principal qui crée les autres dossiers.
_LOG_DIR = "logs"
os.makedirs(_LOG_DIR, exist_ok=True)
log_file = os.path.join(_LOG_DIR, "photobooth.log")

_logger = logging.getLogger("photobooth")
_logger.setLevel(logging.DEBUG)
if not _logger.handlers:
    _fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _handler_fichier = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    _handler_fichier.setFormatter(_fmt)
    _handler_fichier.setLevel(logging.INFO)
    _logger.addHandler(_handler_fichier)

    _handler_console = logging.StreamHandler()
    _handler_console.setFormatter(logging.Formatter("📝 %(message)s"))
    _handler_console.setLevel(logging.INFO)
    _logger.addHandler(_handler_console)


def log_info(message):
    """Log explicite niveau INFO. Pour flux normal (démarrage session, photo sauvegardée, etc.)."""
    _logger.info(message)


def log_warning(message):
    """Log explicite niveau WARNING. Pour anomalies non-bloquantes (retry, état dégradé)."""
    _logger.warning(message)


def log_critical(message):
    """Log explicite niveau ERROR. Pour échecs bloquants (capture perdue, imprimante offline)."""
    _logger.error(message)


def log_error(message):
    """Wrapper historique — backward compat. Détecte le niveau depuis ❌/⚠️ en début de
    message, sinon INFO par défaut. Pour du code nouveau, préférer log_info/log_warning/log_critical."""
    try:
        niveau = logging.INFO
        debut = message[:2] if isinstance(message, str) else ""
        if "❌" in debut:
            niveau = logging.ERROR
        elif "⚠️" in debut:
            niveau = logging.WARNING
        _logger.log(niveau, message)
    except Exception as e:
        print(f"❌ Erreur critique LOG : {message} ({e})")
