# Phase 7 Observability Runbook

**Last Updated**: January 12, 2026  
**Phase**: 7A–7H (Logging, Metrics, Latency Accounting, Safety Limits)  
**Status**: Production-Safe Additive Changes

---

## 1. Services + Ports + Endpoints

### LLM Orchestrator (Port 5102)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/info` | GET | Service metadata |
| `/llm/turn` | POST | Synchronous LLM turn (placeholder) |
| `/llm/turn/stream` | POST | Streaming LLM turn (NDJSON) |
| `/metrics` | GET | Prometheus metrics |

**Base URL**: `http://localhost:5102`

### ASR Service (Port 5101)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/info` | GET | Service metadata |
| `/stt/transcribe` | POST | One-shot transcription |
| `/stt/session/start` | POST | Start chunked session |
| `/stt/session/{asrSessionId}/chunk` | POST | Add audio chunk |
| `/stt/session/{asrSessionId}/finalize` | POST | Finalize session |
| `/metrics` | GET | Prometheus metrics |

**Base URL**: `http://localhost:5101`

---

## 2. Environment Variables

| Variable | Default | Affects | Notes |
|----------|---------|---------|-------|
| `OPENAI_API_KEY` | *(required)* | LLM service authentication | **NEVER log or print this value.** |
| `RECEPAI_LLM_MODEL` | `gpt-4o-mini` | OpenAI model selection | Low-cardinality metric label |
| `RECEPAI_LOG_LEVEL` | `INFO` | Log verbosity | Standard Python levels (DEBUG, INFO, WARNING, ERROR) |
| `RECEPAI_LLM_MAX_BUFFER_CHARS` | `200000` | In-memory buffer cap for LLM streaming | Prevents unbounded memory growth; triggers `internal_error` if exceeded |
| `RECEPAI_LLM_STREAM_TIMEOUT_SECONDS` | `120` | Wall-clock timeout for `/llm/turn/stream` | Terminates stream with `reason=timeout` if exceeded |
| `RECEPAI_LLM_BACKPRESSURE_WARN_MS` | `2000` | Slow-client detection threshold | Logs `stream_backpressure` warning when yield stalls exceed this |

Security Notice: Do not log secrets. Do not print OPENAI_API_KEY. Avoid logging full inbound payloads. If you need debug logging, redact sensitive fields first.

---

## 3. Metrics Inventory

### LLM Metrics (`/metrics` at port 5102)

| Metric Name | Type | Labels | Meaning |
|-------------|------|--------|---------|
| `recepai_llm_stream_starts_total` | Counter | `model` | Number of `/llm/turn/stream` requests initiated |
| `recepai_llm_stream_cancels_total` | Counter | `reason` | Stream cancellations (typically `client_disconnect`) |
| `recepai_llm_stream_errors_total` | Counter | `type` | Exceptions during streaming (e.g., `RuntimeError`, `TimeoutError`) |
| `recepai_llm_stream_ends_total` | Counter | `model`, `reason` | Stream completions by normalized reason (`success`, `timeout`, `client_disconnect`, `upstream_error`, `internal_error`) |
| `recepai_llm_ttft_ms` | Histogram | `model` | Time to first token (ms) from handler entry |
| `recepai_llm_first_ndjson_ms` | Histogram | `model` | Time from handler entry to first NDJSON write (ms) |
| `recepai_llm_stream_total_ms` | Histogram | `model` | Total stream duration (ms) from entry to finally block |
| `recepai_llm_active_streams` | Gauge | *(none)* | Currently active streaming requests |
| `recepai_llm_delta_chunks_total` | Counter | `model` | Total non-final chunks emitted |

### ASR Metrics (`/metrics` at port 5101)

| Metric Name | Type | Labels | Meaning |
|-------------|------|--------|---------|
| `recepai_asr_requests_total` | Counter | `endpoint`, `status` | Request count per endpoint and HTTP status code |
| `recepai_asr_request_ms` | Histogram | `endpoint` | Request duration (ms) per endpoint |
| `recepai_asr_limits_exceeded_total` | Counter | `type` | Limit violations (e.g., `chunk_too_large`) |
| `recepai_asr_active_sessions` | Gauge | *(none)* | Number of active (non-finalized, non-expired) ASR sessions |

### Key Alert Candidates

1. **`recepai_llm_active_streams > 0` for extended periods** → possible stuck streams or leak
2. **`recepai_llm_stream_ends_total{reason="timeout"}` spikes** → upstream latency or config issue
3. **`recepai_llm_stream_ends_total{reason="internal_error"}` increases** → buffer limits or unexpected failures
4. **`stream_backpressure` warnings in logs** → slow clients or network congestion
5. **`recepai_asr_limits_exceeded_total{type="chunk_too_large"}` increases** → clients exceeding audio size limits
6. **`recepai_asr_active_sessions` stuck high** → session leaks or cleanup failures

---

## 4. Log Markers (LLM Service)

All log lines use the structured formatter with correlation fields appended when present:

```
YYYY-MM-DD HH:MM:SS | LEVEL | logger_name | message | requestId=... sessionId=... turnId=... corr=... service=...
```

### Key Events

| Event | Level | When | Fields |
|-------|-------|------|--------|
| `stream_start` | INFO | `/llm/turn/stream` handler entry | `requestId`, `sessionId`, `turnId`, `corr`, `service` |
| `ttft_ms` | INFO | First token delta emitted | `requestId`, `sessionId`, `turnId`, `corr`, `service`, `ttft_ms` |
| `stream_end` | INFO | Normal completion or error termination | `requestId`, `sessionId`, `turnId`, `corr`, `service`, `reason`, `total_ms`, `ttft_ms`, `first_ndjson_ms`, `delta_chunks`, `is_cancelled=false` |
| `stream_cancel` | INFO | Client disconnect cancellation | `requestId`, `sessionId`, `turnId`, `corr`, `service`, `reason=client_disconnect`, `total_ms`, `ttft_ms`, `first_ndjson_ms`, `delta_chunks`, `is_cancelled=true` |
| `stream_backpressure` | WARNING | Yield stall exceeds threshold | `requestId`, `sessionId`, `turnId`, `corr`, `service`, `model`, `gap_ms`, `delta_chunks_so_far` |
| `stream_buffer_limit_exceeded` | WARNING | Buffered chars exceed `MAX_BUFFER_CHARS` | `requestId`, `sessionId`, `turnId`, `corr`, `service`, `model`, `limit_chars`, `buffered_chars`, `reason=buffer_limit` |
| `stream_timeout` | WARNING | Stream duration exceeds `STREAM_TIMEOUT_SECONDS` | `requestId`, `sessionId`, `turnId`, `corr`, `service`, `model`, `timeout_seconds`, `elapsed_ms`, `reason=timeout` |

### Normalized End Reasons (Low-Cardinality)

- `success` — normal stream completion with final chunk
- `client_disconnect` — client disconnected before completion
- `timeout` — wall-clock timeout exceeded
- `upstream_error` — OpenAI API error
- `internal_error` — buffer limit, RuntimeError, or other internal failure

---

## 5. Smoke Test Checklist

### Prerequisites

- Python 3.10+ with `.venv` activated
- `OPENAI_API_KEY` set in environment (or in launch.json for debugging)
- Dependencies installed: `pip install -r services/llm/recepai_llm_orchestrator/requirements.txt`

### Start Services

**Terminal 1 (ASR)**:
```powershell
cd services/asr/recepai_asr_service
uvicorn main:app --host 0.0.0.0 --port 5101 --reload
```

**Terminal 2 (LLM)**:
```powershell
cd services/llm/recepai_llm_orchestrator
uvicorn main:app --host 0.0.0.0 --port 5102 --reload
```

### Test Commands

#### 1. Health Checks

```powershell
curl http://localhost:5102/health
curl http://localhost:5101/health
```

**Expected**: `{"status":"ok","service":"..."}`

#### 2. Metrics Endpoints

```powershell
curl http://localhost:5102/metrics
curl http://localhost:5101/metrics
```

**Expected**: Prometheus text format with metric names from inventory above.

**Verify**:
- `recepai_llm_active_streams 0.0` (initially)
- `recepai_asr_active_sessions 0.0` (initially)
- Counter baselines at `0.0`

#### 3. LLM Streaming (Success Path)
Use user_text or userText depending on what the service currently parses.
```powershell
curl -X POST http://localhost:5102/llm/turn/stream `
  -H "Content-Type: application/json" `
  -d '{"user_text":"Hello, what is 2+2?","sessionId":"test-sess-001","turnId":"turn-001"}' `
  --no-buffer
```

# Alternative if the handler expects camelCase:
curl -X POST http://localhost:5102/llm/turn/stream `
  -H "Content-Type: application/json" `
  -d '{"userText":"Hello, what is 2+2?","sessionId":"test-sess-001","turnId":"turn-001"}' `
  --no-buffer


**Expected Output** (NDJSON, one object per line):
```json
{"text":"token1","isFinal":false,"source":"llm"}
{"text":"token2","isFinal":false,"source":"llm"}
...
{"text":"Full response text","isFinal":true,"source":"llm"}
```

**Verify Logs** (LLM service terminal):
- `stream_start` with `requestId`, `sessionId=test-sess-001`, `turnId=turn-001`
- `ttft_ms` log with measured latency
- `stream_end` with `reason=success`, `is_cancelled=false`, `delta_chunks>0`

**Verify Metrics** (re-fetch `/metrics`):
- `recepai_llm_stream_starts_total{model="gpt-4o-mini"}` incremented
- `recepai_llm_stream_ends_total{model="gpt-4o-mini",reason="success"}` incremented
- `recepai_llm_ttft_ms_count` incremented

#### 4. Client Disconnect Test (Cancellation Path)

```powershell
# Start stream and press Ctrl+C after 1-2 seconds
curl -X POST http://localhost:5102/llm/turn/stream `
  -H "Content-Type: application/json" `
  -d '{"user_text":"Tell me a very long story","sessionId":"test-sess-002"}' `
  --no-buffer
# Press Ctrl+C after seeing a few chunks
```

**Verify Logs**:
- `stream_start`
- `ttft_ms` (if first token arrived before disconnect)
- `stream_cancel` with `reason=client_disconnect`, `is_cancelled=true`
- **NO** final chunk in NDJSON output

**Verify Metrics**:
- `recepai_llm_stream_cancels_total{reason="client_disconnect"}` incremented
- `recepai_llm_stream_ends_total{model="...",reason="client_disconnect"}` incremented

#### 5. ASR Session Flow
Note: The example audioBase64 below is not valid PCM16 (it’s just a placeholder to test routing). For real transcription, send base64-encoded PCM16 audio bytes.
```powershell
# Start session
$resp = curl -X POST http://localhost:5101/stt/session/start `
  -H "Content-Type: application/json" `
  -d '{"sessionId":"asr-test-001","format":"pcm16","sampleRate":16000,"channels":1}' | ConvertFrom-Json

$asrSessionId = $resp.asrSessionId

# Add chunk
curl -X POST "http://localhost:5101/stt/session/$asrSessionId/chunk" `
  -H "Content-Type: application/json" `
#   -d '{"sequence":0,"isLast":false,"audioBase64":"SGVsbG8="}'
# Placeholder bytes only (NOT real PCM16 audio). Replace with real PCM16 base64 for a true ASR test.
  -d '{"sequence":0,"isLast":false,"audioBase64":"AAAAAA=="}'


# Finalize
curl -X POST "http://localhost:5101/stt/session/$asrSessionId/finalize"
```

**Verify Metrics**:
- `recepai_asr_requests_total{endpoint="/stt/session/start",status="200"}` incremented
- `recepai_asr_active_sessions` increased then decreased (after finalize)

---

## 6. Invariants Checklist (Phase 6/7 Guarantees)

**Must remain true after all Phase 7 changes:**

| Invariant | Verification |
|-----------|--------------|
| **NDJSON schema unchanged** | Every chunk is exactly `{"text":str,"isFinal":bool,"source":"llm"}` — no new fields |
| **One final chunk on success only** | Exactly one `isFinal:true` chunk per successful stream; inspect NDJSON output |
| **No final chunk on client disconnect** | When client disconnects (Ctrl+C), stream terminates with NO `isFinal:true` chunk |
| **No final chunk on timeout/error** | Buffer limit or timeout raises exception; no final chunk emitted |
| **Gateway cancellation supremacy preserved** | LLM service respects `request.is_disconnected()` and cancels stream immediately |
| **No protocol changes** | HTTP POST, NDJSON streaming (`application/x-ndjson`), no WebSockets introduced |
| **Token cadence unchanged** | Deltas still yield immediately (per OpenAI event); no batching or buffering delays added |
| **Streaming still async** | Uses FastAPI `StreamingResponse` with async generator; no blocking I/O introduced |
| **Correlation fields optional** | `sessionId`, `turnId`, `corr` are read from payload if present; logs work without them |
| **Low-cardinality labels** | Metric labels are `model`, `reason`, `endpoint`, `status`, `type` only — NO `requestId`/`sessionId`/`turnId` |

### Phase-Specific Confirmations

- **Phase 7A (Logging)**: Structured logs render correlation extras without `KeyError`
- **Phase 7A.2 (Metrics)**: Prometheus `/metrics` endpoint added; no endpoint behavior changed
- **Phase 7B.1 (Latency)**: Stage timings (`ttft_ms`, `first_ndjson_ms`) tracked; NDJSON unchanged
- **Phase 7B.PY.2 (ASR Gauge)**: `active_sessions` gauge updates at request boundaries; no session semantics changed
- **Phase 7B.PY.3 (Backpressure)**: Log-only slow-client detection; no cadence or output changed
- **Phase 7G.PY1 (Buffer Cap)**: Memory limit enforced by raising exception; no final chunk on limit breach
- **Phase 7G.PY2 (Timeout)**: Timeout enforced by raising exception; normalized as `reason=timeout`

---

## 7. Troubleshooting Guide

### Issue: `recepai_llm_active_streams` stuck > 0

**Symptoms**: Gauge never returns to 0 after streams complete.

**Diagnosis**:
1. Check logs for uncaught exceptions in `ndjson_stream()` finally block.
2. Verify `_LLM_ACTIVE_STREAMS.dec()` is always called (finally block).

**Remediation**: Restart LLM service; investigate exception logs.

---

### Issue: `stream_backpressure` warnings frequent

**Symptoms**: Many `WARNING` logs with `gap_ms > 2000`.

**Diagnosis**:
1. Client network slow or processing backpressure.
2. Check client-side logs for blocking operations.

**Remediation**:
- Increase `RECEPAI_LLM_BACKPRESSURE_WARN_MS` if false positives.
- Investigate client network/processing latency.

---

### Issue: `stream_timeout` or `stream_buffer_limit_exceeded`

**Symptoms**: Streams terminate with `reason=timeout` or `reason=internal_error`.

**Diagnosis**:
1. Check `RECEPAI_LLM_STREAM_TIMEOUT_SECONDS` and `RECEPAI_LLM_MAX_BUFFER_CHARS` settings.
2. Review OpenAI API latency metrics.
3. Inspect log fields: `elapsed_ms`, `buffered_chars`, `limit_chars`.

**Remediation**:
- Increase limits if legitimate use case.
- Investigate upstream latency or prompt complexity.

---

### Issue: No metrics visible at `/metrics`

**Symptoms**: `curl http://localhost:5102/metrics` returns empty or error.

**Diagnosis**:
1. Verify `prometheus-client` package installed.
2. Check service startup logs for import errors.

**Remediation**:
```powershell
pip install prometheus-client>=0.20.0
```

---

## 8. Production Deployment Checklist

- [ ] Set `OPENAI_API_KEY` in secure secret store (Azure Key Vault, AWS Secrets Manager).
- [ ] Configure `RECEPAI_LOG_LEVEL=INFO` (avoid DEBUG in production).
- [ ] Set appropriate `RECEPAI_LLM_STREAM_TIMEOUT_SECONDS` based on expected latency.
- [ ] Set `RECEPAI_LLM_MAX_BUFFER_CHARS` based on memory constraints.
- [ ] Configure Prometheus scrape targets for `:5101/metrics` and `:5102/metrics`.
- [ ] Set up alerting rules for key metrics (active streams, timeout rate, error rate).
- [ ] Enable structured log ingestion (Azure Monitor, CloudWatch, Splunk).
- [ ] Verify log correlation fields (`requestId`, `sessionId`, `turnId`) propagate end-to-end.
- [ ] Test client disconnect handling under load.
- [ ] Validate no secrets appear in logs or metrics.

---

**End of Runbook**
