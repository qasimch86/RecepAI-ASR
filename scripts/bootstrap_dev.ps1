# Bootstrap developer environment for RecepAI Python stack.
# Assumes the virtual environment is already activated (e.g., & .\.venv\Scripts\Activate.ps1).
# Installs the shared package in editable mode and ASR service requirements
# so imports like `recepai_shared` succeed when running services.

Write-Host "Bootstrapping RecepAI Python dev environment..." -ForegroundColor Cyan

Write-Host "Installing shared package (editable): shared\python\recepai_shared" -ForegroundColor Yellow
python -m pip install -e .\shared\python\recepai_shared
if ($LASTEXITCODE -ne 0) { throw "Failed to install recepai_shared (editable)" }

Write-Host "Installing ASR service requirements" -ForegroundColor Yellow
python -m pip install -r .\services\asr\recepai_asr_service\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install ASR service requirements" }

Write-Host "Bootstrap complete." -ForegroundColor Green
Write-Host "Next: run ASR via scripts\run_asr.ps1 -Reload" -ForegroundColor Green
