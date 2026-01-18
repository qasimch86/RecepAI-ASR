#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Phase 8 Smoke Test - Validates the Gateway WebSocket protocol implementation.

.DESCRIPTION
    Runs ws_phase8_client.ps1 and propagates exit codes.
    - Exit 0: PASS (all validations successful)
    - Exit 1: FAIL (validation errors or protocol violations)

.PARAMETER WsUrl
    WebSocket URL to connect to (default: ws://127.0.0.1:5080/ws/voice)

.PARAMETER StoreId
    Store ID for session_start (default: 1)

.PARAMETER Locale
    Locale for session_start (default: en-CA)

.PARAMETER CustomerToken
    Optional customer token

.PARAMETER TimeoutSeconds
    Timeout for receiving messages (default: 20)

.PARAMETER BargeInDuringText
    Enable barge-in test (optional, skips some validations)

.EXAMPLE
    .\phase8_smoketest.ps1

.EXAMPLE
    .\phase8_smoketest.ps1 -WsUrl "ws://localhost:5080/ws/voice" -TimeoutSeconds 30
#>

param(
    [string]$WsUrl = "ws://127.0.0.1:5080/ws/voice",
    [int]$StoreId = 1,
    [string]$Locale = "en-CA",
    [string]$CustomerToken = "",
    [int]$TimeoutSeconds = 20,
    [switch]$BargeInDuringText
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Phase 8 WebSocket Protocol Smoke Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Target: $WsUrl"
Write-Host "Timeout: ${TimeoutSeconds}s"
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$clientScript = Join-Path $scriptDir "ws_phase8_client.ps1"

if (-not (Test-Path $clientScript)) {
    Write-Host "ERROR: Client script not found: $clientScript" -ForegroundColor Red
    exit 1
}

try {
    $params = @{
        WsUrl = $WsUrl
        StoreId = $StoreId
        Locale = $Locale
        CustomerToken = $CustomerToken
        TimeoutSeconds = $TimeoutSeconds
    }
    
    if ($BargeInDuringText) {
        $params['BargeInDuringText'] = $true
    }
    
    Write-Host "Running WebSocket client..." -ForegroundColor Yellow
    Write-Host ""
    
    & $clientScript @params
    $exitCode = $LASTEXITCODE
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    if ($exitCode -eq 0) {
        Write-Host "  SMOKE TEST: PASS" -ForegroundColor Green
    } else {
        Write-Host "  SMOKE TEST: FAIL (exit code: $exitCode)" -ForegroundColor Red
    }
    Write-Host "========================================" -ForegroundColor Cyan
    
    exit $exitCode
}
catch {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  SMOKE TEST: FAIL (exception)" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Exception: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    exit 1
}
