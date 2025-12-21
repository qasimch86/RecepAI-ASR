import argparse
import asyncio
import base64
import os
import sys
import json
import wave
from datetime import datetime, timezone
from typing import Optional, Tuple
from urllib.parse import urlparse

import websockets

# Ensure localhost bypasses proxies
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")

DEFAULT_URL = "ws://127.0.0.1:5080/ws/voice"
OPEN_TIMEOUT = 5
RECV_TIMEOUT = 5


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_env(msg_type: str, session_id: Optional[str], turn_id: Optional[str], payload: dict) -> dict:
    env = {
        "type": msg_type,
        "ts": iso_now(),
        "payload": payload,
    }
    if session_id is not None:
        env["sessionId"] = session_id
    if turn_id is not None:
        env["turnId"] = turn_id
    return env


def read_wav_pcm16_mono16k(path: str) -> Tuple[int, int, bytes]:
    with wave.open(path, "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()  # bytes per sample per channel
        fr = wf.getframerate()
        nframes = wf.getnframes()
        if not (nch == 1 and sw == 2 and fr == 16000):
            raise ValueError(
                f"Unsupported WAV format. Expected PCM16 mono 16k. Got channels={nch}, sampleWidth={sw*8}bit, sampleRate={fr}."
            )
        pcm = wf.readframes(nframes)
        return fr, nch, pcm


def chunk_bytes(pcm: bytes, chunk_ms: int) -> list[bytes]:
    # For PCM16 mono 16k: 32 bytes per ms (16000 * 2 / 1000)
    bytes_per_ms = 32
    size = max(bytes_per_ms * max(1, int(chunk_ms)), bytes_per_ms)
    out: list[bytes] = []
    for i in range(0, len(pcm), size):
        out.append(pcm[i : i + size])
    if not out:
        out = [pcm]
    return out


async def stream_audio(url: str, wav_path: str, chunk_ms: int, turn_id: str) -> int:
    print(f"Python: {sys.version.split()[0]}")
    print(f"websockets: {getattr(websockets, '__version__', 'unknown')}")
    print(f"URL: {url}")

    # Load and validate WAV
    try:
        rate, ch, pcm = read_wav_pcm16_mono16k(wav_path)
    except Exception as e:
        print(f"WAV error: {e}")
        return 2
    frames = chunk_bytes(pcm, chunk_ms)
    print(f"WAV ok: {len(pcm)} bytes, chunks={len(frames)} of ~{chunk_ms}ms")

    # Prepare connect kwargs; avoid proxies; small timeouts
    connect_kwargs = dict(
        open_timeout=OPEN_TIMEOUT,
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
        # Expect server_ready first
        first = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT)
        if isinstance(first, (bytes, bytearray)):
            first = first.decode("utf-8", errors="replace")
        print(f"RECV: {first}")
        try:
            first_obj = json.loads(first)
        except Exception:
            print("Invalid JSON from server; aborting")
            return 2
        if first_obj.get("type") != "server_ready":
            print("Unexpected first message; expected server_ready")
            return 2
        session_id = first_obj.get("sessionId")

        # Send session_start
        start = make_env(
            "session_start",
            session_id,
            None,
            {
                "storeId": 1,
                "customerToken": None,
                "locale": "en-US",
                "capabilities": ["audio_chunk", "user_text"],
            },
        )
        await ws.send(json.dumps(start))
        print("SENT: session_start")

        # Expect session_ack
        ack = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT)
        if isinstance(ack, (bytes, bytearray)):
            ack = ack.decode("utf-8", errors="replace")
        print(f"RECV: {ack}")

        # Stream audio_chunk frames
        print("Streaming audio chunks …")
        for idx, buf in enumerate(frames):
            is_last = idx == (len(frames) - 1)
            payload = {
                "sequence": idx,
                "isLast": is_last,
                "format": "pcm16",
                "sampleRate": 16000,
                "channels": 1,
                "dataBase64": base64.b64encode(buf).decode("ascii"),
            }
            env = make_env("audio_chunk", session_id, turn_id, payload)
            await ws.send(json.dumps(env))
            if idx % max(1, int(500 / max(1, chunk_ms))) == 0:
                print(f"SENT: audio_chunk seq={idx} last={is_last}")
        print("Audio stream sent.")

        # Wait for final_transcript and agent_text for the same turn
        got_final = False
        got_agent = False
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT)
            except asyncio.TimeoutError:
                print("Timeout waiting for server after audio; stopping.")
                break
            if isinstance(msg, (bytes, bytearray)):
                msg = msg.decode("utf-8", errors="replace")
            print(f"RECV: {msg}")
            try:
                obj = json.loads(msg)
            except Exception:
                continue
            typ = obj.get("type")
            if typ == "final_transcript" and obj.get("turnId") == turn_id:
                got_final = True
            elif typ == "agent_text" and obj.get("turnId") == turn_id:
                got_agent = True
            if got_final and got_agent:
                print("Got final_transcript and agent_text. Done.")
                break
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Audio WS test client (PCM16 mono 16k)")
    p.add_argument("--url", default=DEFAULT_URL, help="WebSocket URL (default ws://127.0.0.1:5080/ws/voice)")
    p.add_argument("--wav", required=True, help="Path to PCM16 mono 16k WAV file")
    p.add_argument("--chunk-ms", type=int, default=100, help="Chunk duration ms (default 100)")
    p.add_argument("--turn-id", default="turn-1", help="Turn ID (default turn-1)")
    args = p.parse_args()

    try:
        return asyncio.run(stream_audio(args.url, args.wav, args.chunk_ms, args.turn_id))
    except Exception as e:
        print(f"{e.__class__.__name__}: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
