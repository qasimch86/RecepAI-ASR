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


def get_backend():
    import os

    provider = os.getenv("RECEPAI_STT_PROVIDER", "mock")
    if provider == "mock":
        return MockSttBackend()
    raise NotImplementedError(f"STT provider '{provider}' not implemented")
