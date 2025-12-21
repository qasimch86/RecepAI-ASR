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

Note: This repo currently contains placeholders only. Service logic and projects will be added later.
