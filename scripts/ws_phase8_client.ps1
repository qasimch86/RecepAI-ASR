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

function New-EnvelopeJson {
    param(
        [Parameter(Mandatory = $true)][string]$Type,
        [string]$SessionId,
        [string]$TurnId,
        [Parameter(Mandatory = $true)]$Payload
    )

    $env = [ordered]@{
        type      = $Type
        sessionId = if ([string]::IsNullOrWhiteSpace($SessionId)) { $null } else { $SessionId }
        turnId    = if ([string]::IsNullOrWhiteSpace($TurnId)) { $null } else { $TurnId }
        ts        = [DateTimeOffset]::UtcNow.ToString("o")
        payload   = $Payload
    }

    # Match WsCodec: camelCase + null omitted
    return ($env | ConvertTo-Json -Depth 20 -Compress)
}

function Get-JsonProperty {
    param(
        [Parameter(Mandatory=$true)]$JsonObj,
        [Parameter(Mandatory=$true)][string]$PropertyName,
        [string]$DefaultValue = ""
    )
    
    if ($null -eq $JsonObj) { return $DefaultValue }
    
    # Handle System.Text.Json.JsonElement (if available)
    $jsonElementType = "System.Text.Json.JsonElement" -as [type]
    if ($null -ne $jsonElementType -and $JsonObj.GetType().FullName -eq "System.Text.Json.JsonElement") {
        try {
            $prop = [System.Text.Json.JsonElement]::new()
            if ($JsonObj.TryGetProperty($PropertyName, [ref]$prop)) {
                if ($prop.ValueKind -eq [System.Text.Json.JsonValueKind]::String) {
                    return $prop.GetString()
                }
                return $prop.ToString()
            }
        }
        catch {
            # Fall through to PSCustomObject handling
        }
    }
    
    # Handle PSCustomObject (from ConvertFrom-Json)
    if ($JsonObj.PSObject.Properties.Name -contains $PropertyName) {
        $val = $JsonObj.PSObject.Properties[$PropertyName].Value
        if ($null -eq $val) { return $DefaultValue }
        return [string]$val
    }
    
    return $DefaultValue
}

function Get-JsonNestedProperty {
    param(
        [Parameter(Mandatory=$true)]$JsonObj,
        [Parameter(Mandatory=$true)][string]$ParentName,
        [Parameter(Mandatory=$true)][string]$ChildName,
        [string]$DefaultValue = ""
    )
    
    if ($null -eq $JsonObj) { return $DefaultValue }
    
    # Handle System.Text.Json.JsonElement (if available)
    $jsonElementType = "System.Text.Json.JsonElement" -as [type]
    if ($null -ne $jsonElementType -and $JsonObj.GetType().FullName -eq "System.Text.Json.JsonElement") {
        try {
            $parentProp = [System.Text.Json.JsonElement]::new()
            if ($JsonObj.TryGetProperty($ParentName, [ref]$parentProp)) {
                $childProp = [System.Text.Json.JsonElement]::new()
                if ($parentProp.TryGetProperty($ChildName, [ref]$childProp)) {
                    if ($childProp.ValueKind -eq [System.Text.Json.JsonValueKind]::String) {
                        return $childProp.GetString()
                    }
                    return $childProp.ToString()
                }
            }
        }
        catch {
            # Fall through to PSCustomObject handling
        }
    }
    
    # Handle PSCustomObject
    if ($JsonObj.PSObject.Properties.Name -contains $ParentName) {
        $parent = $JsonObj.PSObject.Properties[$ParentName].Value
        if ($null -ne $parent -and $parent.PSObject.Properties.Name -contains $ChildName) {
            $val = $parent.PSObject.Properties[$ChildName].Value
            if ($null -eq $val) { return $DefaultValue }
            return [string]$val
        }
    }
    
    return $DefaultValue
}

function Parse-JsonSafe {
  param([Parameter(Mandatory=$true)][string]$Json)

  if ([string]::IsNullOrWhiteSpace($Json)) { return $null }

  $clean = $Json.Trim()
  $clean = $clean.TrimStart([char]0xFEFF)  # strip BOM if present

  try {
    # ConvertFrom-Json is more compatible (works in PS 5.1 and 7+)
    return ($clean | ConvertFrom-Json)
  }
  catch {
    # Fallback: System.Text.Json (if available)
    try {
      $doc = [System.Text.Json.JsonDocument]::Parse($clean)
      return $doc.RootElement
    }
    catch {
      Write-Host "JSON parse error: $($_.Exception.Message)"
      Write-Host "RAW(JSON): $clean"
      return $null
    }
  }
}



function Receive-TextMessage {
  param(
    [Parameter(Mandatory = $true)] [System.Net.WebSockets.ClientWebSocket]$Ws,
    [Parameter(Mandatory = $true)] [System.Threading.CancellationToken]$Ct
  )

  $buffer = New-Object byte[] (64 * 1024)
  $seg = [System.ArraySegment[byte]]::new($buffer)
  $ms = New-Object System.IO.MemoryStream

  try {
    while ($true) {
      $result = $Ws.ReceiveAsync($seg, $Ct).GetAwaiter().GetResult()

      if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
        return $null
      }

      if ($result.MessageType -ne [System.Net.WebSockets.WebSocketMessageType]::Text) {
        # ignore all non-text frames and keep waiting
        continue
      }

      if ($result.Count -gt 0) {
        $ms.Write($buffer, 0, $result.Count) | Out-Null
      }

      if ($result.EndOfMessage) {
        $text = [System.Text.Encoding]::UTF8.GetString($ms.ToArray())
        $ms.Dispose()
        $ms = New-Object System.IO.MemoryStream  # Reset for next message
        return $text
      }
    }
  }
  catch {
    return $null
  }
  finally {
    if ($null -ne $ms) {
      $ms.Dispose()
    }
  }
}


function Send-TextMessage {
    param(
        [Parameter(Mandatory = $true)] [System.Net.WebSockets.ClientWebSocket]$Ws,
        [Parameter(Mandatory = $true)] [string]$Json,
        [Parameter(Mandatory = $true)] [System.Threading.CancellationToken]$Ct
    )

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Json)
    $seg = [System.ArraySegment[byte]]::new($bytes)
    $Ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $Ct).GetAwaiter().GetResult() | Out-Null
}

Write-Host "=== WS Phase8 Client ==="
Write-Host "WS URL: $WsUrl"
Write-Host "BargeInDuringText: $BargeInDuringText"
Write-Host ""

$ws = New-Object System.Net.WebSockets.ClientWebSocket
$cts = New-Object System.Threading.CancellationTokenSource([TimeSpan]::FromSeconds($TimeoutSeconds))

try {
    $ws.ConnectAsync([Uri]$WsUrl, $cts.Token).GetAwaiter().GetResult() | Out-Null
    Write-Host "Connected. State=$($ws.State)"
    Write-Host ""

    # 1) Expect initial server_ready (non-envelope)
    $msg1 = Receive-TextMessage -Ws $ws -Ct $cts.Token
    if ($null -eq $msg1) { 
        Write-Host "FAIL: No initial message; expected server_ready."
        exit 1
    }
    
    $msg1Obj = Parse-JsonSafe $msg1
    Write-Host "RECV(1): $msg1"
    
    $msg1Type = Get-JsonProperty -JsonObj $msg1Obj -PropertyName "type"
    $msg1SessionId = Get-JsonProperty -JsonObj $msg1Obj -PropertyName "sessionId"
    
    Write-Host "  type=$msg1Type, sessionId=$msg1SessionId"
    
    if ($msg1Type -ne "server_ready") {
        Write-Host "FAIL: Expected type='server_ready', got '$msg1Type'"
        exit 1
    }

    if ([string]::IsNullOrWhiteSpace($msg1SessionId)) { 
        Write-Host "FAIL: server_ready missing sessionId."
        exit 1
    }
    
    $sessionId = $msg1SessionId
    Write-Host "server_ready OK: sessionId=$sessionId"
    Write-Host ""

    # 2) Send session_start (enveloped)
    $capabilities = @("text", "audio")
    $payloadSessionStart = @{
        storeId       = $StoreId
        customerToken = if ([string]::IsNullOrWhiteSpace($CustomerToken)) { $null } else { $CustomerToken }
        locale        = $Locale
        capabilities  = $capabilities
    }

    $jsonStart = New-EnvelopeJson -Type "session_start" -SessionId $sessionId -TurnId "" -Payload $payloadSessionStart
    Write-Host "SEND(session_start): $jsonStart"
    Send-TextMessage -Ws $ws -Json $jsonStart -Ct $cts.Token

    # 3) Expect session_ack envelope
    $msg2 = Receive-TextMessage -Ws $ws -Ct $cts.Token
    if ($null -eq $msg2) { 
        Write-Host "FAIL: No session_ack received."
        exit 1
    }

    Write-Host "RECV(2): $msg2"
    $msg2Obj = Parse-JsonSafe $msg2
    
    $msg2Type = Get-JsonProperty -JsonObj $msg2Obj -PropertyName "type"
    $msg2SessionId = Get-JsonProperty -JsonObj $msg2Obj -PropertyName "sessionId"
    $msg2PayloadSessionId = Get-JsonNestedProperty -JsonObj $msg2Obj -ParentName "payload" -ChildName "sessionId"
    
    Write-Host "  type=$msg2Type, sessionId=$msg2SessionId, payload.sessionId=$msg2PayloadSessionId"
    
    if ($msg2Type -ne "session_ack") {
        Write-Host "FAIL: Expected type='session_ack', got '$msg2Type'"
        exit 1
    }
    
    if ($msg2SessionId -ne $sessionId) {
        Write-Host "FAIL: session_ack sessionId mismatch. Expected '$sessionId', got '$msg2SessionId'"
        exit 1
    }
    
    if ($msg2PayloadSessionId -ne $sessionId) {
        Write-Host "FAIL: session_ack payload.sessionId mismatch. Expected '$sessionId', got '$msg2PayloadSessionId'"
        exit 1
    }
    
    Write-Host "session_ack OK"
    Write-Host ""

    # # 4) Send user_text
    # $turnId = [Guid]::NewGuid().ToString("N")
    # $payloadUserText = @{ text = "Hello! Please suggest 2 menu items and ask one follow-up question." }
    # $jsonUser = New-EnvelopeJson -Type "user_text" -SessionId $sessionId -TurnId $turnId -Payload $payloadUserText
    # Write-Host "SEND(user_text): $jsonUser"
    # Write-Host "  turnId=$turnId"
    # Send-TextMessage -Ws $ws -Json $jsonUser -Ct $cts.Token

# 4a) Send user_text
$turnId = [Guid]::NewGuid().ToString("N")
$payloadUserText = @{ text = "Hello! Please suggest 2 menu items and ask one follow-up question." }
$jsonUser = New-EnvelopeJson -Type "user_text" -SessionId $sessionId -TurnId $turnId -Payload $payloadUserText
Write-Host "SEND(user_text): $jsonUser"
Write-Host "  turnId=$turnId"
Send-TextMessage -Ws $ws -Json $jsonUser -Ct $cts.Token

Start-Sleep -Milliseconds 200

# 4b) Send a follow-up message (same WS connection, new turnId)
$turnId2 = [Guid]::NewGuid().ToString("N")
$payloadUserText2 = @{ text = "Hello again! Please suggest 2 more items and ask another follow-up question." }
$jsonUser2 = New-EnvelopeJson -Type "user_text" -SessionId $sessionId -TurnId $turnId2 -Payload $payloadUserText2
Write-Host "SEND(user_text): $jsonUser2"
Write-Host "  turnId=$turnId2"
Send-TextMessage -Ws $ws -Json $jsonUser2 -Ct $cts.Token



    # Optional: barge-in test during text streaming
    if ($BargeInDuringText) {
        Start-Sleep -Milliseconds 150

        # Minimal valid audio_chunk while agent is in-flight -> triggers barge-in observation
        # Keep isLast=false to avoid running audio pipeline
        $tiny = New-Object byte[] 32
        $b64 = [Convert]::ToBase64String($tiny)

        $audioPayload = @{
            sequence   = 0
            isLast     = $false
            format     = "pcm16"
            sampleRate = 16000
            channels   = 1
            dataBase64 = $b64
        }

        $jsonAudio = New-EnvelopeJson -Type "audio_chunk" -SessionId $sessionId -TurnId $turnId -Payload $audioPayload
        Write-Host ""
        Write-Host "SEND(audio_chunk for barge-in): $jsonAudio"
        Send-TextMessage -Ws $ws -Json $jsonAudio -Ct $cts.Token

        # Cleanup the buffered audio (will likely error because too short, but that’s OK for testing)
        $jsonTurnEnd = New-EnvelopeJson -Type "turn_end" -SessionId $sessionId -TurnId $turnId -Payload @{}
        Write-Host "SEND(turn_end cleanup): $jsonTurnEnd"
        Send-TextMessage -Ws $ws -Json $jsonTurnEnd -Ct $cts.Token
    }

    # 5) Receive loop: collect partials + final
    $partials = New-Object System.Collections.Generic.List[object]
    $final = $null
    $gotSpeaking = $false
    $gotIdle = $false
    $errors = New-Object System.Collections.Generic.List[object]
    $receivedCount = 0

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)

    Write-Host ""
    while ([DateTime]::UtcNow -lt $deadline) {
        $m = Receive-TextMessage -Ws $ws -Ct $cts.Token
        if ($null -eq $m) { break }

        $o = Parse-JsonSafe $m
        $receivedCount++
        
        $msgType = Get-JsonProperty -JsonObj $o -PropertyName "type"
        $msgSessionId = Get-JsonProperty -JsonObj $o -PropertyName "sessionId"
        $msgTurnId = Get-JsonProperty -JsonObj $o -PropertyName "turnId"
        
        Write-Host "RECV($receivedCount): type=$msgType, sessionId=$msgSessionId, turnId=$msgTurnId"

        if ([string]::IsNullOrWhiteSpace($msgType)) { 
            Write-Host "  (skipped: no type)"
            continue 
        }

        switch ($msgType) {
            "agent_state" {
                $state = Get-JsonNestedProperty -JsonObj $o -ParentName "payload" -ChildName "state"
                Write-Host "  state=$state"
                if ($state -eq "speaking") { $gotSpeaking = $true }
                if ($state -eq "idle") { $gotIdle = $true }
            }
            "agent_text_partial" {
                $partialText = Get-JsonNestedProperty -JsonObj $o -ParentName "payload" -ChildName "text"
                if (-not [string]::IsNullOrWhiteSpace($partialText)) {
                    $preview = if ($partialText.Length -gt 60) { $partialText.Substring(0, 60) + "..." } else { $partialText }
                    Write-Host "  partial text (len=$($partialText.Length)): $preview"
                    $partials.Add($o) | Out-Null
                }
            }
            "agent_text" {
                $finalText = Get-JsonNestedProperty -JsonObj $o -ParentName "payload" -ChildName "text"
                $finalSource = Get-JsonNestedProperty -JsonObj $o -ParentName "payload" -ChildName "source"
                $preview = if ($finalText.Length -gt 120) { $finalText.Substring(0, 120) + "..." } else { $finalText }
                Write-Host "  final text (len=$($finalText.Length), source=$finalSource): $preview"
                $final = $o
                break
            }
            "error" {
                $errorCode = Get-JsonNestedProperty -JsonObj $o -ParentName "payload" -ChildName "code"
                $errorMessage = Get-JsonNestedProperty -JsonObj $o -ParentName "payload" -ChildName "message"
                $errorDetails = Get-JsonNestedProperty -JsonObj $o -ParentName "payload" -ChildName "details"
                Write-Host "  ERROR: code=$errorCode, message=$errorMessage, details=$errorDetails"
                $errors.Add($o) | Out-Null
            }
            default { 
                Write-Host "  (unhandled type)"
            }
        }

        if ($final -ne $null) { break }
    }

    Write-Host ""
    Write-Host "=== Summary ==="
    Write-Host "MessagesReceived: $receivedCount"
    Write-Host "SpeakingSeen: $gotSpeaking"
    Write-Host "PartialsCount: $($partials.Count)"
    Write-Host "FinalSeen: $([bool]($final -ne $null))"
    Write-Host "IdleSeen: $gotIdle"
    Write-Host "ErrorsCount: $($errors.Count)"

    Write-Host ""
    Write-Host "=== Validation ==="
    
    # Check for errors on this turn
    $hasLlmError = $false
    foreach ($err in $errors) {
        $errTurnId = Get-JsonProperty -JsonObj $err -PropertyName "turnId"
        if ($errTurnId -eq $turnId) {
            $errorCode = Get-JsonNestedProperty -JsonObj $err -ParentName "payload" -ChildName "code"
            $errorMessage = Get-JsonNestedProperty -JsonObj $err -ParentName "payload" -ChildName "message"
            $errorDetails = Get-JsonNestedProperty -JsonObj $err -ParentName "payload" -ChildName "details"
            Write-Host "ERROR received for turnId=$turnId"
            Write-Host "  code=$errorCode"
            Write-Host "  message=$errorMessage"
            Write-Host "  details=$errorDetails"
            
            # Check if it's an LLM-related error (expected failure mode)
            if ($errorCode -like "llm*" -or $errorCode -like "*llm*" -or $errorMessage -like "*LLM*" -or $errorMessage -like "*llm*") {
                Write-Host ""
                Write-Host "INFO: LLM-related error detected - this is expected when LLM service is misconfigured."
                Write-Host "PASS: Error properly propagated instead of empty agent_text"
                $hasLlmError = $true
            }
            else {
                Write-Host "FAIL: Received non-LLM error for turnId=$turnId"
                exit 1
            }
        }
    }
    
    if ($hasLlmError) {
        # If we got an LLM error, that's acceptable (better than silent empty agent_text)
        exit 0
    }

    if ($BargeInDuringText) {
        Write-Host "NOTE: barge-in test enabled. Depending on timing, final may be suppressed."
        Write-Host "PASS (barge-in mode, validations skipped)"
        exit 0
    }
    
    # MUST receive agent_text final
    if ($final -eq $null) { 
        Write-Host "FAIL: Expected agent_text final but did not receive it."
        Write-Host "  (No error message received either - protocol violation)"
        exit 1
    }
    
    # MUST have non-empty text in final
    $finalText = Get-JsonNestedProperty -JsonObj $final -ParentName "payload" -ChildName "text"
    if ([string]::IsNullOrWhiteSpace($finalText)) {
        Write-Host "FAIL: Final agent_text payload.text is empty or missing."
        Write-Host "  This indicates Gateway sent empty success instead of error."
        Write-Host "  Check LLM service configuration and API keys."
        Write-Host "  Check Gateway error propagation logic."
        exit 1
    }
    
    # Partials and agent_state are OPTIONAL
    if ($partials.Count -lt 1) { 
        Write-Host "INFO: No agent_text_partial messages received (optional, OK)."
    }
    if (-not $gotSpeaking -and -not $gotIdle) {
        Write-Host "INFO: No agent_state messages received (optional, OK)."
    }
    
    Write-Host ""
    Write-Host "PASS: All validations successful"
    Write-Host ""
    Write-Host "Final agent_text (len=$($finalText.Length)):"
    Write-Host $finalText
    Write-Host ""
    
    exit 0

}
finally {
    try {
        if ($ws.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
            $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", [System.Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
        }
    }
    catch { }
    $ws.Dispose()
}
