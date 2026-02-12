import os
import logging
import logging.config

_DEFAULT_LEVEL = "INFO"
_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

_level = os.getenv("LOG_LEVEL", _DEFAULT_LEVEL).upper()
_fmt = os.getenv("LOG_FORMAT", _DEFAULT_FORMAT)
_datefmt = os.getenv("LOG_DATEFMT", "%Y-%m-%d %H:%M:%S")
_file = os.getenv("LOG_FILE")
_json = os.getenv("LOG_JSON", "false").lower() == "true"

_handlers = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "standard",
        "level": _level,
    }
}

if _file:
    _handlers["file"] = {
        "class": "logging.FileHandler",
        "filename": _file,
        "formatter": "json" if _json else "standard",
        "level": _level,
    }

_formatters = {
    "standard": {"format": _fmt, "datefmt": _datefmt},
}

if _json:
    _formatters["json"] = {
        "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
        "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        "datefmt": _datefmt,
    }

_logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": _formatters,
    "handlers": _handlers,
    "root": {"level": _level, "handlers": list(_handlers.keys())},
}

logging.config.dictConfig(_logging_config)


def get_logger(name: str = __name__) -> logging.Logger:
    """Return a logger instance with the given name.

    The logger is configured according to environment variables
    (LOG_LEVEL, LOG_FORMAT, LOG_DATEFMT, LOG_FILE, LOG_JSON)."""
    return logging.getLogger(name)
