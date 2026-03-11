# Reception AI (Python) — Current Implementation Audit (ASR + LLM/NLU + supporting)

Date: 2026-03-02  
Workspace: `C:\inetpub\wwwroot\RecepAIPython`

## Executive Summary

The Python workstream currently consists of **FastAPI microservices** for ASR and LLM orchestration, plus placeholder RAG and TTS services, and a small shared package for configuration and logging.

- **ASR service** exposes HTTP endpoints for *single-shot transcription* and *chunked session ingestion*, but the transcription backend is currently **mock-only** (`MockSttBackend`).
- **LLM orchestrator** provides a basic non-streaming endpoint (placeholder response) and a production-oriented **NDJSON streaming endpoint** backed by the OpenAI Python SDK (Responses streaming API).
- **Gateway integration** (the .NET VoiceGateway code itself is **not present** in this workspace) is represented by **WebSocket client scripts and phase reports** that define the on-wire WS envelope and the HTTP calls the gateway is expected to make to the Python services.

Net: the repo is **operationally shaped for a microservices gateway + HTTP/WS stack** with observability hooks, but **end-to-end voice intelligence is only partially implemented** (LLM streaming exists; ASR/RAG/TTS are not production-grade yet).

## What the Python project does today

### ASR (Speech-to-Text)

Implemented surface area:
- HTTP health/info/metrics endpoints.
- **Batch** transcription: `POST /stt/transcribe` expecting base64 audio and metadata.
- **Chunked (non-WebSocket) session** ingestion:
  - `POST /stt/session/start`
  - `POST /stt/session/{asrSessionId}/chunk`
  - `POST /stt/session/{asrSessionId}/finalize`

What it *does not* do today (based on code present):
- No real transcription model/provider (only `mock`).
- No diarization.
- No VAD endpoint/pipeline.
- No streaming ASR over WebSocket (only chunked HTTP session ingestion).

Key code:
- API: [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py)
- Session accumulator: [services/asr/recepai_asr_service/sessions.py](../services/asr/recepai_asr_service/sessions.py)
- Backend provider selection: [services/asr/recepai_asr_service/backend.py](../services/asr/recepai_asr_service/backend.py)

### LLM / “NLU”

Implemented surface area:
- HTTP health/info/metrics endpoints.
- Non-streaming turn endpoint: `POST /llm/turn` (returns a hardcoded placeholder response).
- Streaming text endpoint: `POST /llm/turn/stream` that emits **newline-delimited JSON** chunks.

What it *does not* do today (based on code present):
- No intent/slot extraction in Python.
- No prompt templating system in Python.
- No JSON-schema validation of any NLU output in Python.
- No tool/function calling integration to a “VoiceAgent” HTTP endpoint.

Key code:
- Orchestrator: [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py)

### RAG

- Exposes `POST /rag/query` but returns a placeholder answer.
- No vector DB, embeddings, retrieval, or grounding logic.

Key code:
- [services/rag/recepai_rag_service/main.py](../services/rag/recepai_rag_service/main.py)

### TTS

- Exposes `POST /tts/dummy` but does not synthesize audio.

Key code:
- [services/tts/recepai_tts_service/main.py](../services/tts/recepai_tts_service/main.py)

### Streaming vs batch summary

- ASR: batch (`/stt/transcribe`) and chunked-session (`/stt/session/*`).
- LLM: batch placeholder (`/llm/turn`) and **streaming** NDJSON (`/llm/turn/stream`).
- Gateway WS: real-time client ↔ gateway is WS-based; Python services are HTTP-based.

## How it integrates with the .NET VoiceGateway

**Important constraint:** the actual .NET VoiceGateway source code is **not** in this workspace (see [gateway/RecepAI.VoiceGateway/README.md](../gateway/RecepAI.VoiceGateway/README.md)). Integration must therefore be described from:
- Python WS client scripts that encode the WS envelope and expected message types.
- Phase 8 reports describing how the gateway should call the Python services.

### Client ↔ Gateway protocol (WebSocket)

The WS URL assumed by the Python tooling:
- Default gateway URL: `ws://127.0.0.1:5080/ws/voice` (see [scripts/ws_test_client.py](../scripts/ws_test_client.py#L24) and [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1#L2)).

Envelope shape used by the Python clients (camelCase fields):
```json
{
  "type": "<message_type>",
  "sessionId": "...",   // omitted/null in some cases
  "turnId": "...",      // omitted/null in some cases
  "ts": "2026-...Z",
  "payload": { ... }
}
```
See the envelope constructors:
- `make_envelope(...)` in [scripts/ws_test_client.py](../scripts/ws_test_client.py)
- `make_env(...)` in [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py)
- `New-EnvelopeJson` in [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1)

Message types explicitly expected/sent by the clients:
- Initial server message: `server_ready` (non-envelope per PowerShell client comments) — see [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1#L211)
- Client → gateway:
  - `session_start` (see [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1#L249))
  - `user_text` (see [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1#L295))
  - `audio_chunk` (see [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1#L333) and [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py#L143))
- Gateway → client:
  - `session_ack` (see [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1#L269))
  - `final_transcript` + `agent_text` (see [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py#L149))

Audio chunk payload shape (from the audio WS test client):
```json
{
  "sequence": 0,
  "isLast": false,
  "format": "pcm16",
  "sampleRate": 16000,
  "channels": 1,
  "dataBase64": "..."
}
```
See [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py#L139-L141).

### Gateway ↔ Python services protocol (HTTP)

The gateway is expected to call Python services over HTTP and propagate correlation IDs using headers.

Correlation headers implemented on Python services:
- `X-RecepAI-RequestId`
- `X-RecepAI-SessionId`
- `X-RecepAI-TurnId`
- `X-RecepAI-Corr`

Evidence:
- ASR endpoints read these headers in [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py#L94-L97).
- LLM endpoints read these headers in [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L155-L158) and [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L394-L397).

Expected gateway → LLM request shape is documented in the Phase 8 write-up (note: doc is guidance, not code):
- [Reports/phase8/GATEWAY_IMPLEMENTATION_REQUIRED.md](../Reports/phase8/GATEWAY_IMPLEMENTATION_REQUIRED.md)

## What replaced the original AWS/Connect plan in practice

Based on the current workspace contents, the “AWS Connect/Lambda/Bedrock” plan has been replaced by:

- **Local / self-hostable microservices** (FastAPI + Uvicorn) under [services/](../services/).
- A **WebSocket** gateway contract on `ws://127.0.0.1:5080/ws/voice` exercised by [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1) and [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py).
- A **direct OpenAI API integration** for LLM streaming via `openai` Python SDK in [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py).

There is **no AWS SDK usage** and no AWS service-specific implementation visible in this repository’s Python code.

## Project Structure

Top-level:
- [services/asr/recepai_asr_service/](../services/asr/recepai_asr_service/) — ASR HTTP API + session accumulator.
- [services/llm/recepai_llm_orchestrator/](../services/llm/recepai_llm_orchestrator/) — LLM HTTP API + NDJSON streaming.
- [services/rag/recepai_rag_service/](../services/rag/recepai_rag_service/) — placeholder.
- [services/tts/recepai_tts_service/](../services/tts/recepai_tts_service/) — placeholder.
- [shared/python/recepai_shared/](../shared/python/recepai_shared/) — settings + logging + tracing stub.
- [scripts/](../scripts/) — WS clients, probes, smoke test, bootstrap.
- [gateway/RecepAI.VoiceGateway/](../gateway/RecepAI.VoiceGateway/) — **placeholder** .NET gateway folder (no .cs source here).

### Key modules/packages and entrypoints

- ASR FastAPI app: `app` in `recepai_asr_service.main` ([services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py)).
- LLM FastAPI app: `app` in `recepai_llm_orchestrator.main` ([services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py)).
- Shared settings + logger:
  - `settings: VoiceStackSettings` ([shared/python/recepai_shared/src/recepai_shared/config.py](../shared/python/recepai_shared/src/recepai_shared/config.py))
  - `get_logger(...)` and `log_extra(...)` ([shared/python/recepai_shared/src/recepai_shared/logging_utils.py](../shared/python/recepai_shared/src/recepai_shared/logging_utils.py))

### How to run locally

Assumes you are in the repo root and have an activated venv.

Bootstrap (installs `recepai_shared` editable + ASR deps):
- `pwsh scripts/bootstrap_dev.ps1`

Run ASR:
- `pwsh scripts/run_asr.ps1 -Reload`
- or `python -m uvicorn recepai_asr_service.main:app --app-dir services/asr --host 0.0.0.0 --port 5101 --reload`

Run LLM orchestrator:
- `set OPENAI_API_KEY=...`
- `python -m pip install -r services/llm/recepai_llm_orchestrator/requirements.txt`
- `python -m uvicorn recepai_llm_orchestrator.main:app --app-dir services/llm --host 0.0.0.0 --port 5102 --reload`

Run RAG:
- `python -m pip install -r services/rag/recepai_rag_service/requirements.txt`
- `python -m uvicorn recepai_rag_service.main:app --app-dir services/rag --host 0.0.0.0 --port 5104 --reload`

Run TTS:
- `python -m pip install -r services/tts/recepai_tts_service/requirements.txt`
- `python -m uvicorn recepai_tts_service.main:app --app-dir services/tts --host 0.0.0.0 --port 5103 --reload`

Gateway WS protocol validation (requires the gateway to be running separately):
- `pwsh scripts/phase8_smoketest.ps1 -WsUrl "ws://127.0.0.1:5080/ws/voice"`
- Text-only WS probe: `python scripts/ws_test_client.py`
- Audio WS probe: `python scripts/ws_audio_test_client.py --wav scripts/test_mono16k_pcm16_2s.wav`

### Dependencies (major libraries) and versions

From the currently configured workspace venv (Python 3.14.2):
- `fastapi==0.124.4`
- `uvicorn==0.38.0`
- `pydantic==2.12.5` + `pydantic-settings==2.12.0`
- `openai==2.14.0`
- `httpx==0.28.1`
- `prometheus_client==0.23.1`
- `websockets==15.0.1`

Service requirement specs (minimums, not pinned):
- ASR: [services/asr/recepai_asr_service/requirements.txt](../services/asr/recepai_asr_service/requirements.txt)
- LLM: [services/llm/recepai_llm_orchestrator/requirements.txt](../services/llm/recepai_llm_orchestrator/requirements.txt)
- Scripts: [scripts/requirements.txt](../scripts/requirements.txt)

## ASR Pipeline

### Audio input format expectations

**Batch endpoint** (`POST /stt/transcribe`):
- Declares `format`, `sampleRate`, `channels`, and `audioBase64` in the request model (see [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py#L72-L78)).
- Rejects any format other than `pcm16` (see [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py#L104)).

**Chunked session endpoints**:
- `POST /stt/session/start` expects `format/sampleRate/channels` (see [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py#L157-L164)).
- `POST /stt/session/{asrSessionId}/chunk` expects base64 `audioBase64` plus `sequence/isLast` (see [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py#L170-L174)).

**WS audio client expectations (gateway WS, not ASR HTTP)**:
- The test client enforces WAV PCM16 mono 16k input (see [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py#L46)).

### Streaming vs non-streaming mode

- No WS streaming endpoint exists in the ASR service.
- “Streaming” is simulated via **chunked HTTP session ingestion** (`/stt/session/*`).

### Voice activity detection (VAD)

- No VAD implementation is present in the ASR service code.

### Transcription model(s) used

- Current backend is **mock-only** (`RECEPAI_STT_PROVIDER=mock` by default) and returns synthetic text.
- Backend selection is in [services/asr/recepai_asr_service/backend.py](../services/asr/recepai_asr_service/backend.py#L46).

### Latency considerations and performance bottlenecks

ASR service has the scaffolding for latency measurement but not real inference:
- Request histograms are recorded per endpoint (see Prometheus metrics in [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py)).
- Chunked sessions accumulate audio in-memory (`bytearray`) until finalized, bounded by `max_bytes_default` (see [services/asr/recepai_asr_service/sessions.py](../services/asr/recepai_asr_service/sessions.py#L47)).

Expected bottlenecks once a real backend is added:
- Base64 decoding and memory copies (currently done on every request).
- Session accumulation + final inference step.
- Model loading / warm-up time.

## LLM / NLU Layer

### Prompt templates / schema definitions

Python LLM orchestrator does **not** currently load or apply prompt templates.

However, an intent extraction prompt + JSON schema exist under the gateway folder:
- JSON schema: [gateway/RecepAI.VoiceGateway/Actions/Contracts/VoiceIntent.v1.schema.json](../gateway/RecepAI.VoiceGateway/Actions/Contracts/VoiceIntent.v1.schema.json)
- System prompt: [gateway/RecepAI.VoiceGateway/Actions/Prompts/intent_extractor.system.v1.txt](../gateway/RecepAI.VoiceGateway/Actions/Prompts/intent_extractor.system.v1.txt)
- User template: [gateway/RecepAI.VoiceGateway/Actions/Prompts/intent_extractor.user_template.v1.txt](../gateway/RecepAI.VoiceGateway/Actions/Prompts/intent_extractor.user_template.v1.txt)

### Output JSON schema (intent, slots, order items, etc.)

No Python endpoint currently returns an intent/slots JSON object.

The schema that exists in-repo is “VoiceIntent v1” in:
- [gateway/RecepAI.VoiceGateway/Actions/Contracts/VoiceIntent.v1.schema.json](../gateway/RecepAI.VoiceGateway/Actions/Contracts/VoiceIntent.v1.schema.json)

### Determinism controls

- The LLM streaming call uses `AsyncOpenAI(...).responses.stream(model=_MODEL_NAME, input=user_text)` without explicit temperature/seed controls (see [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L257)).
- The code does implement operational “determinism-like” safety controls:
  - Buffer cap: `RECEPAI_LLM_MAX_BUFFER_CHARS` default `200000` (see [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L61)).
  - Stream timeout: `RECEPAI_LLM_STREAM_TIMEOUT_SECONDS` default `120` (see [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L67)).

### Error handling and fallback behavior

Non-streaming `/llm/turn`:
- Returns a fixed placeholder response; no upstream calls.

Streaming `/llm/turn/stream`:
- If the OpenAI stream produces an empty final response, the code raises a `RuntimeError` (see `llm_empty_response` log in [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L344)).
- The NDJSON generator catches exceptions and yields a final error NDJSON object to avoid “response ended prematurely” behavior (see phase report [Reports/phase8/PHASE8B3_LLM_STREAM_FIX.md](../Reports/phase8/PHASE8B3_LLM_STREAM_FIX.md)).

NDJSON success chunk shape (documented in code):
```json
{"text":"...","isFinal":false,"source":"llm"}
```
See the handler docstring in [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L387-L392).

NDJSON error chunk shape (emitted on internal/upstream error):
```json
{"type":"error","code":"llm_stream_error","message":"..."}
```
See [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L589-L596).

## Interfaces & Contracts

### HTTP endpoints (Python services)

ASR service ([services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py)):
- `GET /health`
- `GET /info`
- `GET /metrics`
- `POST /stt/transcribe`
- `POST /stt/session/start`
- `POST /stt/session/{asrSessionId}/chunk`
- `POST /stt/session/{asrSessionId}/finalize`

LLM orchestrator ([services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py)):
- `GET /health`
- `GET /info`
- `GET /metrics`
- `POST /llm/turn`
- `POST /llm/turn/stream` (NDJSON)

RAG service ([services/rag/recepai_rag_service/main.py](../services/rag/recepai_rag_service/main.py)):
- `GET /health`
- `GET /info`
- `POST /rag/query`

TTS service ([services/tts/recepai_tts_service/main.py](../services/tts/recepai_tts_service/main.py)):
- `GET /health`
- `GET /info`
- `POST /tts/dummy`

### WebSocket endpoints

Python does not host WS endpoints in this repo; WS is assumed to be served by the .NET gateway.

The Python repo contains WS clients and probes:
- Text-only: [scripts/ws_test_client.py](../scripts/ws_test_client.py)
- Audio: [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py)
- Minimal: [scripts/ws_min_connect.py](../scripts/ws_min_connect.py)
- Raw handshake probe: [scripts/di_probe_runner.py](../scripts/di_probe_runner.py)
- Validation/smoke test: [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1) and [scripts/phase8_smoketest.ps1](../scripts/phase8_smoketest.ps1)

### Request/response examples (redacted)

ASR `/stt/transcribe` request example:
```json
{
  "sessionId": "s-123",
  "turnId": "t-456",
  "format": "pcm16",
  "sampleRate": 16000,
  "channels": 1,
  "audioBase64": "<base64 pcm16 bytes>"
}
```

LLM `/llm/turn/stream` request example:
```json
{
  "user_text": "Hello! Please suggest 2 menu items."
}
```

LLM `/llm/turn/stream` NDJSON response (example):
```text
{"text":"Sure","isFinal":false,"source":"llm"}
{"text":"...","isFinal":true,"source":"llm"}
```

### Correlation IDs / tracing conventions

- Services prefer correlation headers, fallback to payload (where applicable), and generate a UUID request id if missing.
  - ASR: [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py#L94-L97)
  - LLM: [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L155-L158)
- Logging uses `log_extra(...)` and a safe formatter that appends `requestId/sessionId/turnId/corr/service` when present.
  - [shared/python/recepai_shared/src/recepai_shared/logging_utils.py](../shared/python/recepai_shared/src/recepai_shared/logging_utils.py)
- Distributed tracing is currently a no-op stub (`init_tracer`).
  - [shared/python/recepai_shared/src/recepai_shared/tracing.py](../shared/python/recepai_shared/src/recepai_shared/tracing.py)

## Configuration & Secrets

### Where config lives

`recepai_shared` defines `VoiceStackSettings` using environment variables with prefix `RECEPAI_`:
- [shared/python/recepai_shared/src/recepai_shared/config.py](../shared/python/recepai_shared/src/recepai_shared/config.py)

Service-specific config is primarily via `os.getenv(...)`:
- LLM: `OPENAI_API_KEY`, `RECEPAI_LLM_MODEL`, and stream controls (see [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py)).
- ASR: `RECEPAI_STT_PROVIDER` provider selection (see [services/asr/recepai_asr_service/backend.py](../services/asr/recepai_asr_service/backend.py#L46)).

No `.env` file is present in this workspace. There is an installed `python-dotenv` in the venv, but no code currently loads it.

### Hard-coded values inventory (with file+line references)

This list is intentionally literal: it is only what exists in the repo today.

- Default Redis URL: [shared/python/recepai_shared/src/recepai_shared/config.py](../shared/python/recepai_shared/src/recepai_shared/config.py#L8)
- Default VoiceAgent base URL: [shared/python/recepai_shared/src/recepai_shared/config.py](../shared/python/recepai_shared/src/recepai_shared/config.py#L10)
- Default VoiceAgent API key placeholder (`CHANGE_ME`): [shared/python/recepai_shared/src/recepai_shared/config.py](../shared/python/recepai_shared/src/recepai_shared/config.py#L11)
- LLM default model (`gpt-4o-mini`): [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L51)
- LLM backpressure warning threshold (`2000` ms): [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L55)
- LLM max buffered chars (`200000`): [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L61)
- LLM stream timeout (`120` seconds): [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L67)
- ASR session TTL + max bytes are derived from settings with defaults (TTL=60s, max=5MiB): [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py#L193-L197)
- ASR session store defaults (TTL=60, max=5MiB): [services/asr/recepai_asr_service/sessions.py](../services/asr/recepai_asr_service/sessions.py#L47)
- Default gateway WS URL in client scripts: [scripts/ws_test_client.py](../scripts/ws_test_client.py#L24) and [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py#L18)
- WS audio test client expects WAV 16kHz mono PCM16: [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py#L46) and uses `sampleRate=16000` on the wire: [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py#L139)

### How secrets are stored/loaded (and what should change for production)

Today:
- LLM uses `OPENAI_API_KEY` from environment (validated at import time in [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L28-L35)).
- The shared config includes `voiceagent_api_key` but it is a placeholder default and is not used by any Python code currently.

Recommended production changes (not implemented here):
- Remove placeholder defaults for secrets (`CHANGE_ME`).
- Load secrets from a secret manager (Kubernetes secrets, Azure Key Vault, AWS Secrets Manager, etc.) and inject via env vars.
- Ensure logs never include secret material (current code previews only a masked key prefix).

## Testing & Validation

### Unit tests / integration tests present?

- No `pytest`-style unit test suite is present under `services/*/tests/`.
- The repo relies on **scripts** and **phase reports** as validation artifacts.

Evidence (reporting):
- [Reports/phase8/PHASE8_OBSERVABILITY_VERIFICATION.md](../Reports/phase8/PHASE8_OBSERVABILITY_VERIFICATION.md) mentions unit tests missing.

### How to run validation

LLM stream test:
- Start LLM service (port 5102) and run: `pwsh test_llm_stream.ps1`
  - Script: [test_llm_stream.ps1](../test_llm_stream.ps1)

WS gateway protocol smoke test:
- `pwsh scripts/phase8_smoketest.ps1`
  - Calls [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1)

Audio format sanity scripts:
- Generate a 2s 16kHz PCM16 mono WAV: `python scripts/make_test_wav.py` (see [scripts/make_test_wav.py](../scripts/make_test_wav.py#L4))

### Golden tests for determinism

- No golden/determinism test harness exists in this workspace.

## Operational Readiness

### Logging approach and log fields

- Services use `recepai_shared.get_logger(...)` and structure via `log_extra(...)`.
- Common correlation fields are appended when present: `requestId`, `sessionId`, `turnId`, `corr`, `service`.

Key implementation:
- [shared/python/recepai_shared/src/recepai_shared/logging_utils.py](../shared/python/recepai_shared/src/recepai_shared/logging_utils.py)

### Metrics

- ASR and LLM expose Prometheus-compatible `/metrics` endpoints.
  - ASR: [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py)
  - LLM: [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py)
- RAG/TTS do not expose metrics.

### Docker support

- No Dockerfiles or docker-compose manifests exist in this workspace.

### GPU usage assumptions

- No GPU-specific dependencies or runtime assumptions are present in the code.
- Once a real ASR/TTS model is introduced, GPU usage should be explicitly declared (not implemented today).

## “Done / Partially Done / Not Done Yet”

| Component | Status | Evidence in workspace | Next action |
|---|---:|---|---|
| Gateway WS contract validation tools | Done | [scripts/ws_phase8_client.ps1](../scripts/ws_phase8_client.ps1), [scripts/ws_audio_test_client.py](../scripts/ws_audio_test_client.py) | Keep in sync with gateway repo contract |
| ASR HTTP API surface + session accumulator | Partially Done | [services/asr/recepai_asr_service/main.py](../services/asr/recepai_asr_service/main.py), [services/asr/recepai_asr_service/sessions.py](../services/asr/recepai_asr_service/sessions.py) | Implement a real STT backend + streaming semantics |
| ASR transcription backend | Not Done Yet | `MockSttBackend` only ([services/asr/recepai_asr_service/backend.py](../services/asr/recepai_asr_service/backend.py)) | Add at least one provider (e.g., Whisper, Azure, etc.) |
| LLM non-streaming turn endpoint | Partially Done | `/llm/turn` returns placeholder ([services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L152)) | Implement real orchestration / NLU / tool calls |
| LLM NDJSON streaming endpoint | Done (for text streaming) | `/llm/turn/stream` ([services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py#L386)) | Add prompt/schema controls and robustness tests |
| Intent/slot schema + prompts | Partially Done | Schema/prompt files exist under [gateway/RecepAI.VoiceGateway/Actions/](../gateway/RecepAI.VoiceGateway/Actions/) | Wire into actual runtime (gateway or Python) |
| RAG service | Not Done Yet | Placeholder response ([services/rag/recepai_rag_service/main.py](../services/rag/recepai_rag_service/main.py)) | Implement retrieval + citations/grounding |
| TTS service | Not Done Yet | Placeholder response ([services/tts/recepai_tts_service/main.py](../services/tts/recepai_tts_service/main.py)) | Implement synthesis + audio contract |
| Tracing | Not Done Yet | Stub only ([shared/python/recepai_shared/src/recepai_shared/tracing.py](../shared/python/recepai_shared/src/recepai_shared/tracing.py)) | Add OpenTelemetry + propagate `traceparent` |
