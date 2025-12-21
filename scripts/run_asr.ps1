# Runs the ASR FastAPI service from the repo root.
# Uses --app-dir because the Python package lives under services\asr\recepai_asr_service,
# and starting from the repo root would otherwise fail to import the package.
# Assumes the virtual environment is already activated (e.g., & .\.venv\Scripts\Activate.ps1).

param(
    [int] $Port = 5101,
    [string] $Host = "0.0.0.0",
    [switch] $Reload
)

$reloadFlag = $Reload.IsPresent ? "--reload" : ""

Write-Host "Starting ASR service on $Host:$Port (reload=$($Reload.IsPresent))" -ForegroundColor Cyan
python -m uvicorn recepai_asr_service.main:app --app-dir services\asr --host $Host --port $Port $reloadFlag
