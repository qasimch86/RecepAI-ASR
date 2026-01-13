import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from recepai_shared import settings, get_logger
from recepai_shared.logging_utils import log_extra
from openai import AsyncOpenAI
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

try:
    # Optional: used only to classify upstream vs internal errors.
    from openai import OpenAIError  # type: ignore
except Exception:  # pragma: no cover
    OpenAIError = Exception  # type: ignore


app = FastAPI(title="recepai_llm_orchestrator", version="0.1.0")
logger = get_logger("recepai_llm_orchestrator")
_openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_MODEL_NAME = os.getenv("RECEPAI_LLM_MODEL", "gpt-4o-mini")

_BACKPRESSURE_WARN_MS = 2000
try:
    _BACKPRESSURE_WARN_MS = int(os.getenv("RECEPAI_LLM_BACKPRESSURE_WARN_MS", "2000"))
except Exception:
    _BACKPRESSURE_WARN_MS = 2000

_MAX_BUFFER_CHARS = 200000
try:
    _MAX_BUFFER_CHARS = int(os.getenv("RECEPAI_LLM_MAX_BUFFER_CHARS", "200000"))
except Exception:
    _MAX_BUFFER_CHARS = 200000

_STREAM_TIMEOUT_SECONDS = 120
try:
    _STREAM_TIMEOUT_SECONDS = int(os.getenv("RECEPAI_LLM_STREAM_TIMEOUT_SECONDS", "120"))
except Exception:
    _STREAM_TIMEOUT_SECONDS = 120


# === Metrics (Prometheus) ===

_LLM_STREAM_STARTS_TOTAL = Counter(
    "recepai_llm_stream_starts_total",
    "Number of LLM stream requests started",
    ["model"],
)

_LLM_STREAM_CANCELS_TOTAL = Counter(
    "recepai_llm_stream_cancels_total",
    "Number of LLM stream cancellations",
    ["reason"],
)

_LLM_STREAM_ERRORS_TOTAL = Counter(
    "recepai_llm_stream_errors_total",
    "Number of LLM stream errors",
    ["type"],
)

_LLM_TTFT_MS = Histogram(
    "recepai_llm_ttft_ms",
    "Time to first token (ms) for LLM streaming",
    ["model"],
)

_LLM_STREAM_TOTAL_MS = Histogram(
    "recepai_llm_stream_total_ms",
    "Total stream duration (ms) for LLM streaming",
    ["model"],
)

_LLM_FIRST_NDJSON_MS = Histogram(
    "recepai_llm_first_ndjson_ms",
    "Time from stream handler entry to first NDJSON write (ms)",
    ["model"],
)

_LLM_ACTIVE_STREAMS = Gauge(
    "recepai_llm_active_streams",
    "Number of currently active LLM streams",
)

_LLM_DELTA_CHUNKS_TOTAL = Counter(
    "recepai_llm_delta_chunks_total",
    "Number of delta chunks emitted by LLM streaming",
    ["model"],
)

_LLM_STREAM_ENDS_TOTAL = Counter(
    "recepai_llm_stream_ends_total",
    "Number of LLM stream ends by normalized reason",
    ["model", "reason"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "recepai_llm_orchestrator"}


@app.get("/info")
async def info():
    return {
        "service": "recepai_llm_orchestrator",
        "environment": settings.environment,
        "region": settings.region,
        "voiceagent_base_url": settings.voiceagent_base_url,
    }


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


class TurnRequest(BaseModel):
    user_text: str


@app.post("/llm/turn")
async def llm_turn(body: TurnRequest, request: Request):
    request_id = str(uuid.uuid4())
    # TODO: Replace with real LLM tool-calling and action planning logic.
    # This is a placeholder for Phase 1 scaffolding only.

    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            session_id = raw.get("sessionId")
            turn_id = raw.get("turnId")
    except Exception:
        pass

    logger.debug(
        "Received user_text for placeholder turn",
        extra=log_extra(
            requestId=request_id,
            sessionId=session_id,
            turnId=turn_id,
            service="recepai_llm_orchestrator",
            len=len(body.user_text),
        ),
    )
    return {
        "agentText": "This is a placeholder response.",
        "actions": [],
    }


# === Phase-6F additive streaming surface (deterministic placeholder) ===

@dataclass
class AgentTextChunk:
    text: str
    is_final: bool
    source: str


async def stream_llm_text(
    request_id: str,
    session_id: str,
    turn_id: Optional[str],
    user_text: str,
    cancellation_event: asyncio.Event,
    timings: dict[str, float],
) -> AsyncIterator[AgentTextChunk]:
    """Async streaming LLM integration (OpenAI-compatible Responses API).

    Streams token-level deltas and yields them as non-final chunks, then emits
    exactly one final authoritative chunk upon normal completion.
    Cancellation immediately stops streaming and prevents final emission.
    """
    logger.debug(
        "LLM stream start",
        extra=log_extra(
            requestId=request_id,
            sessionId=session_id,
            turnId=turn_id,
            service="recepai_llm_orchestrator",
            len=len(user_text),
            model=_MODEL_NAME,
        ),
    )

    full_text_parts: list[str] = []
    buffered_chars = 0
    t_start_monotonic = time.monotonic()

    try:
        timings["t_openai_stream_start"] = time.perf_counter()
        async with _openai_client.responses.stream(model=_MODEL_NAME, input=user_text) as stream:
            async for event in stream:
                # Check overall stream timeout
                elapsed_seconds = time.monotonic() - t_start_monotonic
                if elapsed_seconds > _STREAM_TIMEOUT_SECONDS:
                    elapsed_ms = int(elapsed_seconds * 1000)
                    logger.warning(
                        "stream_timeout",
                        extra=log_extra(
                            requestId=request_id,
                            sessionId=session_id,
                            turnId=turn_id,
                            corr=None,
                            service="recepai_llm_orchestrator",
                            model=_MODEL_NAME,
                            timeout_seconds=_STREAM_TIMEOUT_SECONDS,
                            elapsed_ms=elapsed_ms,
                            reason="timeout",
                        ),
                    )
                    raise TimeoutError(f"LLM stream timeout: {_STREAM_TIMEOUT_SECONDS}s exceeded")
                if cancellation_event.is_set():
                    logger.debug(
                        "LLM stream cancellation observed; aborting",
                        extra=log_extra(requestId=request_id, sessionId=session_id, turnId=turn_id, service="recepai_llm_orchestrator"),
                    )
                    raise asyncio.CancelledError()
                if getattr(event, "type", None) == "response.output_text.delta":
                    token_text = getattr(event, "delta", "")
                    if token_text:
                        # Enforce memory cap before appending
                        if buffered_chars + len(token_text) > _MAX_BUFFER_CHARS:
                            logger.warning(
                                "stream_buffer_limit_exceeded",
                                extra=log_extra(
                                    requestId=request_id,
                                    sessionId=session_id,
                                    turnId=turn_id,
                                    corr=None,
                                    service="recepai_llm_orchestrator",
                                    model=_MODEL_NAME,
                                    limit_chars=_MAX_BUFFER_CHARS,
                                    buffered_chars=buffered_chars,
                                    reason="buffer_limit",
                                ),
                            )
                            raise RuntimeError(f"LLM buffer limit exceeded: {_MAX_BUFFER_CHARS} chars")
                        full_text_parts.append(token_text)
                        buffered_chars += len(token_text)
                        if len(full_text_parts) % 20 == 0:
                            logger.debug(
                                "LLM token receipt",
                                extra=log_extra(
                                    requestId=request_id,
                                    sessionId=session_id,
                                    turnId=turn_id,
                                    service="recepai_llm_orchestrator",
                                    tokens=len(full_text_parts),
                                ),
                            )
                        yield AgentTextChunk(text=token_text, is_final=False, source="llm")

            final_response = await stream.get_final_response()
            final_text = getattr(final_response, "output_text", None)
            if not final_text:
                final_text = "".join(full_text_parts)
            logger.debug(
                "LLM stream completion",
                extra=log_extra(
                    requestId=request_id,
                    sessionId=session_id,
                    turnId=turn_id,
                    service="recepai_llm_orchestrator",
                    totalChars=len(final_text),
                ),
            )
            yield AgentTextChunk(text=final_text, is_final=True, source="llm")

    except asyncio.CancelledError:
        logger.debug(
            "LLM stream cancelled (propagating)",
            extra=log_extra(requestId=request_id, sessionId=session_id, turnId=turn_id, service="recepai_llm_orchestrator"),
        )
        raise
    except Exception as e:
        type_name = type(e).__name__ or "Exception"
        _LLM_STREAM_ERRORS_TOTAL.labels(type=type_name).inc()
        logger.error(
            "LLM stream failed",
            extra=log_extra(
                requestId=request_id,
                sessionId=session_id,
                turnId=turn_id,
                service="recepai_llm_orchestrator",
                error=str(e),
                model=_MODEL_NAME,
            ),
        )
        raise


@app.post("/llm/turn/stream")
async def llm_turn_stream(body: TurnRequest, request: Request):
    """Streams newline-delimited JSON chunks representing agent text.

    Each item has shape: { "text": str, "isFinal": bool, "source": "llm" }
    Exactly one final chunk is emitted. Client disconnect triggers cancellation.
    """
    request_id = str(uuid.uuid4())
    cancellation_event = asyncio.Event()

    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    corr: Optional[str] = None
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            session_id = raw.get("sessionId")
            turn_id = raw.get("turnId")
            corr = raw.get("corr") or raw.get("correlationId")
    except Exception:
        pass

    # Preserve existing placeholder behavior if sessionId/turnId are not provided.
    effective_session_id = session_id or "session-placeholder"

    timings: dict[str, float] = {}
    t_stream_enter = time.perf_counter()
    timings["t_stream_enter"] = t_stream_enter

    first_delta_logged = False
    delta_chunks = 0
    end_reason: Optional[str] = None
    ttft_ms_value: Optional[int] = None
    first_ndjson_ms_value: Optional[int] = None

    _LLM_STREAM_STARTS_TOTAL.labels(model=_MODEL_NAME).inc()

    logger.info(
        "stream_start",
        extra=log_extra(
            requestId=request_id,
            sessionId=session_id,
            turnId=turn_id,
            corr=corr,
            service="recepai_llm_orchestrator",
        ),
    )

    async def monitor_disconnect():
        # Cooperatively watch for client disconnect and signal cancellation.
        while not cancellation_event.is_set():
            await asyncio.sleep(0.2)
            try:
                res = request.is_disconnected()
                if asyncio.iscoroutine(res):
                    disconnected = await res
                else:
                    disconnected = bool(res)
                if disconnected:
                    nonlocal end_reason
                    end_reason = "client_disconnect"
                    _LLM_STREAM_CANCELS_TOTAL.labels(reason="client_disconnect").inc()
                    cancellation_event.set()
                    break
            except Exception:
                # If request state is unavailable, bail out and let normal completion occur.
                break

    monitor_task = asyncio.create_task(monitor_disconnect())

    async def ndjson_stream():
        _LLM_ACTIVE_STREAMS.inc()
        try:
            async for chunk in stream_llm_text(
                request_id=request_id,
                session_id=effective_session_id,
                turn_id=turn_id,
                user_text=body.user_text,
                cancellation_event=cancellation_event,
                timings=timings,
            ):
                if "t_first_ndjson_write" not in timings:
                    timings["t_first_ndjson_write"] = time.perf_counter()
                    first_ndjson_ms_value_local = int((timings["t_first_ndjson_write"] - t_stream_enter) * 1000)
                    nonlocal first_ndjson_ms_value
                    first_ndjson_ms_value = first_ndjson_ms_value_local
                    _LLM_FIRST_NDJSON_MS.labels(model=_MODEL_NAME).observe(first_ndjson_ms_value_local)

                if not chunk.is_final:
                    delta_chunks += 1
                    _LLM_DELTA_CHUNKS_TOTAL.labels(model=_MODEL_NAME).inc()
                    if not first_delta_logged:
                        first_delta_logged = True
                        t_first_token_delta = time.perf_counter()
                        timings["t_first_token_delta"] = t_first_token_delta
                        ttft_ms = int((t_first_token_delta - t_stream_enter) * 1000)
                        nonlocal ttft_ms_value
                        ttft_ms_value = ttft_ms
                        _LLM_TTFT_MS.labels(model=_MODEL_NAME).observe(ttft_ms)
                        logger.info(
                            "ttft_ms",
                            extra=log_extra(
                                requestId=request_id,
                                sessionId=session_id,
                                turnId=turn_id,
                                corr=corr,
                                service="recepai_llm_orchestrator",
                                ttft_ms=ttft_ms,
                            ),
                        )
                obj = {"text": chunk.text, "isFinal": chunk.is_final, "source": chunk.source}

                # Backpressure proxy: measure time until the generator is resumed
                # after yielding a chunk. This is log-only and does not alter output.
                t_before_yield = time.perf_counter()
                yield (json.dumps(obj) + "\n").encode("utf-8")
                gap_ms = int((time.perf_counter() - t_before_yield) * 1000)
                if gap_ms >= _BACKPRESSURE_WARN_MS:
                    logger.warning(
                        f"stream_backpressure model={_MODEL_NAME} gap_ms={gap_ms} delta_chunks_so_far={delta_chunks}",
                        extra=log_extra(
                            requestId=request_id,
                            sessionId=session_id,
                            turnId=turn_id,
                            corr=corr,
                            service="recepai_llm_orchestrator",
                        ),
                    )
            if end_reason is None:
                end_reason = "success"
        except asyncio.CancelledError:
            # Cancellation semantics: no final chunk on cancellation.
            if end_reason is None and cancellation_event.is_set():
                end_reason = "client_disconnect"
            raise
        except Exception as e:
            if end_reason is None:
                if isinstance(e, TimeoutError):
                    end_reason = "timeout"
                elif OpenAIError is not Exception and isinstance(e, OpenAIError):
                    end_reason = "upstream_error"
                else:
                    end_reason = "internal_error"
            raise
        finally:
            monitor_task.cancel()
            timings["t_stream_end"] = time.perf_counter()
            total_ms = int((timings["t_stream_end"] - t_stream_enter) * 1000)
            _LLM_STREAM_TOTAL_MS.labels(model=_MODEL_NAME).observe(total_ms)
            _LLM_ACTIVE_STREAMS.dec()

            normalized_reason = end_reason or "internal_error"
            _LLM_STREAM_ENDS_TOTAL.labels(model=_MODEL_NAME, reason=normalized_reason).inc()

            is_cancelled = normalized_reason == "client_disconnect"
            end_event = "stream_cancel" if is_cancelled else "stream_end"
            logger.info(
                end_event,
                extra=log_extra(
                    requestId=request_id,
                    sessionId=session_id,
                    turnId=turn_id,
                    corr=corr,
                    service="recepai_llm_orchestrator",
                    reason=normalized_reason,
                    total_ms=total_ms,
                    ttft_ms=ttft_ms_value,
                    first_ndjson_ms=first_ndjson_ms_value,
                    delta_chunks=delta_chunks,
                    is_cancelled=is_cancelled,
                ),
            )

    return StreamingResponse(ndjson_stream(), media_type="application/x-ndjson")


if __name__ == "__main__":
    # Development runner
    import uvicorn

    uvicorn.run(
        "recepai_llm_orchestrator.main:app",
        host="0.0.0.0",
        port=5102,
        reload=True,
    )
