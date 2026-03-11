from __future__ import annotations

import os
import threading
from typing import Optional, Dict, Any


class ISttBackend:
    def transcribe(
        self,
        audio_bytes: bytes,
        fmt: str,
        sample_rate: int,
        channels: int,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class MockSttBackend(ISttBackend):
    def transcribe(
        self,
        audio_bytes: bytes,
        fmt: str,
        sample_rate: int,
        channels: int,
    ) -> Dict[str, Any]:
        text = f"[mock-asr] bytes={len(audio_bytes)} format={fmt} sr={sample_rate} ch={channels}"

        duration_ms: Optional[int] = None
        if fmt == "pcm16" and channels > 0 and sample_rate > 0:
            try:
                # bytes per sample = 2 for pcm16; total samples = len(bytes) / (2 * channels)
                total_samples = len(audio_bytes) / (2 * channels)
                seconds = total_samples / sample_rate
                duration_ms = int(seconds * 1000)
            except Exception:
                duration_ms = None

        return {
            "text": text,
            "confidence": 0.5,
            "provider": "mock",
            "durationMs": duration_ms,
        }


class AudioValidationError(Exception):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


_WHISPER_MODEL = None
_WHISPER_MODEL_LOCK = threading.Lock()


def _get_whisper_model():
    global _WHISPER_MODEL

    if _WHISPER_MODEL is not None:
        return _WHISPER_MODEL

    with _WHISPER_MODEL_LOCK:
        if _WHISPER_MODEL is not None:
            return _WHISPER_MODEL

        try:
            from faster_whisper import WhisperModel
        except Exception as e:  # pragma: no cover
            raise NotImplementedError(
                "faster-whisper is not installed; install it and set RECEPAI_STT_PROVIDER=whisper"
            ) from e

        model_name = os.getenv("RECEPAI_WHISPER_MODEL", "base")
        device = os.getenv("RECEPAI_WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("RECEPAI_WHISPER_COMPUTE_TYPE", "int8")

        cpu_threads: Optional[int] = None
        try:
            cpu_threads = int(os.getenv("RECEPAI_WHISPER_CPU_THREADS", ""))
        except Exception:
            cpu_threads = None

        _WHISPER_MODEL = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
        )
        return _WHISPER_MODEL


class FasterWhisperSttBackend(ISttBackend):
    def transcribe(
        self,
        audio_bytes: bytes,
        fmt: str,
        sample_rate: int,
        channels: int,
    ) -> Dict[str, Any]:
        if fmt != "pcm16":
            raise AudioValidationError("Only format 'pcm16' is supported", status_code=400)
        if sample_rate != 16000 or channels != 1:
            raise AudioValidationError("Only 16kHz mono PCM16 is supported (sampleRate=16000, channels=1)")
        if len(audio_bytes) % 2 != 0:
            raise AudioValidationError("Invalid pcm16 payload: byte length must be even")

        try:
            import numpy as np
        except Exception as e:  # pragma: no cover
            raise NotImplementedError("numpy is required for whisper backend") from e

        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_f32 = (audio_int16.astype(np.float32)) / 32768.0

        model = _get_whisper_model()

        language = os.getenv("RECEPAI_WHISPER_LANGUAGE") or None
        vad_filter = os.getenv("RECEPAI_WHISPER_VAD_FILTER", "1") not in ("0", "false", "False")

        segments, info = model.transcribe(
            audio_f32,
            language=language,
            vad_filter=vad_filter,
            beam_size=int(os.getenv("RECEPAI_WHISPER_BEAM_SIZE", "1")),
        )
        text = " ".join((seg.text or "").strip() for seg in segments).strip()

        duration_ms: Optional[int] = None
        try:
            total_samples = len(audio_bytes) / 2
            seconds = total_samples / sample_rate
            duration_ms = int(seconds * 1000)
        except Exception:
            duration_ms = None

        # faster-whisper does not provide a simple overall confidence score.
        confidence: Optional[float] = None
        try:
            confidence = float(getattr(info, "language_probability", None)) if info is not None else None
        except Exception:
            confidence = None

        return {
            "text": text,
            "confidence": confidence,
            "provider": "whisper",
            "durationMs": duration_ms,
        }


def get_backend():
    provider = os.getenv("RECEPAI_STT_PROVIDER", "mock").lower().strip()
    if provider == "mock":
        return MockSttBackend()
    if provider in ("whisper", "faster-whisper"):
        return FasterWhisperSttBackend()
    raise NotImplementedError(f"STT provider '{provider}' not implemented")
