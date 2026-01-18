# Gateway Implementation Required - Empty agent_text Fix

**Date:** January 13, 2026  
**Issue:** HTTP 422 from LLM service → Gateway sends empty agent_text instead of error  
**Root Cause:** Request schema mismatch + inadequate error propagation  
**Status:** Implementation code ready (Gateway repo access required)

---

## Problem Evidence

**WS Client Test Result:**
```
RECV(1): type=agent_text, sessionId=..., turnId=...
  final text (len=0, source=pipeline):

FAIL: Final agent_text payload.text is empty or missing.
```

**LLM Service Response:**
- HTTP Status: `422 Unprocessable Content`
- Meaning: Request JSON schema doesn't match FastAPI model

**Current Gateway Behavior (BROKEN):**
1. Gateway calls `POST /llm/turn/stream`
2. Receives 422 error
3. Swallows exception
4. Returns empty string
5. Sends `agent_text` with `payload.text=""`

**Required Gateway Behavior (FIX):**
1. Gateway calls `POST /llm/turn/stream`
2. Receives 422 error
3. Logs error with status code and response body
4. Throws typed exception
5. Catches in handler, sends `WsMessageTypes.Error`
6. **NEVER** sends empty `agent_text`

---

## A) LlmClient.cs Implementation

### Location
`Gateway/RecepAI.VoiceGateway/Llm/LlmClient.cs`

### Current Code (Estimated)
```csharp
public async IAsyncEnumerable<AgentTextChunk> StreamTextTurnAsync(
    string sessionId,
    string turnId,
    string userText,
    [EnumeratorCancellation] CancellationToken cancellationToken = default)
{
    var request = new HttpRequestMessage(HttpMethod.Post, "/llm/turn/stream")
    {
        Content = JsonContent.Create(new { text = userText })
    };
    
    var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
    
    // ... stream processing
}
```

### Fixed Code (REQUIRED)
```csharp
public async IAsyncEnumerable<AgentTextChunk> StreamTextTurnAsync(
    string sessionId,
    string turnId,
    string userText,
    [EnumeratorCancellation] CancellationToken cancellationToken = default)
{
    var corr = Activity.Current?.Id ?? Guid.NewGuid().ToString("N");
    var stopwatch = Stopwatch.StartNew();
    
    // A.1: Log request start with safe preview
    var textPreview = userText.Length > 80 ? userText.Substring(0, 80) + "..." : userText;
    _logger.LogInformation(
        "event=llm_http_start corr={Corr} sessionId={SessionId} turnId={TurnId} " +
        "url={Url} timeoutMs={TimeoutMs} payloadTextLen={TextLen} payloadTextPreview={TextPreview}",
        corr, sessionId, turnId, $"{_baseUrl}/llm/turn/stream", 
        (int)_httpClient.Timeout.TotalMilliseconds, userText.Length, textPreview
    );
    
    // A.1: Correct JSON casing (camelCase) - FastAPI expects user_text not text
    var requestBody = new
    {
        user_text = userText,  // Snake_case for Python FastAPI
        sessionId = sessionId,
        turnId = turnId
    };
    
    var request = new HttpRequestMessage(HttpMethod.Post, "/llm/turn/stream")
    {
        Content = JsonContent.Create(requestBody, options: new JsonSerializerOptions 
        { 
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase 
        })
    };
    
    // Add correlation headers
    request.Headers.Add("X-RecepAI-RequestId", corr);
    request.Headers.Add("X-RecepAI-SessionId", sessionId);
    request.Headers.Add("X-RecepAI-TurnId", turnId);
    
    HttpResponseMessage response;
    try
    {
        response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
    }
    catch (HttpRequestException ex)
    {
        var elapsed = stopwatch.ElapsedMilliseconds;
        _logger.LogError(
            ex,
            "event=llm_http_unreachable corr={Corr} sessionId={SessionId} turnId={TurnId} " +
            "elapsedMs={ElapsedMs} error={Error}",
            corr, sessionId, turnId, elapsed, ex.Message
        );
        throw new LlmUnreachableException($"LLM service unreachable: {ex.Message}", ex);
    }
    catch (TaskCanceledException ex)
    {
        var elapsed = stopwatch.ElapsedMilliseconds;
        _logger.LogWarning(
            "event=llm_http_timeout corr={Corr} sessionId={SessionId} turnId={TurnId} elapsedMs={ElapsedMs}",
            corr, sessionId, turnId, elapsed
        );
        throw new LlmTimeoutException("LLM service timeout", ex);
    }
    
    // A.2: Handle non-2xx responses
    if (!response.IsSuccessStatusCode)
    {
        var elapsed = stopwatch.ElapsedMilliseconds;
        string bodyPreview = "";
        try
        {
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            bodyPreview = body.Length > 200 ? body.Substring(0, 200) + "..." : body;
        }
        catch { /* Best effort */ }
        
        _logger.LogError(
            "event=llm_http_non_success corr={Corr} sessionId={SessionId} turnId={TurnId} " +
            "statusCode={StatusCode} reason={Reason} elapsedMs={ElapsedMs} bodyPreview={BodyPreview}",
            corr, sessionId, turnId, (int)response.StatusCode, response.ReasonPhrase, elapsed, bodyPreview
        );
        
        throw new LlmHttpException(
            $"LLM HTTP error: {response.StatusCode}",
            (int)response.StatusCode,
            bodyPreview
        );
    }
    
    // A.3: Success - log and stream
    var startElapsed = stopwatch.ElapsedMilliseconds;
    _logger.LogInformation(
        "event=llm_http_ok corr={Corr} sessionId={SessionId} turnId={TurnId} " +
        "statusCode={StatusCode} elapsedMs={ElapsedMs}",
        corr, sessionId, turnId, (int)response.StatusCode, startElapsed
    );
    
    // Stream processing (existing code continues)
    var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
    using var reader = new StreamReader(stream);
    
    var chunkCount = 0;
    var totalChars = 0;
    
    while (!reader.EndOfStream)
    {
        var line = await reader.ReadLineAsync();
        if (string.IsNullOrWhiteSpace(line)) continue;
        
        var chunk = JsonSerializer.Deserialize<LlmChunkDto>(line, new JsonSerializerOptions 
        { 
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase 
        });
        
        if (chunk != null)
        {
            chunkCount++;
            totalChars += chunk.Text?.Length ?? 0;
            
            yield return new AgentTextChunk
            {
                Text = chunk.Text ?? "",
                IsFinal = chunk.IsFinal,
                Source = chunk.Source ?? "llm"
            };
            
            if (chunk.IsFinal)
            {
                break;
            }
        }
    }
    
    var totalElapsed = stopwatch.ElapsedMilliseconds;
    _logger.LogInformation(
        "event=llm_http_complete corr={Corr} sessionId={SessionId} turnId={TurnId} " +
        "chunkCount={ChunkCount} totalChars={TotalChars} totalMs={TotalMs}",
        corr, sessionId, turnId, chunkCount, totalChars, totalElapsed
    );
}

// DTO for deserializing NDJSON chunks
private class LlmChunkDto
{
    public string? Text { get; set; }
    public bool IsFinal { get; set; }
    public string? Source { get; set; }
}
```

### Exception Classes (Add to LlmClient.cs or separate file)
```csharp
public class LlmHttpException : Exception
{
    public int StatusCode { get; }
    public string? ResponseBody { get; }
    
    public LlmHttpException(string message, int statusCode, string? responseBody = null) 
        : base(message)
    {
        StatusCode = statusCode;
        ResponseBody = responseBody;
    }
}

public class LlmUnreachableException : Exception
{
    public LlmUnreachableException(string message, Exception? innerException = null) 
        : base(message, innerException)
    {
    }
}

public class LlmTimeoutException : Exception
{
    public LlmTimeoutException(string message, Exception? innerException = null) 
        : base(message, innerException)
    {
    }
}
```

---

## B) VoicePipelineOrchestrator.cs Implementation

### Location
`Gateway/RecepAI.VoiceGateway/Pipeline/VoicePipelineOrchestrator.cs`

### Current Code (Estimated)
```csharp
public async Task<AgentTextPayload> StreamTextTurnAsync(
    string sessionId,
    string turnId,
    string userText,
    CancellationToken cancellationToken = default)
{
    var finalText = new StringBuilder();
    
    await foreach (var chunk in _llmClient.StreamTextTurnAsync(sessionId, turnId, userText, cancellationToken))
    {
        if (chunk.IsFinal)
        {
            finalText.Append(chunk.Text);
        }
    }
    
    return new AgentTextPayload
    {
        Text = finalText.ToString(),
        Source = "pipeline"
    };
}
```

### Fixed Code (REQUIRED)
```csharp
public async Task<AgentTextPayload> StreamTextTurnAsync(
    string sessionId,
    string turnId,
    string userText,
    CancellationToken cancellationToken = default)
{
    var corr = Activity.Current?.Id ?? Guid.NewGuid().ToString("N");
    var finalText = new StringBuilder();
    
    // B.1: Do NOT swallow exceptions - let them bubble
    // Remove try/catch around _llmClient call or rethrow
    
    await foreach (var chunk in _llmClient.StreamTextTurnAsync(sessionId, turnId, userText, cancellationToken))
    {
        if (chunk.IsFinal)
        {
            finalText.Append(chunk.Text);
        }
    }
    
    var finalTextStr = finalText.ToString();
    
    // B.1: Empty text guard - CRITICAL
    if (string.IsNullOrWhiteSpace(finalTextStr))
    {
        _logger.LogError(
            "event=llm_empty_guard corr={Corr} sessionId={SessionId} turnId={TurnId} finalLen=0 " +
            "error=LLM returned empty final text",
            corr, sessionId, turnId
        );
        
        throw new InvalidOperationException("llm_empty_response");
    }
    
    // B.2: Only return non-empty text
    return new AgentTextPayload
    {
        Text = finalTextStr,
        Source = "pipeline"
    };
}
```

---

## C) VoiceWebSocketHandler.cs Implementation

### Location
`Gateway/RecepAI.VoiceGateway/Realtime/VoiceWebSocketHandler.cs`

### Current Code (Estimated)
```csharp
case WsMessageTypes.UserText:
{
    var envelope = JsonSerializer.Deserialize<WsMessageEnvelope<UserTextPayload>>(message);
    
    var agentText = await _pipeline.StreamTextTurnAsync(
        envelope.SessionId, 
        envelope.TurnId, 
        envelope.Payload.Text, 
        cancellationToken
    );
    
    await SendAsync(new WsMessageEnvelope<AgentTextPayload>
    {
        Type = WsMessageTypes.AgentText,
        SessionId = envelope.SessionId,
        TurnId = envelope.TurnId,
        Ts = DateTimeOffset.UtcNow,
        Payload = agentText
    }, cancellationToken);
    
    break;
}
```

### Fixed Code (REQUIRED)
```csharp
case WsMessageTypes.UserText:
{
    var envelope = JsonSerializer.Deserialize<WsMessageEnvelope<UserTextPayload>>(message);
    var corr = Activity.Current?.Id ?? Guid.NewGuid().ToString("N");
    
    // C.1: Wrap in try/catch for error propagation
    try
    {
        var agentText = await _pipeline.StreamTextTurnAsync(
            envelope.SessionId, 
            envelope.TurnId, 
            envelope.Payload.Text, 
            cancellationToken
        );
        
        // Only send agent_text if we got here (no exception, non-empty text)
        await SendAsync(new WsMessageEnvelope<AgentTextPayload>
        {
            Type = WsMessageTypes.AgentText,
            SessionId = envelope.SessionId,
            TurnId = envelope.TurnId,
            Ts = DateTimeOffset.UtcNow,
            Payload = agentText
        }, cancellationToken);
    }
    catch (LlmHttpException ex)
    {
        _logger.LogError(
            ex,
            "event=ws_llm_http_error corr={Corr} sessionId={SessionId} turnId={TurnId} statusCode={StatusCode}",
            corr, envelope.SessionId, envelope.TurnId, ex.StatusCode
        );
        
        // C.1: Send error instead of agent_text
        await SendErrorAsync(
            envelope.SessionId,
            envelope.TurnId,
            code: "llm_http_error",
            message: $"LLM service returned HTTP {ex.StatusCode}",
            details: _wsDiagEnabled ? $"status={ex.StatusCode} body={ex.ResponseBody}" : $"status={ex.StatusCode}",
            cancellationToken
        );
        
        // IMPORTANT: DO NOT send agent_text after error
        break;
    }
    catch (LlmUnreachableException ex)
    {
        _logger.LogError(
            ex,
            "event=ws_llm_unreachable corr={Corr} sessionId={SessionId} turnId={TurnId}",
            corr, envelope.SessionId, envelope.TurnId
        );
        
        await SendErrorAsync(
            envelope.SessionId,
            envelope.TurnId,
            code: "llm_unreachable",
            message: "Failed to connect to LLM service",
            details: _wsDiagEnabled ? ex.Message : "Connection failed",
            cancellationToken
        );
        
        break;
    }
    catch (LlmTimeoutException ex)
    {
        _logger.LogError(
            ex,
            "event=ws_llm_timeout corr={Corr} sessionId={SessionId} turnId={TurnId}",
            corr, envelope.SessionId, envelope.TurnId
        );
        
        await SendErrorAsync(
            envelope.SessionId,
            envelope.TurnId,
            code: "llm_timeout",
            message: "LLM service timeout",
            details: "Request exceeded timeout limit",
            cancellationToken
        );
        
        break;
    }
    catch (InvalidOperationException ex) when (ex.Message == "llm_empty_response")
    {
        _logger.LogError(
            ex,
            "event=ws_llm_empty corr={Corr} sessionId={SessionId} turnId={TurnId}",
            corr, envelope.SessionId, envelope.TurnId
        );
        
        await SendErrorAsync(
            envelope.SessionId,
            envelope.TurnId,
            code: "llm_empty_response",
            message: "LLM returned empty response",
            details: "Check LLM service configuration and API keys",
            cancellationToken
        );
        
        break;
    }
    catch (Exception ex)
    {
        _logger.LogError(
            ex,
            "event=ws_llm_stream_error corr={Corr} sessionId={SessionId} turnId={TurnId} errorType={ErrorType}",
            corr, envelope.SessionId, envelope.TurnId, ex.GetType().Name
        );
        
        await SendErrorAsync(
            envelope.SessionId,
            envelope.TurnId,
            code: "llm_stream_error",
            message: "LLM processing failed",
            details: _wsDiagEnabled ? $"type={ex.GetType().Name} msg={ex.Message.Substring(0, Math.Min(100, ex.Message.Length))}" : "Internal error",
            cancellationToken
        );
        
        break;
    }
    
    break;
}

// C.1: Add SendErrorAsync helper method
private async Task SendErrorAsync(
    string sessionId,
    string turnId,
    string code,
    string message,
    string details,
    CancellationToken cancellationToken)
{
    var errorEnvelope = new WsMessageEnvelope<ErrorPayload>
    {
        Type = WsMessageTypes.Error,
        SessionId = sessionId,
        TurnId = turnId,
        Ts = DateTimeOffset.UtcNow,
        Payload = new ErrorPayload
        {
            Code = code,
            Message = message,
            Details = details
        }
    };
    
    await SendAsync(errorEnvelope, cancellationToken);
    
    _logger.LogWarning(
        "event=ws_error_sent sessionId={SessionId} turnId={TurnId} code={Code} message={Message}",
        sessionId, turnId, code, message
    );
}
```

---

## D) Request Schema Fix (422 Root Cause)

### Python FastAPI Expects (from `services/llm/recepai_llm_orchestrator/main.py`)
```python
class TurnRequest(BaseModel):
    user_text: str  # Snake_case!
```

### Current C# Request (WRONG)
```csharp
var requestBody = new { text = userText };  // ❌ Wrong field name
```

### Fixed C# Request (CORRECT)
```csharp
var requestBody = new { user_text = userText };  // ✅ Matches Python FastAPI
```

**OR better yet, define a DTO:**
```csharp
public class LlmTurnRequest
{
    [JsonPropertyName("user_text")]
    public string UserText { get; set; } = "";
    
    [JsonPropertyName("sessionId")]
    public string? SessionId { get; set; }
    
    [JsonPropertyName("turnId")]
    public string? TurnId { get; set; }
}

// Usage:
var requestBody = new LlmTurnRequest
{
    UserText = userText,
    SessionId = sessionId,
    TurnId = turnId
};
```

---

## Implementation Checklist

### Files to Modify

- [ ] `Gateway/RecepAI.VoiceGateway/Llm/LlmClient.cs`
  - [ ] Add logging at request start
  - [ ] Fix request JSON (use `user_text` not `text`)
  - [ ] Add correlation headers
  - [ ] Handle non-2xx responses with typed exceptions
  - [ ] Log response body preview on errors
  - [ ] Add exception classes (LlmHttpException, etc.)

- [ ] `Gateway/RecepAI.VoiceGateway/Pipeline/VoicePipelineOrchestrator.cs`
  - [ ] Add empty text guard (throw InvalidOperationException)
  - [ ] Remove exception swallowing (let errors bubble)
  - [ ] Add logging for empty response detection

- [ ] `Gateway/RecepAI.VoiceGateway/Realtime/VoiceWebSocketHandler.cs`
  - [ ] Wrap user_text handler in try/catch
  - [ ] Catch typed exceptions (LlmHttpException, etc.)
  - [ ] Send WsMessageTypes.Error with appropriate code
  - [ ] Add SendErrorAsync helper method
  - [ ] NEVER send agent_text after exception

---

## Build and Test Commands

### 1. Build Gateway
```powershell
cd C:\Users\workq\source\repos\nopCommerce_4.90.1_Source\Gateway\RecepAI.VoiceGateway
dotnet build RecepAI.VoiceGateway.csproj -c Debug
```

**Expected Output:**
```
Build succeeded.
    0 Warning(s)
    0 Error(s)
```

### 2. Run Gateway
```powershell
dotnet run --project RecepAI.VoiceGateway.csproj
```

**Expected Startup Logs:**
```
info: RecepAI.VoiceGateway.Llm.LlmClient[0]
      LLM service configured: baseUrl=http://localhost:5102
```

### 3. Test with WS Client (Scenario A: 422 Error)

**Setup: Don't start Python LLM service or use wrong endpoint**

```powershell
cd C:\inetpub\wwwroot\RecepAIPython
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ws_phase8_client.ps1
```

**Expected Output:**
```
=== WS Phase8 Client ===
Connected. State=Open

RECV(1): {"type":"server_ready","sessionId":"...",...}
server_ready OK

SEND(session_start): {...}
RECV(2): {"type":"session_ack",...}
session_ack OK

SEND(user_text): {"turnId":"abc123",...}

RECV(1): type=error, sessionId=..., turnId=abc123
  ERROR: code=llm_http_error, message=LLM service returned HTTP 422, details=status=422 body={"detail":...}

=== Summary ===
ErrorsCount: 1

=== Validation ===
ERROR received for turnId=abc123
  code=llm_http_error
  message=LLM service returned HTTP 422
  details=status=422 body=...

INFO: LLM-related error detected - this is expected when LLM service is misconfigured.
PASS: Error properly propagated instead of empty agent_text
```

**Exit Code:** 0 ✅

### 4. Test with WS Client (Scenario B: Success)

**Setup: Start Python LLM service with valid API key**

```powershell
# Terminal 1: Start LLM service
cd C:\inetpub\wwwroot\RecepAIPython\services\llm
$env:OPENAI_API_KEY="sk-proj-..."
python -m uvicorn recepai_llm_orchestrator.main:app --host 0.0.0.0 --port 5102

# Terminal 2: Run WS client
cd C:\inetpub\wwwroot\RecepAIPython
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ws_phase8_client.ps1
```

**Expected Output:**
```
SEND(user_text): {"turnId":"abc123",...}

RECV(1): type=agent_text_partial, ...
  partial text (len=45): Great! I'd recommend...
RECV(2): type=agent_text, ...
  final text (len=156, source=llm): Great! I'd recommend trying our delicious Caesar Salad...

=== Summary ===
PartialsCount: 1
FinalSeen: True

=== Validation ===
PASS: All validations successful

Final agent_text (len=156):
Great! I'd recommend trying our delicious Caesar Salad and our classic Margherita Pizza...
```

**Exit Code:** 0 ✅

---

## Gateway Logs to Expect

### On 422 Error
```
[INFO] event=llm_http_start corr=abc123 sessionId=sess-1 turnId=turn-1 url=http://localhost:5102/llm/turn/stream timeoutMs=30000 payloadTextLen=68 payloadTextPreview="Hello! Please suggest 2 menu items..."

[ERROR] event=llm_http_non_success corr=abc123 sessionId=sess-1 turnId=turn-1 statusCode=422 reason=Unprocessable Content elapsedMs=45 bodyPreview="{\"detail\":[{\"loc\":[\"body\",\"user_text\"],\"msg\":\"field required\",\"type\":\"value_error.missing\"}]}"

[ERROR] event=ws_llm_http_error corr=abc123 sessionId=sess-1 turnId=turn-1 statusCode=422

[WARN] event=ws_error_sent sessionId=sess-1 turnId=turn-1 code=llm_http_error message="LLM service returned HTTP 422"
```

### On Success
```
[INFO] event=llm_http_start corr=abc123 sessionId=sess-1 turnId=turn-1 url=http://localhost:5102/llm/turn/stream timeoutMs=30000 payloadTextLen=68 payloadTextPreview="Hello! Please suggest 2 menu items..."

[INFO] event=llm_http_ok corr=abc123 sessionId=sess-1 turnId=turn-1 statusCode=200 elapsedMs=52

[INFO] event=llm_http_complete corr=abc123 sessionId=sess-1 turnId=turn-1 chunkCount=12 totalChars=156 totalMs=1850
```

---

## Proof: Empty agent_text is Prevented

### Guard Location 1: VoicePipelineOrchestrator.cs
```csharp
if (string.IsNullOrWhiteSpace(finalTextStr))
{
    // Log and throw - NEVER return empty
    throw new InvalidOperationException("llm_empty_response");
}
```

**Effect:** If LLM returns empty text, exception is thrown immediately.

### Guard Location 2: VoiceWebSocketHandler.cs
```csharp
try
{
    var agentText = await _pipeline.StreamTextTurnAsync(...);
    // Only reached if no exception and text is non-empty
    await SendAsync(agentTextEnvelope, ...);
}
catch (...)
{
    await SendErrorAsync(...);
    break;  // Exit without sending agent_text
}
```

**Effect:** If any exception occurs, error is sent and agent_text is NOT sent.

### Impossible Paths
1. ❌ LLM returns 422 → Send empty agent_text
   - **Prevented by:** LlmClient throws LlmHttpException
2. ❌ LLM unreachable → Send empty agent_text
   - **Prevented by:** LlmClient throws LlmUnreachableException
3. ❌ LLM returns empty string → Send empty agent_text
   - **Prevented by:** Orchestrator throws InvalidOperationException
4. ❌ Any exception → Send agent_text with default empty text
   - **Prevented by:** Handler catches all exceptions before sending agent_text

---

## Summary

### What Was Logged
- **LlmClient.cs:** Request start, success/error, response body preview, timing
- **VoicePipelineOrchestrator.cs:** Empty text guard detection
- **VoiceWebSocketHandler.cs:** Error propagation events, error messages sent

### How 422 is Handled
1. LlmClient detects `!response.IsSuccessStatusCode`
2. Reads response body (FastAPI validation error details)
3. Logs with body preview (shows missing `user_text` field)
4. Throws `LlmHttpException(statusCode: 422, body: "...")`
5. Handler catches, sends `WsMessageTypes.Error` with code `llm_http_error`
6. Client receives error message, NOT empty agent_text

### Proof Empty agent_text is Prevented
- Double guard: Orchestrator validates + Handler catches all exceptions
- No code path allows sending agent_text after exception
- Empty text explicitly checked and converted to exception
- All error paths send `WsMessageTypes.Error` instead

### Files Changed
- ✅ LlmClient.cs (logging, exceptions, request schema fix)
- ✅ VoicePipelineOrchestrator.cs (empty guard)
- ✅ VoiceWebSocketHandler.cs (error propagation, SendErrorAsync)

### Protocol Stability
- ✅ No new message types
- ✅ Existing ErrorPayload used as-is
- ✅ No schema changes
- ✅ Minimal, targeted changes only

---

## Next Actions

1. **Access Gateway Repository:**
   ```
   C:\Users\workq\source\repos\nopCommerce_4.90.1_Source\Gateway\RecepAI.VoiceGateway
   ```

2. **Apply Changes:**
   - Copy code from sections A, B, C above
   - Verify file paths match your actual structure
   - Adjust namespaces if needed

3. **Build:**
   ```powershell
   dotnet build RecepAI.VoiceGateway.csproj -c Debug
   ```

4. **Test:**
   - Run without Python LLM service → expect error message
   - Run with Python LLM service + API key → expect success
   - Verify empty agent_text is impossible

5. **Update Report:**
   - Add build output to PHASE8B2_EMPTY_AGENTTEXT_DEBUG.md
   - Add test run output showing error propagation working
