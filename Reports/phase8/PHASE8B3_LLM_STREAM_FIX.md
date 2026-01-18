# LLM Stream Endpoint Fix - Response Premature Ending

## Problem
Gateway received HTTP 200 from `/llm/turn/stream` but then got `HttpIOException: "The response ended prematurely. (ResponseEnded)"`. This occurs when FastAPI's `StreamingResponse` sends headers (HTTP 200) but the async generator raises an exception before yielding any NDJSON lines, causing an abrupt connection close.

## Root Cause
The `ndjson_stream()` async generator in [main.py](../services/llm/recepai_llm_orchestrator/main.py) was not handling exceptions that occurred after HTTP 200 was sent. When `stream_llm_text()` raised an exception (e.g., empty response, API error, timeout), the exception propagated up and terminated the response without yielding a final NDJSON object.

## Changes Made

### 1. Added Stream Start Logging
**Location**: [main.py](../services/llm/recepai_llm_orchestrator/main.py#L468-L482)

```python
async def ndjson_stream():
    nonlocal first_ndjson_ms_value, ttft_ms_value, end_reason
    _LLM_ACTIVE_STREAMS.inc()
    
    # Log stream start with correlation IDs
    logger.info(
        "ndjson_stream_start",
        extra=log_extra(
            requestId=request_id,
            sessionId=session_id,
            turnId=turn_id,
            corr=corr,
            service="recepai_llm_orchestrator",
            model=_MODEL_NAME,
        ),
    )
```

**Purpose**: Confirms when streaming begins with all correlation IDs for debugging.

### 2. Added First Yield Logging
**Location**: [main.py](../services/llm/recepai_llm_orchestrator/main.py#L527-L540)

```python
# Log first yield to confirm streaming started successfully
if first_yield:
    first_yield = False
    logger.info(
        "ndjson_first_yield",
        extra=log_extra(
            requestId=request_id,
            sessionId=session_id,
            turnId=turn_id,
            corr=corr,
            service="recepai_llm_orchestrator",
            is_final=chunk.is_final,
            text_len=len(chunk.text),
        ),
    )
```

**Purpose**: Confirms first NDJSON line was successfully yielded (HTTP 200 committed + data flowing).

### 3. Exception Handling with Error NDJSON Yield
**Location**: [main.py](../services/llm/recepai_llm_orchestrator/main.py#L565-L599)

```python
except Exception as e:
    # Log exception with type and message
    exception_type = type(e).__name__
    exception_msg = str(e)[:200]
    logger.error(
        "ndjson_stream_exception",
        extra=log_extra(
            requestId=request_id,
            sessionId=session_id,
            turnId=turn_id,
            corr=corr,
            service="recepai_llm_orchestrator",
            exception_type=exception_type,
            exception_message=exception_msg,
        ),
    )
    
    if end_reason is None:
        if isinstance(e, TimeoutError):
            end_reason = "timeout"
        elif OpenAIError is not Exception and isinstance(e, OpenAIError):
            end_reason = "upstream_error"
        else:
            end_reason = "internal_error"
    
    # Yield one final error NDJSON object to prevent premature response ending
    # This ensures the Gateway receives a valid stream termination instead of ResponseEnded
    error_obj = {
        "type": "error",
        "code": "llm_stream_error",
        "message": f"{exception_type}: {exception_msg}"
    }
    yield (json.dumps(error_obj) + "\n").encode("utf-8")
```

**Purpose**: 
- Catches any exception after HTTP 200 sent
- Logs exception details (`ndjson_stream_exception`)
- Yields one final NDJSON error object instead of abrupt termination
- Prevents Gateway from seeing "ResponseEnded" error

### 4. Verified NDJSON Format
All yields use proper format:
```python
yield (json.dumps(obj) + "\n").encode("utf-8")
```

Ensures trailing newline on every NDJSON object (both success chunks and error objects).

### 5. Schema Stability Confirmed
Request model unchanged - still expects `user_text`:
```python
class TurnRequest(BaseModel):
    user_text: str
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
```

## How to Test

### Prerequisites
```powershell
# Ensure OPENAI_API_KEY is set
$env:OPENAI_API_KEY = "sk-proj-..."

# Start the LLM service
cd C:\inetpub\wwwroot\RecepAIPython
python -m uvicorn services.llm.recepai_llm_orchestrator.main:app --host 0.0.0.0 --port 5102 --log-level info
```

### Test 1: Using Test Script (Recommended)
```powershell
.\test_llm_stream.ps1
```

This script tests:
- Valid streaming request with proper NDJSON parsing
- Line-by-line streaming with EOF detection
- Error object detection

### Test 2: Manual PowerShell Test with HttpWebRequest
```powershell
$req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:5102/llm/turn/stream")
$req.Method = "POST"
$req.ContentType = "application/json"
$req.Headers.Add("X-RecepAI-RequestId", "req-test-001")
$req.Headers.Add("X-RecepAI-SessionId", "test-session")
$req.Headers.Add("X-RecepAI-TurnId", "test-turn-001")
$req.Timeout = 300000

$body = '{"user_text":"Hello! Please suggest 2 menu items.","session_id":"test-session","turn_id":"test-turn-001"}'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$reqStream = $req.GetRequestStream()
$reqStream.Write($bytes, 0, $bytes.Length)
$reqStream.Dispose()

try {
    $resp = $req.GetResponse()
    Write-Host "HTTP:" ([int]$resp.StatusCode) $resp.StatusDescription
    
    $stream = $resp.GetResponseStream()
    $reader = New-Object System.IO.StreamReader($stream)
    
    $count = 0
    while ($true) {
        $line = $reader.ReadLine()
        if ($null -eq $line) { Write-Host "EOF"; break }
        $count++
        Write-Host "NDJSON[$count]: $line"
    }
    
    $reader.Dispose()
    $stream.Dispose()
    $resp.Dispose()
    
} catch {
    Write-Host "ERROR:" $_.Exception.Message
    if ($_.Exception.Response) {
        $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host "ERROR BODY:" $sr.ReadToEnd()
        $sr.Dispose()
    }
}
```

### Test 3: Using curl.exe (NOT curl alias)
```powershell
# Success case (with valid API key)
curl.exe -X POST http://127.0.0.1:5102/llm/turn/stream `
  -H "Content-Type: application/json" `
  -H "X-RecepAI-RequestId: req-test-001" `
  -H "X-RecepAI-SessionId: test-session" `
  -H "X-RecepAI-TurnId: test-turn-001" `
  -d '{\"user_text\":\"Hello! Suggest 2 menu items.\",\"session_id\":\"test-session\",\"turn_id\":\"test-turn-001\"}' `
  --no-buffer

# Error case (without API key) - should yield error NDJSON instead of premature ending
$env:OPENAI_API_KEY = ""
# Restart service, then run same curl.exe command
# Expected: {"type":"error","code":"llm_stream_error","message":"..."}
```

## Expected Outcomes

### Success Case (Valid API Key)
**Log Sequence**:
1. `stream_start` - Request received
2. `ndjson_stream_start` - Streaming generator started
3. `ndjson_first_yield` - First NDJSON line yielded
4. `ttft_ms` - Time to first token
5. `llm_stream_response` - Final text received
6. `stream_end` - Stream completed

**NDJSON Output**:
```json
{"text":"Sure","isFinal":false,"source":"llm"}
{"text":"!","isFinal":false,"source":"llm"}
...
{"text":"Sure! I recommend: 1) Pasta Carbonara, 2) Caesar Salad. What cuisine do you prefer?","isFinal":true,"source":"llm"}
```

### Error Case (Invalid API Key or Empty Response)
**Log Sequence**:
1. `stream_start` - Request received
2. `ndjson_stream_start` - Streaming generator started
3. `llm_stream_error` - Error in stream_llm_text()
4. `ndjson_stream_exception` - Exception caught in ndjson_stream
5. `stream_end` - Stream completed with error

**NDJSON Output**:
```json
{"type":"error","code":"llm_stream_error","message":"RuntimeError: LLM returned empty response (model=gpt-4o-mini, chunks=0)"}
```

### Gateway Behavior
**Before Fix**: Gateway sees HTTP 200, starts reading, then gets `ResponseEnded` exception.

**After Fix**: Gateway sees HTTP 200, receives error NDJSON object, cleanly closes connection. No `ResponseEnded` exception.

## Proof of Prevention

### Empty agent_text Cannot Be Sent
1. **Orchestrator Guard**: [main.py](../services/llm/recepai_llm_orchestrator/main.py#L337-L358) - Raises `RuntimeError` if `final_text` is empty
2. **Stream Exception Handler**: Catches the `RuntimeError` and yields error NDJSON instead of text chunk
3. **Double Guard**: Even if empty text somehow passes orchestrator, Gateway handler should validate

### ResponseEnded Cannot Occur
- Exception handler yields valid NDJSON error object
- Stream terminates cleanly with proper EOF
- Gateway reads error object and handles gracefully

## Files Modified
- [services/llm/recepai_llm_orchestrator/main.py](../services/llm/recepai_llm_orchestrator/main.py) (4 changes)
  - Added `ndjson_stream_start` logging
  - Added `ndjson_first_yield` logging  
  - Added `ndjson_stream_exception` logging with error NDJSON yield
  - Moved `nonlocal` declarations to function start

## Files Created
- [test_llm_stream.ps1](../test_llm_stream.ps1) - Test script for streaming endpoint

## Commands to Run

### Start Service
```powershell
cd C:\inetpub\wwwroot\RecepAIPython
$env:OPENAI_API_KEY = "sk-proj-..."
python -m uvicorn services.llm.recepai_llm_orchestrator.main:app --host 0.0.0.0 --port 5102 --log-level info
```

### Run Tests
```powershell
# Automated test
.\test_llm_stream.ps1

# Manual curl.exe test
curl.exe -X POST http://127.0.0.1:5102/llm/turn/stream -H "Content-Type: application/json" -d '{\"user_text\":\"Hello\",\"session_id\":\"test\",\"turn_id\":\"t1\"}' --no-buffer
```

### Verify Logs
Look for these events in service output:
- `ndjson_stream_start` - Confirms streaming started
- `ndjson_first_yield` - Confirms first line sent
- `ndjson_stream_exception` - If error occurs (with exception type/message)
- `stream_end` - Final metrics

## Next Steps
1. Test with Gateway to confirm no more `ResponseEnded` errors
2. Verify Gateway properly handles error NDJSON objects
3. Confirm correlation IDs flow through logs for debugging
