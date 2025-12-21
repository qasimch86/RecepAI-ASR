import asyncio
import json
import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from recepai_shared import settings, get_logger
from openai import AsyncOpenAI


app = FastAPI(title="recepai_llm_orchestrator", version="0.1.0")
logger = get_logger("recepai_llm_orchestrator")
_openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_MODEL_NAME = os.getenv("RECEPAI_LLM_MODEL", "gpt-4o-mini")


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


class TurnRequest(BaseModel):
    user_text: str


@app.post("/llm/turn")
async def llm_turn(body: TurnRequest):
    # TODO: Replace with real LLM tool-calling and action planning logic.
    # This is a placeholder for Phase 1 scaffolding only.
    logger.debug("Received user_text for placeholder turn", extra={"len": len(body.user_text)})
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
    session_id: str,
    turn_id: Optional[str],
    user_text: str,
    cancellation_event: asyncio.Event,
) -> AsyncIterator[AgentTextChunk]:
    """Async streaming LLM integration (OpenAI-compatible Responses API).

    Streams token-level deltas and yields them as non-final chunks, then emits
    exactly one final authoritative chunk upon normal completion.
    Cancellation immediately stops streaming and prevents final emission.
    """
    logger.debug(
        "LLM stream start",
        extra={"sessionId": session_id, "turnId": turn_id, "len": len(user_text), "model": _MODEL_NAME},
    )

    full_text_parts: list[str] = []

    try:
        async with _openai_client.responses.stream(model=_MODEL_NAME, input=user_text) as stream:
            async for event in stream:
                if cancellation_event.is_set():
                    logger.debug("LLM stream cancellation observed; aborting")
                    raise asyncio.CancelledError()
                if getattr(event, "type", None) == "response.output_text.delta":
                    token_text = getattr(event, "delta", "")
                    if token_text:
                        full_text_parts.append(token_text)
                        if len(full_text_parts) % 20 == 0:
                            logger.debug("LLM token receipt", extra={"tokens": len(full_text_parts)})
                        yield AgentTextChunk(text=token_text, is_final=False, source="llm")

            final_response = await stream.get_final_response()
            final_text = getattr(final_response, "output_text", None)
            if not final_text:
                final_text = "".join(full_text_parts)
            logger.debug("LLM stream completion", extra={"totalChars": len(final_text)})
            yield AgentTextChunk(text=final_text, is_final=True, source="llm")

    except asyncio.CancelledError:
        logger.debug("LLM stream cancelled (propagating)")
        raise
    except Exception as e:
        logger.error("LLM stream failed", extra={"error": str(e), "model": _MODEL_NAME})
        raise


@app.post("/llm/turn/stream")
async def llm_turn_stream(body: TurnRequest, request: Request):
    """Streams newline-delimited JSON chunks representing agent text.

    Each item has shape: { "text": str, "isFinal": bool, "source": "llm" }
    Exactly one final chunk is emitted. Client disconnect triggers cancellation.
    """
    cancellation_event = asyncio.Event()

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
                    logger.debug(
                        "Client disconnected; cancelling stream",
                        extra={"len": len(body.user_text)},
                    )
                    cancellation_event.set()
                    break
            except Exception:
                # If request state is unavailable, bail out and let normal completion occur.
                break

    monitor_task = asyncio.create_task(monitor_disconnect())

    async def ndjson_stream():
        try:
            async for chunk in stream_llm_text(
                session_id="session-placeholder",
                turn_id=None,
                user_text=body.user_text,
                cancellation_event=cancellation_event,
            ):
                obj = {"text": chunk.text, "isFinal": chunk.is_final, "source": chunk.source}
                yield (json.dumps(obj) + "\n").encode("utf-8")
        finally:
            monitor_task.cancel()

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
