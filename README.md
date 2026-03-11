# RecepAI Voice Stack

This repository scaffolds the RecepAI Voice Stack:
- C# ASP.NET Core Voice Gateway service in `gateway/RecepAI.VoiceGateway` (project to be created later in Visual Studio).
- Python microservices for ASR, LLM orchestration, TTS, and optional RAG under `services/`.
- Shared libraries for .NET (`shared/dotnet/RecepAI.Shared`) and Python (`shared/python/recepai_shared`).
- Infrastructure manifests for Kubernetes and Helm under `infra/`.
- Documentation under `docs/`.

Integration target: Designed to integrate with nopCommerce 4.9 and `Nop.Plugin.RecepAI.VoiceAgent`.

High-level pipeline:
Client -> VoiceGateway -> ASR -> LLM Orchestrator -> VoiceAgent plugin -> TTS -> Client.

## Local secrets / API keys

This repo expects secrets (for example `OPENAI_API_KEY`) to come from environment variables.

For local development, you can put keys in `.recepai.config.json` (git-ignored) at the repo root:
- Start from `recepai.config.example.json`
- Put your real values in `.recepai.config.json`

The Python services will load this file (if present) and populate missing environment variables on startup.

Note: This repo currently contains placeholders only. Service logic and projects will be added later.
