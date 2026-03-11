from __future__ import annotations

import base64
import os
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for _ in range(12):
        if (p / "test_mono16k_pcm16_2s.wav").exists():
            return p
        p = p.parent
    raise FileNotFoundError("Could not locate repo root containing test_mono16k_pcm16_2s.wav")


@pytest.fixture()
def client():
    from recepai_asr_service.main import app

    return TestClient(app)


def test_rejects_non_pcm16(client: TestClient):
    payload = {
        "sessionId": "s1",
        "turnId": "t1",
        "format": "mp3",
        "sampleRate": 16000,
        "channels": 1,
        "audioBase64": base64.b64encode(b"not audio").decode("ascii"),
    }

    r = client.post("/stt/transcribe", json=payload)
    assert r.status_code == 400


def test_transcribe_returns_non_empty_for_test_wav(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    # Force whisper backend with a small model to keep CPU-only runs reasonable.
    monkeypatch.setenv("RECEPAI_STT_PROVIDER", "whisper")
    monkeypatch.setenv("RECEPAI_WHISPER_MODEL", os.getenv("RECEPAI_WHISPER_MODEL", "tiny"))
    monkeypatch.setenv("RECEPAI_WHISPER_DEVICE", os.getenv("RECEPAI_WHISPER_DEVICE", "cpu"))
    monkeypatch.setenv("RECEPAI_WHISPER_COMPUTE_TYPE", os.getenv("RECEPAI_WHISPER_COMPUTE_TYPE", "int8"))

    # Reset cached model between tests/runs.
    import recepai_asr_service.backend as backend

    backend._WHISPER_MODEL = None

    # If the model can't be loaded (no deps / no network to download), skip rather than failing the suite.
    try:
        backend._get_whisper_model()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Whisper model unavailable: {e}")

    wav_path = _find_repo_root() / "test_mono16k_pcm16_2s.wav"
    with wave.open(str(wav_path), "rb") as w:
        channels = w.getnchannels()
        sample_rate = w.getframerate()
        sample_width = w.getsampwidth()
        frames = w.readframes(w.getnframes())

    assert sample_width == 2

    payload = {
        "sessionId": "s1",
        "turnId": "t1",
        "format": "pcm16",
        "sampleRate": sample_rate,
        "channels": channels,
        "audioBase64": base64.b64encode(frames).decode("ascii"),
    }

    r = client.post("/stt/transcribe", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["provider"] == "whisper"
    assert isinstance(data["text"], str)
    assert data["text"].strip() != ""
