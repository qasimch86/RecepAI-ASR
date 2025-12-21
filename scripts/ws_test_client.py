"""
Quick text-only WebSocket test client for /ws/voice.

For audio streaming (PCM16 mono 16k) see:
    scripts/ws_audio_test_client.py --url ws://127.0.0.1:5080/ws/voice --wav path.wav
"""
import os
import sys
import json
import uuid
import datetime
import asyncio
import socket
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import websockets
from websockets.sync.client import connect as ws_sync_connect

# Ensure localhost bypasses proxies (even if none are set)
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")

DEFAULT_URL = "ws://127.0.0.1:5080/ws/voice"
WS_URL = os.getenv("RECEPAI_WS_URL", DEFAULT_URL)
CLIENT_IMPL = os.getenv("RECEPAI_WS_CLIENT", "async_websockets")

OPEN_TIMEOUT_SECONDS = 5
RECV_TIMEOUT_SECONDS = 5


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def parse_json(msg: Any) -> Dict[str, Any]:
    if isinstance(msg, (bytes, bytearray)):
        try:
            msg = msg.decode("utf-8", errors="replace")
        except Exception:
            return {}
    if not isinstance(msg, str):
        return {}
    try:
        obj = json.loads(msg)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def env_proxy_dump() -> Dict[str, str]:
    keys = [
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    ]
    out: Dict[str, str] = {}
    for k in keys:
        v = os.environ.get(k)
        if v:
            out[k] = v
    return out


def make_envelope(msg_type: str, session_id: Optional[str], turn_id: Optional[str], payload: Any) -> Dict[str, Any]:
    env: Dict[str, Any] = {
        "type": msg_type,
        "ts": now_iso(),
        "payload": payload,
    }
    if session_id is not None:
        env["sessionId"] = session_id
    if turn_id is not None:
        env["turnId"] = turn_id
    return env


async def asyncio_method(url: str) -> int:
    print("Method: websockets.asyncio.client.connect")
    headers_preview = {
        "Host": urlparse(url).netloc,
        "Upgrade": "websocket",
        "Connection": "Upgrade",
        "Sec-WebSocket-Version": "13",
        "User-Agent": f"websockets/{getattr(websockets, '__version__', 'unknown')}",
    }
    for k, v in headers_preview.items():
        print(f"Request header: {k}: {v}")

    connect_kwargs = dict(
        open_timeout=OPEN_TIMEOUT_SECONDS,
        ping_interval=None,
        ping_timeout=None,
        compression=None,
    )
    try:
        connect_kwargs["proxy"] = None
        ws_cm = websockets.connect(url, **connect_kwargs)
    except TypeError:
        connect_kwargs.pop("proxy", None)
        ws_cm = websockets.connect(url, **connect_kwargs)

    async with ws_cm as ws:
        first = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT_SECONDS)
        print("CONNECTED")
        print(f"RECV (initial): {first}")
        first_obj = parse_json(first)
        session_id = first_obj.get("sessionId") if first_obj.get("type") == "server_ready" else None

        start = make_envelope("session_start", session_id, "turn-1", {"client": "ws_test_client"})
        await ws.send(json.dumps(start))
        print("SENT: session_start")
        ack = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT_SECONDS)
        print(f"RECV: {ack}")
        user = make_envelope("user_text", session_id, "turn-2", {"text": "hello"})
        await ws.send(json.dumps(user))
        print("SENT: user_text")
        agent = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT_SECONDS)
        print(f"RECV: {agent}")
    return 0


def sync_method(url: str) -> int:
    print("Method: websockets.sync.client.connect")
    headers_preview = {
        "Host": urlparse(url).netloc,
        "Upgrade": "websocket",
        "Connection": "Upgrade",
        "Sec-WebSocket-Version": "13",
        "User-Agent": f"websockets/{getattr(websockets, '__version__', 'unknown')}",
    }
    for k, v in headers_preview.items():
        print(f"Request header: {k}: {v}")

    try:
        with ws_sync_connect(
            url,
            open_timeout=OPEN_TIMEOUT_SECONDS,
            close_timeout=RECV_TIMEOUT_SECONDS,
            ping_interval=None,
            ping_timeout=None,
            compression=None,
            proxy=None,
        ) as ws:
            print("CONNECTED")
            ws.recv_timeout = RECV_TIMEOUT_SECONDS
            first = ws.recv()
            if isinstance(first, bytes):
                first = first.decode("utf-8", errors="replace")
            print(first)
            first_obj = parse_json(first)
            session_id = first_obj.get("sessionId") if first_obj.get("type") == "server_ready" else None
            start = make_envelope("session_start", session_id, "turn-1", {"client": "ws_test_client"})
            ws.send(json.dumps(start))
            ack = ws.recv()
            if isinstance(ack, bytes):
                ack = ack.decode("utf-8", errors="replace")
            print(ack)
            user = make_envelope("user_text", session_id, "turn-2", {"text": "hello"})
            ws.send(json.dumps(user))
            agent = ws.recv()
            if isinstance(agent, bytes):
                agent = agent.decode("utf-8", errors="replace")
            print(agent)
        return 0
    except TypeError:
        with ws_sync_connect(
            url,
            open_timeout=OPEN_TIMEOUT_SECONDS,
            close_timeout=RECV_TIMEOUT_SECONDS,
            ping_interval=None,
            ping_timeout=None,
        ) as ws:
            print("CONNECTED")
            ws.recv_timeout = RECV_TIMEOUT_SECONDS
            first = ws.recv()
            if isinstance(first, bytes):
                first = first.decode("utf-8", errors="replace")
            print(first)
            first_obj = parse_json(first)
            session_id = first_obj.get("sessionId") if first_obj.get("type") == "server_ready" else None
            start = make_envelope("session_start", session_id, "turn-1", {"client": "ws_test_client"})
            ws.send(json.dumps(start))
            ack = ws.recv()
            if isinstance(ack, bytes):
                ack = ack.decode("utf-8", errors="replace")
            print(ack)
            user = make_envelope("user_text", session_id, "turn-2", {"text": "hello"})
            ws.send(json.dumps(user))
            agent = ws.recv()
            if isinstance(agent, bytes):
                agent = agent.decode("utf-8", errors="replace")
            print(agent)
        return 0


def websocket_client_method(url: str) -> int:
    print("Method: websocket-client")
    try:
        import websocket  # type: ignore
    except Exception as e:
        print(f"websocket-client not installed: {e}")
        return 2
    headers_preview = [
        "Upgrade: websocket",
        "Connection: Upgrade",
        "Sec-WebSocket-Version: 13",
        "User-Agent: websocket-client",
    ]
    for h in headers_preview:
        print(f"Request header: {h}")
    try:
        ws = websocket.WebSocket()
        ws.settimeout(OPEN_TIMEOUT_SECONDS)
        ws.connect(url, header=headers_preview)
        print("CONNECTED")
        first = ws.recv()
        print(first)
        first_obj = parse_json(first)
        session_id = first_obj.get("sessionId") if first_obj.get("type") == "server_ready" else None
        start = make_envelope("session_start", session_id, "turn-1", {"client": "ws_test_client"})
        ws.send(json.dumps(start))
        ack = ws.recv()
        print(ack)
        user = make_envelope("user_text", session_id, "turn-2", {"text": "hello"})
        ws.send(json.dumps(user))
        agent = ws.recv()
        print(agent)
        ws.close()
        return 0
    except Exception as e:
        print(f"{e.__class__.__name__}: {e}")
        return 2


def raw_tcp_probe(url: str) -> None:
    print("Method: raw TCP probe")
    p = urlparse(url)
    host = p.hostname or "127.0.0.1"
    port = p.port or 80
    path = p.path or "/ws/voice"
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "\r\n"
    ).encode("ascii")
    try:
        with socket.create_connection((host, port), timeout=OPEN_TIMEOUT_SECONDS) as s:
            s.sendall(req)
            s.settimeout(RECV_TIMEOUT_SECONDS)
            data = s.recv(4096)
            first_line = b"" if not data else data.split(b"\r\n", 1)[0]
            try:
                print(f"TCP response: {first_line.decode('ascii', errors='replace')}")
            except Exception:
                print("TCP response: <binary>")
    except Exception as e:
        print(f"TCP probe error {e.__class__.__name__}: {e}")


def main() -> int:
    print(f"Python: {sys.version.split()[0]}")
    print(f"websockets: {getattr(websockets, '__version__', 'unknown')}")
    print(f"OS: {sys.platform}")
    print(f"Client impl: {CLIENT_IMPL}")
    proxies = env_proxy_dump()
    if proxies:
        print("Proxy-related env vars detected:")
        for k, v in proxies.items():
            print(f"  {k}={v}")
    else:
        print("No proxy-related env vars detected.")

    url = WS_URL
    print(f"WS URL: {url}")

    try:
        if os.environ.get("RECEPAI_RAW_PROBE") == "1":
            # Optional raw probe first to distinguish server hang vs client issue
            raw_tcp_probe(url)
        if CLIENT_IMPL == "async_websockets":
            rc = asyncio.run(asyncio_method(url))
        elif CLIENT_IMPL == "sync_websockets":
            rc = sync_method(url)
        elif CLIENT_IMPL == "websocket_client":
            rc = websocket_client_method(url)
        else:
            print("Unknown RECEPAI_WS_CLIENT; using async_websockets")
            rc = asyncio.run(asyncio_method(url))
        # Always run raw probe after to capture server behavior
        raw_tcp_probe(url)
        return rc
    except Exception as e:
        print(f"{e.__class__.__name__}: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
