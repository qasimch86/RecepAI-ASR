# recepai_shared (Python)

Shared infrastructure package for the RecepAI Python services.

## Editable install (from repo root)
Activate the virtual environment, then install in editable mode:
```powershell
& .\.venv\Scripts\Activate.ps1
python -m pip install -e .\shared\python\recepai_shared
```

After installation, imports like the following should work:
```python
from recepai_shared import settings, get_logger
```
