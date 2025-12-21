import os
import sys
import time
from typing import List, Tuple
import subprocess

URLS = [
    "ws://127.0.0.1:5080/ws/voice",
    "ws://127.0.0.1:5080/ws/voice-simple",
]
METHODS = [
    "async_websockets",
    "sync_websockets",
    "websocket_client",
    "raw_tcp",
]

LOGS_DIR = os.path.join("Logs")
MATRIX_MD = os.path.join(LOGS_DIR, "ws_probe_matrix.md")


def run_case(url: str, method: str) -> Tuple[str, str]:
    env = os.environ.copy()
    env["RECEPAI_WS_URL"] = url
    env["RECEPAI_WS_CLIENT"] = method
    if method == "raw_tcp":
        # Use ws_test_client to only run TCP probe: set unknown method to still do async and probe
        env["RECEPAI_WS_CLIENT"] = "async_websockets"
    cmd = [sys.executable, os.path.join("scripts", "ws_test_client.py")]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, env=env, text=True, timeout=15)
        status = "OK" if "CONNECTED" in out else "FAIL"
        # Extract first TCP response line if any
        first_line = ""
        for line in out.splitlines():
            if line.startswith("TCP response:"):
                first_line = line
                break
        return status, first_line
    except subprocess.CalledProcessError as e:
        txt = e.output or str(e)
        status = "FAIL"
        first_line = ""
        for line in txt.splitlines():
            if line.startswith("TCP response:"):
                first_line = line
                break
        return status, first_line
    except Exception as e:
        return "ERROR", f"{e.__class__.__name__}: {e}"


def main() -> int:
    os.makedirs(LOGS_DIR, exist_ok=True)
    lines: List[str] = []
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("| URL | Method | Result | TCP first line |")
    lines.append("|---|---|---|---|")
    for url in URLS:
        for method in METHODS:
            status, tcp = run_case(url, method)
            lines.append(f"| {url} | {method} | {status} | {tcp} |")
    with open(MATRIX_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(MATRIX_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
