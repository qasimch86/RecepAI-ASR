import base64
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from recepai_shared import settings, get_logger
from .sessions import (
    SessionStore,
    SessionNotFound,
    SequenceConflict,
    AlreadyFinalized,
    TooLarge,
)

from .backend import get_backend


app = FastAPI(title="recepai_asr_service", version="0.1.0")
logger = get_logger("recepai_asr_service")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "recepai_asr_service"}


@app.get("/info")
async def info():
    return {
        "service": "recepai_asr_service",
        "environment": settings.environment,
        "region": settings.region,
        "redis_url": settings.redis_url,
    }


class TranscribeRequest(BaseModel):
    sessionId: str
    turnId: Optional[str] = None
    format: str = Field(..., description="Audio format, currently only 'pcm16' supported")
    sampleRate: int = Field(..., gt=0)
    channels: int = Field(..., gt=0)
    audioBase64: str


class TranscribeResponse(BaseModel):
    text: str
    confidence: Optional[float] = None
    provider: str
    durationMs: Optional[int] = None


# backend selection is handled in backend.get_backend()


@app.post("/stt/transcribe", response_model=TranscribeResponse)
async def stt_transcribe(req: TranscribeRequest):
    if req.format != "pcm16":
        raise HTTPException(status_code=400, detail="Only format 'pcm16' is supported in Phase 4")

    # Decode base64
    try:
        audio_bytes = base64.b64decode(req.audioBase64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 in 'audioBase64'")

    logger.debug(
        "Transcribe request received",
        extra={
            "sessionId": req.sessionId,
            "turnId": req.turnId,
            "format": req.format,
            "sampleRate": req.sampleRate,
            "channels": req.channels,
            "bytes": len(audio_bytes),
        },
    )

    try:
        backend = get_backend()
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    result = backend.transcribe(
        audio_bytes=audio_bytes,
        fmt=req.format,
        sample_rate=req.sampleRate,
        channels=req.channels,
    )

    logger.debug("Transcribe response (mock)", extra=result)

    return TranscribeResponse(**result)


# ==== Phase 4B: Chunked (non-WebSocket) ASR session endpoints ====

class SttSessionStartRequest(BaseModel):
    sessionId: str
    turnId: Optional[str] = None
    format: str
    sampleRate: int
    channels: int


class SttSessionStartResponse(BaseModel):
    asrSessionId: str
    expiresInSeconds: int


class SttChunkRequest(BaseModel):
    sequence: int
    isLast: bool
    audioBase64: str


class SttChunkResponse(BaseModel):
    accepted: bool
    partialText: Optional[str] = None
    stability: Optional[float] = None


class SttFinalizeResponse(BaseModel):
    text: str
    confidence: Optional[float] = None
    provider: str
    durationMs: Optional[int] = None


def _get_limits() -> tuple[int, int]:
    ttl = 60
    max_bytes = 5 * 1024 * 1024
    try:
        ttl = int(getattr(settings, "asr_session_ttl_seconds", ttl))
    except Exception:
        pass
    try:
        max_bytes = int(getattr(settings, "asr_max_audio_bytes", max_bytes))
    except Exception:
        pass
    return ttl, max_bytes


ttl, max_bytes = _get_limits()
_store = SessionStore(ttl_seconds=ttl, max_bytes_default=max_bytes)


@app.post("/stt/session/start", response_model=SttSessionStartResponse)
async def stt_session_start(req: SttSessionStartRequest):
    _store.cleanup_expired()
    if req.format != "pcm16":
        raise HTTPException(status_code=400, detail="Only format 'pcm16' is supported")
    try:
        state = _store.start_session(req.sessionId, req.turnId, req.format, req.sampleRate, req.channels)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.debug("ASR session started", extra={"asrSessionId": state.asr_session_id, "ttl": ttl})
    return SttSessionStartResponse(asrSessionId=state.asr_session_id, expiresInSeconds=ttl)


@app.post("/stt/session/{asrSessionId}/chunk", response_model=SttChunkResponse)
async def stt_session_chunk(asrSessionId: str, req: SttChunkRequest):
    _store.cleanup_expired()
    try:
        partial_text, stability = _store.add_chunk(asrSessionId, req.sequence, req.isLast, req.audioBase64)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="ASR session not found or expired")
    except AlreadyFinalized:
        raise HTTPException(status_code=409, detail="ASR session already finalized")
    except SequenceConflict:
        raise HTTPException(status_code=409, detail="Non-monotonic sequence; expected next sequence")
    except TooLarge:
        raise HTTPException(status_code=413, detail="Max audio size exceeded")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid base64 in 'audioBase64'")

    logger.debug("ASR chunk accepted", extra={"asrSessionId": asrSessionId, "sequence": req.sequence, "isLast": req.isLast})
    return SttChunkResponse(accepted=True, partialText=partial_text, stability=stability)


@app.post("/stt/session/{asrSessionId}/finalize", response_model=SttFinalizeResponse)
async def stt_session_finalize(asrSessionId: str):
    _store.cleanup_expired()
    try:
        result = _store.finalize(asrSessionId)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="ASR session not found or expired")
    except AlreadyFinalized:
        raise HTTPException(status_code=409, detail="ASR session already finalized")

    logger.debug("ASR session finalized", extra={"asrSessionId": asrSessionId})
    return SttFinalizeResponse(**result)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("recepai_asr_service.main:app", host="0.0.0.0", port=5101, reload=True)
