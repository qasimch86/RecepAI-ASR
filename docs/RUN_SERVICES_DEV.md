# Run Services in Development

This guide shows how to activate the virtual environment and run each microservice locally with Uvicorn.

## Prerequisites
- Python virtual environment created at `.venv` in the repo root.
- Per-service dependencies installed via each service's `requirements.txt`.

## Activate the virtual environment (PowerShell)
```powershell
& .\.venv\Scripts\Activate.ps1
```

## Install dependencies per service (first time or when changed)
```powershell
# ASR
pip install -r services\asr\recepai_asr_service\requirements.txt

# LLM Orchestrator
pip install -r services\llm\recepai_llm_orchestrator\requirements.txt

# TTS
pip install -r services\tts\recepai_tts_service\requirements.txt

# RAG
pip install -r services\rag\recepai_rag_service\requirements.txt
```

Optional environment variables for all services (adjust as needed):
```powershell
$env:RECEPAI_ENVIRONMENT = "dev"
$env:RECEPAI_REGION = "eu-west"
# For LLM service info endpoint
$env:RECEPAI_VOICEAGENT_BASE_URL = "http://localhost:5000"
```

## Run each service (PowerShell)
Note: Run each service from its own folder so Python can import the package module names correctly.

### ASR Service
```powershell
Push-Location services\asr
python -m uvicorn recepai_asr_service.main:app --host 0.0.0.0 --port 5101 --reload
# When done
Pop-Location
```

Alternatively, from the repo root (Windows):
```powershell
scripts\run_asr.ps1 -Reload
```
This runner uses `--app-dir services\asr` so imports work without changing directories.

#### Test /stt/transcribe (non-streaming)
Example using a tiny base64 payload (2 bytes, not real audio, for contract testing):
```powershell
$payload = @{ 
	sessionId = "sess-123"; 
	turnId = "turn-1"; 
	format = "pcm16"; 
	sampleRate = 16000; 
	channels = 1; 
	audioBase64 = "AQID" 
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:5101/stt/transcribe -Method POST -ContentType "application/json" -Body $payload
```
Or with curl:
```powershell
curl -X POST http://localhost:5101/stt/transcribe ^
	-H "Content-Type: application/json" ^
	-d '{
		"sessionId":"sess-123",
		"turnId":"turn-1",
		"format":"pcm16",
		"sampleRate":16000,
		"channels":1,
		"audioBase64":"AQID"
	}'
```
Note: Set `RECEPAI_STT_PROVIDER=mock` (default) to use the mock backend.

#### Curl example (ASR /stt/transcribe)
Run ASR:
```powershell
python -m uvicorn recepai_asr_service.main:app --host 0.0.0.0 --port 5101 --reload
```

Post a tiny base64 payload:
```powershell
curl -X POST http://localhost:5101/stt/transcribe ^
	-H "Content-Type: application/json" ^
	-d '{
		"sessionId":"demo",
		"turnId":"turn-1",
		"format":"pcm16",
		"sampleRate":16000,
		"channels":1,
		"audioBase64":"AAECAw=="
	}'
```
Expected response contains a mock transcript and `provider` of `"mock"`, e.g.:
```json
{
	"text": "[mock-asr] bytes=4 format=pcm16 sr=16000 ch=1",
	"confidence": 0.5,
	"provider": "mock",
	"durationMs": 0
}
```

### Chunked ASR session (Phase 4B)
Start session:
```powershell
curl -X POST http://localhost:5101/stt/session/start ^
	-H "Content-Type: application/json" ^
	-d '{
		"sessionId":"demo",
		"turnId":"turn-1",
		"format":"pcm16",
		"sampleRate":16000,
		"channels":1
	}'
```
Send chunk(s):
```powershell
# Replace <ASR_SESSION_ID> with the returned value
curl -X POST http://localhost:5101/stt/session/<ASR_SESSION_ID>/chunk ^
	-H "Content-Type: application/json" ^
	-d '{
		"sequence":0,
		"isLast":false,
		"audioBase64":"AAECAw=="
	}'
```
Finalize:
```powershell
curl -X POST http://localhost:5101/stt/session/<ASR_SESSION_ID>/finalize
```
Expected responses include deterministic mock partials and a final transcript with `provider` "mock".

### LLM Orchestrator
```powershell
Push-Location services\llm
python -m uvicorn recepai_llm_orchestrator.main:app --host 0.0.0.0 --port 5102 --reload
Pop-Location
```

### TTS Service
```powershell
Push-Location services\tts
python -m uvicorn recepai_tts_service.main:app --host 0.0.0.0 --port 5103 --reload
Pop-Location
```

### RAG Service
```powershell
Push-Location services\rag
python -m uvicorn recepai_rag_service.main:app --host 0.0.0.0 --port 5104 --reload
Pop-Location
```

## Quick checks
- ASR: http://localhost:5101/health
- LLM: http://localhost:5102/health
- TTS: http://localhost:5103/health
- RAG: http://localhost:5104/health

If you prefer, you can set `PYTHONPATH` instead of changing directories, but using `Push-Location`/`Pop-Location` is simplest on Windows.

## Bootstrap (one-time per venv)
Installs the shared package into the virtual environment and ASR requirements so services can import `recepai_shared`.
```powershell
& .\.venv\Scripts\Activate.ps1
scripts\bootstrap_dev.ps1
```

## Testing the VoiceGateway WebSocket endpoint

Prerequisites:
- VoiceGateway running locally at http://localhost:5080 (from Visual Studio).
- Python virtual environment activated for this repo.
- `websockets` library installed:
	```powershell
	& .\.venv\Scripts\Activate.ps1
	pip install -r scripts\requirements.txt
	# or: pip install websockets
	```

How to run:
```powershell
python scripts\ws_test_client.py
```

What to expect:
- A `session_ack` response after sending `session_start`.
- An `agent_text` echo response after sending `user_text`.