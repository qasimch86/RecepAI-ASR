"""recepai_shared

Shared infrastructure package for RecepAI Python services.

Exports:
- settings: Pydantic `VoiceStackSettings` instance
- get_logger: logging helper
- init_tracer: tracing no-op stub
"""

from .config import settings, VoiceStackSettings
from .local_config import load_local_config
from .logging_utils import get_logger
from .tracing import init_tracer

__all__ = ["settings", "VoiceStackSettings", "load_local_config", "get_logger", "init_tracer"]
