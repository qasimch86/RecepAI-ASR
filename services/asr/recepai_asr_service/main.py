import base64
import time
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from recepai_shared import settings, get_logger
from recepai_shared.logging_utils import log_extra
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from .sessions import (
    SessionStore,
    SessionNotFound,
    SequenceConflict,
    AlreadyFinalized,
    TooLarge,
)

from .backend import get_backend, AudioValidationError


app = FastAPI(title="recepai_asr_service", version="0.1.0")
logger = get_logger("recepai_asr_service")


# === Metrics (Prometheus) ===

_ASR_REQUESTS_TOTAL = Counter(
    "recepai_asr_requests_total",
    "Number of ASR requests",
    ["endpoint", "status"],
)

_ASR_REQUEST_MS = Histogram(
    "recepai_asr_request_ms",
    "ASR request duration (ms)",
    ["endpoint"],
)

_ASR_LIMITS_EXCEEDED_TOTAL = Counter(
    "recepai_asr_limits_exceeded_total",
    "Number of ASR limit exceed events",
    ["type"],
)

_ASR_ACTIVE_SESSIONS = Gauge(
    "recepai_asr_active_sessions",
    "Number of active ASR sessions in this process",
)


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


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
async def stt_transcribe(req: TranscribeRequest, request: Request):
    # Correlation fields: prefer headers, fallback to payload, generate requestId if absent
    request_id = request.headers.get("X-RecepAI-RequestId") or str(uuid.uuid4())
    session_id: Optional[str] = request.headers.get("X-RecepAI-SessionId") or req.sessionId
    turn_id: Optional[str] = request.headers.get("X-RecepAI-TurnId") or req.turnId
    corr: Optional[str] = request.headers.get("X-RecepAI-Corr")

    endpoint = "/stt/transcribe"
    started = time.perf_counter()
    status = "200"
    try:
        if req.format != "pcm16":
            raise HTTPException(status_code=400, detail="Only format 'pcm16' is supported in Phase 4")

        if req.sampleRate != 16000 or req.channels != 1:
            raise HTTPException(
                status_code=422,
                detail="Only 16kHz mono PCM16 is supported (sampleRate=16000, channels=1)",
            )

        # Decode base64
        try:
            audio_bytes = base64.b64decode(req.audioBase64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 in 'audioBase64'")

        logger.debug(
            "Transcribe request received",
            extra=log_extra(
                requestId=request_id,
                sessionId=session_id,
                turnId=turn_id,
                corr=corr,
                service="recepai_asr_service",
                format=req.format,
                sampleRate=req.sampleRate,
                channels=req.channels,
                bytes=len(audio_bytes),
            ),
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

        logger.debug("Transcribe response", extra=result)

        return TranscribeResponse(**result)
    except AudioValidationError as e:
        status = str(e.status_code)
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except HTTPException as e:
        status = str(e.status_code)
        raise
    except Exception:
        status = "500"
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        _ASR_REQUESTS_TOTAL.labels(endpoint=endpoint, status=status).inc()
        _ASR_REQUEST_MS.labels(endpoint=endpoint).observe(elapsed_ms)
        _ASR_ACTIVE_SESSIONS.set(_store.active_session_count())


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
async def stt_session_start(req: SttSessionStartRequest, request: Request):
    # Correlation fields: prefer headers, fallback to payload, generate requestId if absent
    request_id = request.headers.get("X-RecepAI-RequestId") or str(uuid.uuid4())
    session_id: Optional[str] = request.headers.get("X-RecepAI-SessionId") or req.sessionId
    turn_id: Optional[str] = request.headers.get("X-RecepAI-TurnId") or req.turnId
    corr: Optional[str] = request.headers.get("X-RecepAI-Corr")

    endpoint = "/stt/session/start"
    started = time.perf_counter()
    status = "200"
    _store.cleanup_expired()
    try:
        if req.format != "pcm16":
            raise HTTPException(status_code=400, detail="Only format 'pcm16' is supported")

        if req.sampleRate != 16000 or req.channels != 1:
            raise HTTPException(
                status_code=422,
                detail="Only 16kHz mono PCM16 is supported (sampleRate=16000, channels=1)",
            )
        try:
            state = _store.start_session(req.sessionId, req.turnId, req.format, req.sampleRate, req.channels)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        logger.debug(
            "ASR session started",
            extra=log_extra(
                requestId=request_id,
                sessionId=session_id,
                turnId=turn_id,
                corr=corr,
                service="recepai_asr_service",
                asrSessionId=state.asr_session_id,
                ttl=ttl,
            ),
        )
        return SttSessionStartResponse(asrSessionId=state.asr_session_id, expiresInSeconds=ttl)
    except HTTPException as e:
        status = str(e.status_code)
        raise
    except Exception:
        status = "500"
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        _ASR_REQUESTS_TOTAL.labels(endpoint=endpoint, status=status).inc()
        _ASR_REQUEST_MS.labels(endpoint=endpoint).observe(elapsed_ms)
        _ASR_ACTIVE_SESSIONS.set(_store.active_session_count())


@app.post("/stt/session/{asrSessionId}/chunk", response_model=SttChunkResponse)
async def stt_session_chunk(asrSessionId: str, req: SttChunkRequest, request: Request):
    # Correlation fields: prefer headers, generate requestId if absent
    request_id = request.headers.get("X-RecepAI-RequestId") or str(uuid.uuid4())
    corr: Optional[str] = request.headers.get("X-RecepAI-Corr")

    endpoint = "/stt/session/{asrSessionId}/chunk"
    started = time.perf_counter()
    status = "200"
    _store.cleanup_expired()
    try:
        try:
            partial_text, stability = _store.add_chunk(asrSessionId, req.sequence, req.isLast, req.audioBase64)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="ASR session not found or expired")
        except AlreadyFinalized:
            raise HTTPException(status_code=409, detail="ASR session already finalized")
        except SequenceConflict:
            raise HTTPException(status_code=409, detail="Non-monotonic sequence; expected next sequence")
        except TooLarge:
            _ASR_LIMITS_EXCEEDED_TOTAL.labels(type="chunk_too_large").inc()
            raise HTTPException(status_code=413, detail="Max audio size exceeded")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid base64 in 'audioBase64'")

        logger.debug(
            "ASR chunk accepted",
            extra=log_extra(
                requestId=request_id,
                corr=corr,
                service="recepai_asr_service",
                asrSessionId=asrSessionId,
                sequence=req.sequence,
                isLast=req.isLast,
            ),
        )
        return SttChunkResponse(accepted=True, partialText=partial_text, stability=stability)
    except HTTPException as e:
        status = str(e.status_code)
        raise
    except Exception:
        status = "500"
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        _ASR_REQUESTS_TOTAL.labels(endpoint=endpoint, status=status).inc()
        _ASR_REQUEST_MS.labels(endpoint=endpoint).observe(elapsed_ms)
        _ASR_ACTIVE_SESSIONS.set(_store.active_session_count())


@app.post("/stt/session/{asrSessionId}/finalize", response_model=SttFinalizeResponse)
async def stt_session_finalize(asrSessionId: str, request: Request):
    # Correlation fields: prefer headers, generate requestId if absent
    request_id = request.headers.get("X-RecepAI-RequestId") or str(uuid.uuid4())
    corr: Optional[str] = request.headers.get("X-RecepAI-Corr")

    endpoint = "/stt/session/{asrSessionId}/finalize"
    started = time.perf_counter()
    status = "200"
    _store.cleanup_expired()
    try:
        try:
            audio_bytes, fmt, sample_rate, channels, chunk_count = _store.finalize(asrSessionId)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="ASR session not found or expired")
        except AlreadyFinalized:
            raise HTTPException(status_code=409, detail="ASR session already finalized")

        try:
            backend = get_backend()
        except NotImplementedError as e:
            raise HTTPException(status_code=501, detail=str(e))

        try:
            result = backend.transcribe(
                audio_bytes=audio_bytes,
                fmt=fmt,
                sample_rate=sample_rate,
                channels=channels,
            )
        except AudioValidationError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail)

        logger.debug(
            "ASR session finalized",
            extra=log_extra(
                requestId=request_id,
                corr=corr,
                service="recepai_asr_service",
                asrSessionId=asrSessionId,
                chunks=chunk_count,
            ),
        )
        return SttFinalizeResponse(**result)
    except HTTPException as e:
        status = str(e.status_code)
        raise
    except Exception:
        status = "500"
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        _ASR_REQUESTS_TOTAL.labels(endpoint=endpoint, status=status).inc()
        _ASR_REQUEST_MS.labels(endpoint=endpoint).observe(elapsed_ms)
        _ASR_ACTIVE_SESSIONS.set(_store.active_session_count())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("recepai_asr_service.main:app", host="0.0.0.0", port=5101, reload=True)
