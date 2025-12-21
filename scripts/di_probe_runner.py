import os
import sys
import time
import socket
import argparse
from datetime import datetime

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 5080
PATHS_DEFAULT = ["/ws/voice", "/ws/voice-simple"]
CONNECT_TIMEOUT = 2.0
READ_TIMEOUT = 2.0

RFC6455_KEY = "dGhlIHNhbXBsZSBub25jZQ=="  # static key OK for probe


def timestamp() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def tcp_upgrade_probe(host: str, port: int, path: str) -> None:
    print(f"[{timestamp()}] Probe {host}:{port}{path}")
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT) as s:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            print(f"[{timestamp()}] TCP connect time: {elapsed_ms:.1f} ms")
            req = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                f"Sec-WebSocket-Key: {RFC6455_KEY}\r\n"
                "\r\n"
            ).encode("ascii")
            s.sendall(req)
            s.settimeout(READ_TIMEOUT)
            try:
                data = s.recv(1024)
            except socket.timeout:
                data = b""
            if data:
                text = data.decode("iso-8859-1", errors="replace")
                lines = text.split("\r\n")
                status = lines[0] if lines else "<no status line>"
                print(f"[{timestamp()}] HTTP response status line: {status}")
                print(f"[{timestamp()}] HTTP headers (partial):")
                for line in lines[1:]:
                    if not line:
                        break
                    print(f"  {line}")
            else:
                print(f"[{timestamp()}] No HTTP upgrade response within {READ_TIMEOUT:.0f}s")
    except Exception as e:
        print(f"[{timestamp()}] TCP error {e.__class__.__name__}: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Raw RFC6455 upgrade probe (stdlib-only)")
    parser.add_argument("--host", default=HOST_DEFAULT)
    parser.add_argument("--port", type=int, default=PORT_DEFAULT)
    parser.add_argument("--paths", nargs="*", default=PATHS_DEFAULT, help="Paths to probe, default: /ws/voice /ws/voice-simple")
    args = parser.parse_args()

    # Ensure localhost bypasses proxies
    os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
    os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")

    for p in args.paths:
        tcp_upgrade_probe(args.host, args.port, p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
