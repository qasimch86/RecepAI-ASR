import logging
import os
from typing import Any, Optional

_LOG_LEVEL_ENV_VAR = "RECEPAI_LOG_LEVEL"


class _RecepAISafeExtraFormatter(logging.Formatter):
    """Formatter that appends common correlation extras when present.

    Never raises if extras are absent.
    """

    _FIELD_ORDER = ("requestId", "sessionId", "turnId", "service")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)

        parts: list[str] = []
        for field in self._FIELD_ORDER:
            value = getattr(record, field, None)
            if value is not None:
                parts.append(f"{field}={value}")

        # Support either 'corr' or 'correlationId' (render as 'corr=...').
        corr_value = getattr(record, "corr", None)
        if corr_value is None:
            corr_value = getattr(record, "correlationId", None)
        if corr_value is not None:
            parts.insert(3, f"corr={corr_value}")

        if not parts:
            return base
        return base + " | " + " ".join(parts)


def log_extra(**kwargs: Any) -> dict[str, Any]:
    """Helper to build a safe logging 'extra' dict.

    Filters out None values so callers don't need to pass every field.
    """

    return {k: v for k, v in kwargs.items() if v is not None}


def _get_log_level_from_env() -> int:
    level_name = os.getenv(_LOG_LEVEL_ENV_VAR, "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name if name else "recepai")
    if not logger.handlers:
        logger.setLevel(_get_log_level_from_env())
        handler = logging.StreamHandler()
        formatter = _RecepAISafeExtraFormatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    else:
        logger.setLevel(_get_log_level_from_env())
    return logger


def init_logging() -> logging.Logger:
    """Initialize the default RecepAI logger.

    This is intentionally minimal; services typically use get_logger(...).
    """

    return get_logger("recepai")
