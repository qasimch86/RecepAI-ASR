# Phase 8B.3 Hotfix Validation Script
# Tests that /llm/turn/stream no longer produces curl (18) or UnboundLocalError

$ErrorActionPreference = "Stop"

Write-Host "`n=== Phase 8B.3 Hotfix Validation ===" -ForegroundColor Cyan
Write-Host "Testing: services/llm/recepai_llm_orchestrator/main.py POST /llm/turn/stream`n" -ForegroundColor Cyan

# Ensure body.json exists
if (-not (Test-Path "body.json")) {
    Write-Host "Creating body.json..." -ForegroundColor Yellow
    @{
        user_text = "Hello! Please suggest 2 menu items and ask one follow-up question."
        session_id = "test-session"
        turn_id = "test-turn-001"
    } | ConvertTo-Json | Out-File -FilePath "body.json" -Encoding UTF8 -NoNewline
}

Write-Host "Test 1: curl.exe with --http1.1 (validates no curl (18) error)" -ForegroundColor Yellow
Write-Host "Command: curl.exe --http1.1 -v --no-buffer -H 'Content-Type: application/json' -H 'Accept: application/x-ndjson' --data-binary '@body.json' http://127.0.0.1:5102/llm/turn/stream`n" -ForegroundColor Gray

try {
    $curlOutput = curl.exe --http1.1 -v --no-buffer `
        -H "Content-Type: application/json" `
        -H "Accept: application/x-ndjson" `
        -H "X-RecepAI-RequestId: req-test-curl-001" `
        -H "X-RecepAI-SessionId: test-session" `
        -H "X-RecepAI-TurnId: test-turn-001" `
        --data-binary "@body.json" `
        http://127.0.0.1:5102/llm/turn/stream 2>&1
    
    $curlExitCode = $LASTEXITCODE
    
    # Parse output
    $hasHttp200 = $curlOutput | Where-Object { $_ -match "< HTTP/1.1 200" }
    $hasCurl18 = $curlOutput | Where-Object { $_ -match "curl.*\(18\)" }
    $hasContentType = $curlOutput | Where-Object { $_ -match "< content-type: application/x-ndjson" }
    
    Write-Host "curl exit code: $curlExitCode" -ForegroundColor $(if ($curlExitCode -eq 0) { "Green" } else { "Red" })
    Write-Host "HTTP 200: $(if ($hasHttp200) { 'YES' } else { 'NO' })" -ForegroundColor $(if ($hasHttp200) { "Green" } else { "Red" })
    Write-Host "Content-Type correct: $(if ($hasContentType) { 'YES' } else { 'NO' })" -ForegroundColor $(if ($hasContentType) { "Green" } else { "Yellow" })
    Write-Host "curl (18) error: $(if ($hasCurl18) { 'YES - FAIL' } else { 'NO - PASS' })" -ForegroundColor $(if ($hasCurl18) { "Red" } else { "Green" })
    
    # Show NDJSON lines
    $ndjsonLines = $curlOutput | Where-Object { $_ -match '^\{.*\}$' }
    if ($ndjsonLines) {
        Write-Host "`nNDJSON lines received: $($ndjsonLines.Count)" -ForegroundColor Cyan
        $ndjsonLines | ForEach-Object -Begin { $i = 1 } -Process {
            Write-Host "  [$i] $_"
            $i++
        }
    } else {
        Write-Host "`nNo NDJSON lines detected in output" -ForegroundColor Yellow
    }
    
    if ($hasCurl18) {
        Write-Host "`n[FAIL] curl (18) error detected - stream ended prematurely" -ForegroundColor Red
        $testResult = "FAIL"
    } elseif ($curlExitCode -ne 0) {
        Write-Host "`n[WARN] curl exited with code $curlExitCode but no (18) error" -ForegroundColor Yellow
        $testResult = "WARN"
    } else {
        Write-Host "`n[PASS] curl completed successfully, no premature termination" -ForegroundColor Green
        $testResult = "PASS"
    }
    
} catch {
    Write-Host "[ERROR] curl.exe failed: $_" -ForegroundColor Red
    $testResult = "ERROR"
}

Write-Host "`n---`n" -ForegroundColor Gray

Write-Host "Test 2: HttpWebRequest with line-by-line reading (validates clean EOF)" -ForegroundColor Yellow
Write-Host "Command: [System.Net.HttpWebRequest] POST with StreamReader.ReadLine()`n" -ForegroundColor Gray

try {
    $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:5102/llm/turn/stream")
    $req.Method = "POST"
    $req.ContentType = "application/json"
    $req.Accept = "application/x-ndjson"
    $req.Headers.Add("X-RecepAI-RequestId", "req-test-http-001")
    $req.Headers.Add("X-RecepAI-SessionId", "test-session")
    $req.Headers.Add("X-RecepAI-TurnId", "test-turn-001")
    $req.Timeout = 60000
    $req.ReadWriteTimeout = 60000
    
    $bodyContent = Get-Content "body.json" -Raw
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($bodyContent)
    $reqStream = $req.GetRequestStream()
    $reqStream.Write($bodyBytes, 0, $bodyBytes.Length)
    $reqStream.Dispose()
    
    $resp = $req.GetResponse()
    $statusCode = [int]$resp.StatusCode
    $contentType = $resp.ContentType
    
    Write-Host "HTTP Status: $statusCode $($resp.StatusDescription)" -ForegroundColor $(if ($statusCode -eq 200) { "Green" } else { "Red" })
    Write-Host "Content-Type: $contentType" -ForegroundColor Cyan
    
    $stream = $resp.GetResponseStream()
    $reader = New-Object System.IO.StreamReader($stream)
    
    $lineCount = 0
    $hasError = $false
    $lastLineWasFinal = $false
    
    while (-not $reader.EndOfStream) {
        $line = $reader.ReadLine()
        if ($null -ne $line -and $line.Trim() -ne "") {
            $lineCount++
            Write-Host "  [$lineCount] $($line.Substring(0, [Math]::Min(100, $line.Length)))$(if ($line.Length -gt 100) { '...' } else { '' })"
            
            try {
                $obj = $line | ConvertFrom-Json
                if ($obj.type -eq "error") {
                    $hasError = $true
                    Write-Host "       -> ERROR: $($obj.code) - $($obj.message)" -ForegroundColor Red
                } elseif ($obj.PSObject.Properties.Name -contains "isFinal") {
                    if ($obj.isFinal) {
                        $lastLineWasFinal = $true
                        Write-Host "       -> FINAL (len=$($obj.text.Length), source=$($obj.source))" -ForegroundColor Green
                    } else {
                        Write-Host "       -> DELTA (len=$($obj.text.Length), source=$($obj.source))" -ForegroundColor Cyan
                    }
                }
            } catch {
                Write-Host "       -> JSON parse error: $_" -ForegroundColor Magenta
            }
        }
    }
    
    $reader.Dispose()
    $stream.Dispose()
    $resp.Dispose()
    
    Write-Host "`nTotal NDJSON lines: $lineCount" -ForegroundColor Cyan
    Write-Host "Stream ended with error object: $(if ($hasError) { 'YES' } else { 'NO' })" -ForegroundColor $(if ($hasError) { "Yellow" } else { "Green" })
    Write-Host "Last line was final: $(if ($lastLineWasFinal) { 'YES' } else { 'NO' })" -ForegroundColor $(if ($lastLineWasFinal) { "Green" } else { "Yellow" })
    
    if ($lineCount -eq 0) {
        Write-Host "`n[FAIL] No NDJSON lines received - stream ended prematurely" -ForegroundColor Red
        $testResult2 = "FAIL"
    } elseif ($hasError) {
        Write-Host "`n[WARN] Stream completed with error object (check if expected)" -ForegroundColor Yellow
        $testResult2 = "WARN"
    } elseif (-not $lastLineWasFinal -and -not $hasError) {
        Write-Host "`n[WARN] Stream ended without final chunk or error" -ForegroundColor Yellow
        $testResult2 = "WARN"
    } else {
        Write-Host "`n[PASS] Stream completed cleanly with proper EOF" -ForegroundColor Green
        $testResult2 = "PASS"
    }
    
} catch {
    Write-Host "`n[ERROR] HttpWebRequest failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.InnerException) {
        Write-Host "  Inner: $($_.Exception.InnerException.Message)" -ForegroundColor Red
    }
    $testResult2 = "ERROR"
}

Write-Host "`n=== Validation Summary ===" -ForegroundColor Cyan
Write-Host "Test 1 (curl.exe):       $testResult" -ForegroundColor $(if ($testResult -eq "PASS") { "Green" } elseif ($testResult -eq "FAIL") { "Red" } else { "Yellow" })
Write-Host "Test 2 (HttpWebRequest): $testResult2" -ForegroundColor $(if ($testResult2 -eq "PASS") { "Green" } elseif ($testResult2 -eq "FAIL") { "Red" } else { "Yellow" })

if ($testResult -eq "PASS" -and $testResult2 -eq "PASS") {
    Write-Host "`nOVERALL: PASS - No premature stream termination detected" -ForegroundColor Green
    exit 0
} elseif ($testResult -eq "FAIL" -or $testResult2 -eq "FAIL") {
    Write-Host "`nOVERALL: FAIL - Premature stream termination still occurring" -ForegroundColor Red
    exit 1
} else {
    Write-Host "`nOVERALL: WARN - Tests completed with warnings, review logs" -ForegroundColor Yellow
    exit 2
}
