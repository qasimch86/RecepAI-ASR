# Client Probe Runbook

Use these probes to distinguish whether `/ws/voice` stalls due to server-side DI resolution or client-side issues.

## What Each Probe Shows
- TCP probe: Measures TCP connect time and prints the first line and headers of the HTTP response to an RFC6455 upgrade request within 2s. If no response, the server likely didn’t write the 101/426 response yet (e.g., DI hang).
- WebSockets probe: Attempts `websockets.connect()` with short timeouts and prints the first server message when successful.
- ws_test_client: End-to-end Phase-4/5 flow with optional raw probe first via env `RECEPAI_RAW_PROBE=1`.

## Commands

Probe `/ws/voice`:
```powershell
python scripts/di_probe_runner.py --path /ws/voice
```
Raw probe only:
```powershell
python scripts/di_probe_runner.py --raw-probe-only
```
Run ws_test_client with raw probe first:
```powershell
$env:RECEPAI_WS_URL="ws://127.0.0.1:5080/ws/voice"
$env:RECEPAI_WS_CLIENT="sync_websockets"
$env:RECEPAI_RAW_PROBE="1"
python scripts/ws_test_client.py
```

## Interpreting Results
- TCP connect fast (<50 ms) but no HTTP response in 2s: server accepted the TCP but didn’t send upgrade response; likely server-side stall (e.g., DI resolving `IAsrClient`).
- TCP shows `HTTP/1.1 426 Upgrade Required`: server is reachable and expects WebSocket; client should proceed; if websockets times out, suspect client library/runtime mismatch.
- WebSockets async fails while sync succeeds: prefer sync client or adjust parameters (disable compression, ensure small timeouts). Investigate asyncio/windows specifics.

## Notes
- Probes avoid secrets; only standard headers are used.
- NO_PROXY defaults ensure localhost bypasses proxy settings.
- Keep timeouts short and deterministic.
