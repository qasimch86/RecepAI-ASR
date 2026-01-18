# Test script for /llm/turn/stream endpoint
# Tests both success and error scenarios

$ErrorActionPreference = "Stop"

Write-Host "=== Testing /llm/turn/stream endpoint ===" -ForegroundColor Cyan

# Test 1: Valid request (requires OPENAI_API_KEY to be set)
Write-Host "`nTest 1: Valid streaming request" -ForegroundColor Yellow

$body = @{
    user_text = "Hello! Please suggest 2 menu items."
    session_id = "test-session"
    turn_id = "test-turn-001"
} | ConvertTo-Json

try {
    $headers = @{
        "Content-Type" = "application/json"
        "X-RecepAI-RequestId" = "req-$(New-Guid)"
        "X-RecepAI-SessionId" = "test-session"
        "X-RecepAI-TurnId" = "test-turn-001"
    }
    
    Write-Host "Sending request to http://127.0.0.1:5102/llm/turn/stream"
    Write-Host "Body: $body"
    
    # Use Invoke-WebRequest with -UseBasicParsing to handle streaming
    $response = Invoke-RestMethod `
        -Uri "http://127.0.0.1:5102/llm/turn/stream" `
        -Method Post `
        -Headers $headers `
        -Body $body `
        -ContentType "application/json"
    
    Write-Host "Response received (non-streaming mode):" -ForegroundColor Green
    Write-Host $response
    
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
        $errorBody = $reader.ReadToEnd()
        $reader.Dispose()
        Write-Host "Error body: $errorBody" -ForegroundColor Red
    }
}

# Test 2: Stream with HttpWebRequest (proper streaming test)
Write-Host "`nTest 2: Streaming with HttpWebRequest" -ForegroundColor Yellow

try {
    $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:5102/llm/turn/stream")
    $req.Method = "POST"
    $req.ContentType = "application/json"
    $req.Headers.Add("X-RecepAI-RequestId", "req-$(New-Guid)")
    $req.Headers.Add("X-RecepAI-SessionId", "test-session")
    $req.Headers.Add("X-RecepAI-TurnId", "test-turn-002")
    $req.SendChunked = $true
    $req.Timeout = 300000
    $req.ReadWriteTimeout = 300000
    
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    $reqStream = $req.GetRequestStream()
    $reqStream.Write($bodyBytes, 0, $bodyBytes.Length)
    $reqStream.Dispose()
    
    $resp = $req.GetResponse()
    Write-Host "HTTP: $([int]$resp.StatusCode) $($resp.StatusDescription)" -ForegroundColor Green
    
    $stream = $resp.GetResponseStream()
    $reader = New-Object System.IO.StreamReader($stream)
    
    $lineCount = 0
    $hasError = $false
    
    while ($true) {
        $line = $reader.ReadLine()
        if ($null -eq $line) {
            Write-Host "EOF reached" -ForegroundColor Green
            break
        }
        
        $lineCount++
        Write-Host "NDJSON[$lineCount]: $line"
        
        # Parse and check for error type
        try {
            $obj = $line | ConvertFrom-Json
            if ($obj.type -eq "error") {
                $hasError = $true
                Write-Host "  -> ERROR detected: code=$($obj.code), message=$($obj.message)" -ForegroundColor Red
            } elseif ($obj.PSObject.Properties.Name -contains "isFinal") {
                Write-Host "  -> isFinal=$($obj.isFinal), textLen=$($obj.text.Length), source=$($obj.source)" -ForegroundColor Cyan
            }
        } catch {
            Write-Host "  -> Failed to parse JSON: $_" -ForegroundColor Magenta
        }
    }
    
    $reader.Dispose()
    $stream.Dispose()
    $resp.Dispose()
    
    Write-Host "`nTotal NDJSON lines received: $lineCount" -ForegroundColor Green
    if ($hasError) {
        Write-Host "Stream contained error object (this is expected if API key is invalid)" -ForegroundColor Yellow
    } else {
        Write-Host "Stream completed successfully without errors" -ForegroundColor Green
    }
    
} catch {
    Write-Host "Request failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.InnerException) {
        Write-Host "Inner: $($_.Exception.InnerException.Message)" -ForegroundColor Red
    }
    
    # Try to read error response
    if ($_.Exception.Response) {
        try {
            $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            Write-Host "ERROR BODY: $($sr.ReadToEnd())" -ForegroundColor Red
            $sr.Dispose()
        } catch {}
    }
}

Write-Host "`n=== Test complete ===" -ForegroundColor Cyan
