import sys
import os
import subprocess
import time
import platform

def write_md(md_path: str, header_lines, body_lines) -> None:
    with open(md_path, "w", encoding="utf-8") as f:
        for h in header_lines:
            f.write(h + "\n")
        f.write("\n````\n")
        for line in body_lines:
            # Preserve blanks and order exactly
            f.write(line)
        f.write("\n````\n")

def main() -> int:
    md_path = os.path.join("scripts", "ws_test_client_first30.md")
    # Build header with environment details
    in_venv = (os.environ.get("VIRTUAL_ENV") is not None) or (getattr(sys, "base_prefix", sys.prefix) != sys.prefix)
    venv_desc = os.environ.get("VIRTUAL_ENV") or ("prefix=" + sys.prefix if in_venv else "none")
    header = [
        "# ws_test_client.py First 30 Lines",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"sys.executable: {sys.executable}",
        f"sys.version: {sys.version}",
        f"platform.platform(): {platform.platform()}",
        f"venv: {venv_desc}",
    ]

    # Proactive dependency check for this interpreter
    try:
        import websockets  # noqa: F401
    except Exception as e:
        body = [
            f"Dependency error: {e.__class__.__name__}: {e}\n",
            "websockets is missing in this environment.\n",
            f"Install with:\n",
            f"{sys.executable} -m pip install websockets\n",
        ]
        write_md(md_path, header, body)
        print(md_path)
        return 1

    cmd = [sys.executable, os.path.join("scripts", "ws_test_client.py")]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        lines = []
        for _ in range(30):
            line = proc.stdout.readline()
            if line == "":
                break
            lines.append(line)
    except Exception as e:
        lines = [f"Capture error {e.__class__.__name__}: {e}\n"]

    write_md(md_path, header, lines)
    print(md_path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
