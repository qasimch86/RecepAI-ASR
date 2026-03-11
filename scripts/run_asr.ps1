# Runs the ASR FastAPI service from the repo root.
# Uses --app-dir because the Python package lives under services\asr\recepai_asr_service,
# and starting from the repo root would otherwise fail to import the package.
# Assumes the virtual environment is already activated (e.g., & .\.venv\Scripts\Activate.ps1).

param(
    [int] $Port = 5101,
    [string] $Host = "0.0.0.0",
    [switch] $Reload,
    [string] $Provider = "whisper",
    [string] $WhisperModel = "base",
    [string] $WhisperDevice = "cpu",
    [string] $WhisperComputeType = "int8"
)

$reloadFlag = $Reload.IsPresent ? "--reload" : ""

$env:RECEPAI_STT_PROVIDER = $Provider
if ($Provider -eq "whisper" -or $Provider -eq "faster-whisper") {
    $env:RECEPAI_WHISPER_MODEL = $WhisperModel
    $env:RECEPAI_WHISPER_DEVICE = $WhisperDevice
    $env:RECEPAI_WHISPER_COMPUTE_TYPE = $WhisperComputeType
}

Write-Host "Starting ASR service on $Host:$Port (reload=$($Reload.IsPresent))" -ForegroundColor Cyan
Write-Host "RECEPAI_STT_PROVIDER=$env:RECEPAI_STT_PROVIDER" -ForegroundColor Cyan
if ($env:RECEPAI_STT_PROVIDER -eq "whisper" -or $env:RECEPAI_STT_PROVIDER -eq "faster-whisper") {
    Write-Host "RECEPAI_WHISPER_MODEL=$env:RECEPAI_WHISPER_MODEL; DEVICE=$env:RECEPAI_WHISPER_DEVICE; COMPUTE=$env:RECEPAI_WHISPER_COMPUTE_TYPE" -ForegroundColor Cyan
}
python -m uvicorn recepai_asr_service.main:app --app-dir services\asr --host $Host --port $Port $reloadFlag
