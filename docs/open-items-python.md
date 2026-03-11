# Reception AI (Python) — Open Items (Prioritized)

Date: 2026-03-02

This TODO list is derived strictly from what exists (and is missing) in `C:\inetpub\wwwroot\RecepAIPython`.

## P0 (must-fix for functional end-to-end voice)

### P0.1 Implement a real ASR backend (replace mock)
- **Estimate:** L
- **Why:** ASR currently returns mock transcripts only.
- **Evidence:** Provider selection defaults to `mock` in [services/asr/recepai_asr_service/backend.py](../services/asr/recepai_asr_service/backend.py#L46).
- **Next actions:**
  - Add a concrete `ISttBackend` implementation (e.g., Whisper/faster-whisper, Azure Speech, etc.).
  - Define a production audio contract (sample rate/channels) and enforce resampling or reject.
  - Add model warm-up + caching strategy.

### P0.2 Define and enforce gateway → Python contract (request casing + validation)
- **Estimate:** M
- **Why:** Phase reports show gateway can mis-send payload shape leading to 422/empty agent text failure modes.
- **Evidence:** Guidance doc [Reports/phase8/GATEWAY_IMPLEMENTATION_REQUIRED.md](../Reports/phase8/GATEWAY_IMPLEMENTATION_REQUIRED.md).
- **Next actions:**
  - In Python, keep request models stable and explicitly document expected JSON.
  - In gateway, ensure JSON body matches `TurnRequest` shape (`user_text`) and propagate correlation headers.
  - Add an integration test (HTTP) that the gateway contract uses the same casing.

### P0.3 Add basic automated tests for the two “real” services (ASR+LLM)
- **Estimate:** M
- **Why:** There is no unit/integration test suite in `services/*` today.
- **Evidence:** Phase report notes missing tests in [Reports/phase8/PHASE8_OBSERVABILITY_VERIFICATION.md](../Reports/phase8/PHASE8_OBSERVABILITY_VERIFICATION.md).
- **Next actions:**
  - Add `pytest` + `httpx.AsyncClient` tests for:
    - ASR `/stt/transcribe` rejects non-`pcm16`, rejects invalid base64.
    - ASR session sequencing (`SequenceConflict`) and size limit (`TooLarge`).
    - LLM `/llm/turn/stream` always yields NDJSON (including an error object on failure).

## P1 (production hardening)

### P1.1 Secrets hygiene: remove placeholder defaults and document required env vars
- **Estimate:** S
- **Why:** Shared config includes `voiceagent_api_key` default `CHANGE_ME`.
- **Evidence:** [shared/python/recepai_shared/src/recepai_shared/config.py](../shared/python/recepai_shared/src/recepai_shared/config.py#L11).
- **Next actions:**
  - Remove unsafe defaults for secrets.
  - Document required env vars per service (`OPENAI_API_KEY`, etc.).

### P1.2 Add OpenTelemetry tracing (or remove stub until ready)
- **Estimate:** M
- **Why:** Tracing is a no-op stub today.
- **Evidence:** [shared/python/recepai_shared/src/recepai_shared/tracing.py](../shared/python/recepai_shared/src/recepai_shared/tracing.py).
- **Next actions:**
  - Implement OTLP exporter wiring.
  - Standardize correlation fields (`corr` vs `traceparent`) across services.

### P1.3 Implement real NLU (intent+slots) using the existing schema/prompt assets
- **Estimate:** M
- **Why:** The schema and prompt exist, but are not used by Python runtime.
- **Evidence:** Schema [gateway/RecepAI.VoiceGateway/Actions/Contracts/VoiceIntent.v1.schema.json](../gateway/RecepAI.VoiceGateway/Actions/Contracts/VoiceIntent.v1.schema.json).
- **Next actions:**
  - Decide ownership: gateway (.NET) vs orchestrator (Python).
  - Add schema validation and deterministic failure paths.

### P1.4 Add Docker/Kubernetes runnable artifacts for Python services
- **Estimate:** M
- **Why:** No Dockerfiles exist; infra folder is mostly placeholders.
- **Evidence:** no `Dockerfile` present in repo.
- **Next actions:**
  - Add per-service Dockerfiles and a minimal compose (dev only).
  - Ensure `/health` and `/metrics` are wired for probes.

## P2 (feature completeness)

### P2.1 Implement RAG retrieval pipeline
- **Estimate:** L
- **Why:** RAG is a placeholder.
- **Evidence:** [services/rag/recepai_rag_service/main.py](../services/rag/recepai_rag_service/main.py).
- **Next actions:**
  - Add embeddings + vector store + retrieval.
  - Define grounding/citation format.

### P2.2 Implement TTS synthesis + audio contract
- **Estimate:** L
- **Why:** TTS returns a placeholder message; no audio output.
- **Evidence:** [services/tts/recepai_tts_service/main.py](../services/tts/recepai_tts_service/main.py).
- **Next actions:**
  - Pick a TTS engine and define output encoding (WAV/PCM/Opus).
  - Add streaming vs batch decision.

### P2.3 Improve local dev ergonomics (one-command start)
- **Estimate:** S
- **Why:** Only `scripts/run_asr.ps1` exists; other services require manual uvicorn commands.
- **Evidence:** [scripts/run_asr.ps1](../scripts/run_asr.ps1).
- **Next actions:**
  - Add `scripts/run_llm.ps1`, `scripts/run_rag.ps1`, `scripts/run_tts.ps1`, or a single orchestrator script.
