Generated: 2025-12-14 22:02:50

| URL | Method | Result | TCP first line |
|---|---|---|---|
| ws://127.0.0.1:5080/ws/voice | async_websockets | FAIL |  |
| ws://127.0.0.1:5080/ws/voice | sync_websockets | FAIL |  |
| ws://127.0.0.1:5080/ws/voice | websocket_client | FAIL |  |
| ws://127.0.0.1:5080/ws/voice | raw_tcp | FAIL |  |
| ws://127.0.0.1:5080/ws/voice-simple | async_websockets | OK | TCP response: HTTP/1.1 101 Switching Protocols |
| ws://127.0.0.1:5080/ws/voice-simple | sync_websockets | OK | TCP response: HTTP/1.1 101 Switching Protocols |
| ws://127.0.0.1:5080/ws/voice-simple | websocket_client | OK | TCP response: HTTP/1.1 101 Switching Protocols |
| ws://127.0.0.1:5080/ws/voice-simple | raw_tcp | OK | TCP response: HTTP/1.1 101 Switching Protocols |
