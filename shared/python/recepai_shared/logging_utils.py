import logging
import os
from typing import Optional

_LOG_LEVEL_ENV_VAR = "RECEPAI_LOG_LEVEL"


def _get_log_level_from_env() -> int:
    level_name = os.getenv(_LOG_LEVEL_ENV_VAR, "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name if name else "recepai")
    if not logger.handlers:
        logger.setLevel(_get_log_level_from_env())
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    else:
        logger.setLevel(_get_log_level_from_env())
    return logger
