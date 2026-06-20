import logging
from logging.config import dictConfig
from pathlib import Path

from config.logging_context import get_request_id
from config.settings import Settings, get_settings


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", get_request_id())
        record.phase = getattr(record, "phase", "-")
        return True


def configure_logging(settings: Settings | None = None) -> None:
    config = settings or get_settings()
    log_file = Path(config.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | request_id=%(request_id)s | phase=%(phase)s | %(message)s",
                }
            },
            "filters": {
                "request_context": {
                    "()": RequestContextFilter,
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": config.log_level.upper(),
                    "filters": ["request_context"],
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "default",
                    "level": config.log_level.upper(),
                    "filename": str(log_file),
                    "maxBytes": 10 * 1024 * 1024,
                    "backupCount": 5,
                    "encoding": "utf-8",
                    "filters": ["request_context"],
                },
            },
            "root": {
                "handlers": ["console", "file"],
                "level": config.log_level.upper(),
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
