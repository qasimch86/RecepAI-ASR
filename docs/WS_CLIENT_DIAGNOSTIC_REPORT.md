# WebSocket Client Diagnostic Report

This document explains how to run `scripts/ws_test_client.py`, shows expected outputs for a healthy handshake, and how to interpret the evidence when diagnosing connection timeouts.

## How To Run

- Ensure Python is available and install dependencies:

```bash
python -m pip install websockets
```

- Optional: set a custom gateway URL (defaults to `ws://localhost:5080/ws/voice`):

```bash
set RECEPAI_GATEWAY_WS_URL=ws://localhost:5080/ws/voice
```

- Run the client from the repo root:

```bash
python scripts/ws_test_client.py
```

## What The Script Prints

The script prints an initial Environment section, preflight TCP and HTTP checks, and detailed timestamps around WebSocket connection attempts. It then performs the normal flow without changing behavior:
- `session_start` → expect `session_ack`
- send two `audio_chunk` frames
- expect `final_transcript` then `agent_text`
- send `user_text` → expect `agent_text` echo

### Environment Section
- `sys.version`: Python interpreter version
- `websockets.__version__`: installed websockets package version
- `platform.platform()`: OS and platform string
- `asyncio policy`: active event loop policy class name
- Proxy env vars (only names and values if present): `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` and lowercase variants
- WS URL chosen and how `localhost` was rewritten to `127.0.0.1`

### Preflight Connectivity
- TCP to `127.0.0.1:5080` and `127.0.0.1:5081`: prints `TCP OK` or `TCP FAIL (ExceptionType: message)`
- HTTP GET of `http://127.0.0.1:5080/ws/voice`: prints status and key headers. Expected: `426 Upgrade Required` for a gateway that requires WS upgrade.

### WebSocket Connect Logging
- Timestamps for `connect start`, `connect established`, and duration.
- Exceptions are printed with exact type and message for:
  - `TimeoutError`
  - `InvalidStatusCode`
  - `OSError`
  - `WebSocketException` (reported under their specific types by Python)
- If the standard `websockets.connect` attempt fails, and a legacy API is available, the script will try `websockets.legacy.client.connect` and report success or failure.

## Expected Output (Healthy Handshake)

A healthy run will look roughly like:

```
Environment diagnostics:
  sys.version: Python 3.12.x (...)
  websockets.__version__: 12.x
  platform.platform(): Windows-10-10.0.22621-SP0
  asyncio policy: WindowsSelectorEventLoopPolicy
  WS URL input: ws://localhost:5080/ws/voice
  WS URL rewritten: ws://127.0.0.1:5080/ws/voice
Probing HTTP /healthz: http://localhost:5080/healthz
Healthz status: 200
TCP preflight to 127.0.0.1:5080 ... TCP OK
TCP preflight to 127.0.0.1:5081 ... TCP OK
HTTP GET /ws/voice → 426
  upgrade: websocket
  connection: Upgrade
Connecting to ws://127.0.0.1:5080/ws/voice ...
connect established at 12:34:56 (Δ 0.15s)
→ Sent session_start
← Received: type=session_ack, payload={...}
→ Sent audio_chunk sequence=0 isLast=false
→ Sent audio_chunk sequence=1 isLast=true
← Received: type=final_transcript, payload={...}
← Received: type=agent_text, payload={...}
→ Sent user_text
← Received: type=agent_text, payload={...}
Connection closed.
```

## Interpreting Evidence and Recommended Fixes

- TCP preflight prints `TCP FAIL`:
  - Indicates network/process/binding issues (service not listening, port blocked, firewall, or IPv6/IPv4 mismatch).
  - Verify the gateway process is running and listening on `127.0.0.1:5080` (and `5081` for wss).

- HTTP GET `/ws/voice` returns `426 Upgrade Required`, but WS handshake times out:
  - Suggests the HTTP endpoint exists but the client handshake is not completing.
  - Likely causes: websockets library/runtime mismatch with Python 3.14, or client not sending the Upgrade sequence as expected.
  - Recommended: try under a Python 3.12 virtual environment as a controlled experiment to rule out Python 3.14 compatibility issues.

- Legacy client fallback succeeds while normal client fails:
  - Indicates compatibility quirks in the installed `websockets` version for your Python runtime.
  - Pin `websockets` to a version known to work with your Python version, or temporarily use the legacy client API.

## Notes

- The script avoids dumping secrets; proxy variables are printed only if present.
- `localhost` is rewritten to `127.0.0.1` to avoid IPv6 resolution issues.
- For `wss://localhost:5081/ws/voice`, certificate verification is disabled for local development only.
