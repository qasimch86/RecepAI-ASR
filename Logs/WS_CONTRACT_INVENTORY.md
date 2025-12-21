# WS Contract Inventory (Repo Workspace)

Generated: 2025-12-15

Note: This workspace contains Python clients and tooling. The .NET VoiceGateway code referenced below should live in your Gateway repo. The inventory here lists Python-side assumptions and places to update in the .NET repo.

## Findings

| Path | What was found | Risk |
|---|---|---|
| scripts/ws_test_client.py | Sends/reads camelCase envelope with `type/sessionId/turnId/ts/payload`. Supports multiple client impls; uses raw TCP probe too. | Low: already aligned to camelCase `ts` on wire. |
| scripts/ws_min_connect.py | Minimal connect + ping behavior; prints first frame. | Low. |
| scripts/di_probe_runner.py | Stdlib raw RFC6455 upgrade probe for `/ws/voice` and `/ws/voice-simple`. | Low. |
| docs/WS_CLIENT_DIAGNOSTIC_REPORT.md | Mentions expectations; not normative. | Low. |
| Logs/ws_probe_matrix.md | Captured outcomes of probes; not code. | None. |

## .NET Code (apply in VoiceGateway repo)
- Envelope: Gateway/RecepAI.VoiceGateway/Realtime/WsMessageEnvelope.cs (canonical)
- WS JSON Options: Gateway/RecepAI.VoiceGateway/Realtime/WsJson.cs (existing), or use the new shared helper below
- Handler: Gateway/RecepAI.VoiceGateway/Realtime/VoiceWebSocketHandler.cs
- Diagnostics: Program.cs → `/diag/ws/contract`
- Payload DTOs: Gateway/RecepAI.VoiceGateway/Realtime/Messages/*.cs (SessionStartPayload, SessionAckPayload, AgentTextPayload, FinalTranscriptPayload, ErrorPayload)

## Action Items (VoiceGateway repo)
- Create `Realtime/WsCodec.cs` (added in this workspace for copy-paste) and route all WS Serialize/Deserialize through it.
- Replace direct `JsonSerializer.Serialize/Deserialize` in WS handlers with `WsCodec.Serialize/DeserializeEnvelope`.
- Ensure outbound uses `ts` only; inbound accepts legacy `timestamp`.
- Keep diagnostics endpoint using `WsCodec` as source of truth.
