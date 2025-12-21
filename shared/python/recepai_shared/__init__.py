"""recepai_shared

Shared infrastructure package for RecepAI Python services.

Provides minimal Phase 0 utilities:
- Configuration via Pydantic BaseSettings (see `config.py`)
- Logging helper for consistent stdout formatting (see `logging_utils.py`)
- Placeholder tracer hook for future OpenTelemetry integration (see `tracing.py`)
"""

from .config import settings, VoiceStackSettings
from .logging_utils import get_logger

__all__ = ["settings", "VoiceStackSettings", "get_logger"]
