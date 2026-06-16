import logging
from logging.config import dictConfig

from .settings import get_rag_settings


def configure_logging() -> None:
    settings = get_rag_settings()

    log_file = settings.rag_log_dir / "medical_claim_ai_rag.log"
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": settings.rag_log_level,
                    "formatter": "standard",
                },
                "file": {
                    "class": "logging.FileHandler",
                    "level": settings.rag_log_level,
                    "formatter": "standard",
                    "filename": str(log_file),
                    "encoding": "utf-8",
                },
            },
            "root": {
                "level": settings.rag_log_level,
                "handlers": ["console", "file"],
            },
        }
    )

    logging.getLogger(__name__).debug("RAG logging configured")
