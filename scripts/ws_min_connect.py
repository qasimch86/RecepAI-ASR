import os
import sys
import asyncio
import json
import websockets

# Ensure localhost bypasses proxies
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")

DEFAULT_URL = "ws://127.0.0.1:5080/ws/voice-simple"
WS_URL = os.getenv("RECEPAI_WS_URL", DEFAULT_URL)

OPEN_TIMEOUT = 5

async def main() -> int:
    try:
        try:
            ws = await websockets.connect(
                WS_URL,
                open_timeout=OPEN_TIMEOUT,
                ping_interval=None,
                proxy=None,
            )
        except TypeError:
            ws = await websockets.connect(
                WS_URL,
                open_timeout=OPEN_TIMEOUT,
                ping_interval=None,
            )
        async with ws:
            print("CONNECTED")
            first = await asyncio.wait_for(ws.recv(), timeout=OPEN_TIMEOUT)
            print(str(first))
            await ws.send(json.dumps({"type": "ping", "text": "hello"}))
            echo = await asyncio.wait_for(ws.recv(), timeout=OPEN_TIMEOUT)
            print(str(echo))
        return 0
    except Exception as e:
        print(f"{e.__class__.__name__}: {e}")
        return 2

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
