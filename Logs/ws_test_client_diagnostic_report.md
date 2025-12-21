# ws_test_client Diagnostic Report

Generated: 2025-12-14

## Environment
- sys.executable: (runtime-defined)
- sys.version: (runtime-defined)
- websockets version: (runtime-defined)
- OS/platform: (runtime-defined)
- Event loop policy: asyncio default for Python 3.12
- NO_PROXY: localhost,127.0.0.1,::1
- Proxy env vars: none or printed at runtime if present

## WebSocket URL
- Configured: ws://127.0.0.1:5080/ws/voice
- Resolved host: 127.0.0.1

## Connection Methods Tested
- A: websockets.asyncio.client.connect
- B: websockets.sync.client.connect
- C: websocket-client (optional, if installed)
- D: Raw TCP RFC6455 upgrade probe

### Headers Preview (sent equivalents)
- Host: 127.0.0.1:5080
- Upgrade: websocket
- Connection: Upgrade
- Sec-WebSocket-Version: 13
- User-Agent: websockets/<version> or websocket-client

## Results Table
Produced by scripts/ws_probe_matrix.py into Logs/ws_probe_matrix.md

## Interpretation
- If Raw TCP probe shows HTTP/1.1 101 Switching Protocols for /ws/voice while one client stalls, it indicates client-side library/runtime mismatch during handshake framing.
- If Raw TCP probe returns 426 Upgrade Required, the endpoint expects WS upgrade and is reachable over TCP.
- If websockets.sync succeeds while asyncio fails, it suggests an asyncio handshake quirk with Python 3.12/windows stack or parameter incompatibility.
- If websocket-client works and websockets clients fail, consider headers/compression differences and try disabling compression.

## Recommended Next Steps
- Run with RECEPAI_WS_CLIENT set to each method and capture outputs:
  - `$env:RECEPAI_WS_URL="ws://127.0.0.1:5080/ws/voice"`
  - `$env:RECEPAI_WS_CLIENT="sync_websockets"`
  - `python scripts/ws_test_client.py`
- Generate matrix:
  - `python scripts/ws_probe_matrix.py`
- If only /ws/voice-simple succeeds while /ws/voice stalls, focus on the difference in server flow and Sec-WebSocket-* header handling; test under a clean Python 3.12 venv and websockets 15.x.
