from __future__ import annotations

import sys
from pathlib import Path


def pytest_configure():
    # Ensure `import recepai_asr_service...` works when running pytest from repo root.
    repo_root = Path(__file__).resolve()
    for _ in range(10):
        if (repo_root / "services" / "asr" / "recepai_asr_service").exists():
            break
        repo_root = repo_root.parent

    asr_app_dir = repo_root / "services" / "asr"
    if asr_app_dir.exists():
        sys.path.insert(0, str(asr_app_dir))
