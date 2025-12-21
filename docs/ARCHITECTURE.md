# Architecture

## Overview
This repository hosts the Python microservices for the RecepAI voice stack (ASR, LLM orchestrator, TTS, optional RAG) and a shared infrastructure package `recepai_shared` that provides common configuration, logging, and a tracing hook. The ASP.NET Core VoiceGateway lives in a separate C# repository and orchestrates requests to these Python services.

## Components
- **recepai_asr_service**: ASR microservice (FastAPI, to be added) that will accept audio input and return transcripts.
- **recepai_llm_orchestrator**: Microservice that will coordinate with LLM provider(s) and nopCommerce VoiceAgent via HTTP for session and message handling.
- **recepai_tts_service**: Microservice that will convert text to audio for responses.
- **recepai_rag_service**: Optional RAG/embeddings microservice to enrich responses with domain knowledge.
- **recepai_shared**: Python package offering shared settings, logging helpers, and a no‑op tracing initializer.

## Folder Layout
```
C:\inetpub\wwwroot\RecepAIPython
	docs/
	services/
		asr/recepai_asr_service/
		llm/recepai_llm_orchestrator/
		tts/recepai_tts_service/
		rag/recepai_rag_service/
	shared/
		python/recepai_shared/
	.venv/
```

## Communication with VoiceGateway and nopCommerce
- The C# VoiceGateway (separate repo: `C:\Users\workq\source\repos\nopCommerce_4.90.1_Source\Gateway\RecepAI.VoiceGateway`) will call each Python microservice over HTTP. Typical calls include sending audio to ASR, requesting text generation from the LLM orchestrator, and requesting audio from TTS.
- The LLM orchestrator will call nopCommerce VoiceAgent plugin endpoints over HTTP (for example: `/api-frontend/voice-agent/session/start` and `/message`) to manage conversation sessions and exchange messages. The base URL and credentials are provided via `recepai_shared` settings.

## Future Streaming and Barge-In
In later phases, the ASR and TTS services will support streaming audio and barge‑in for low‑latency interactions. For Phase 1, we are defining clear service boundaries and request/response contracts, while keeping the implementations non‑streaming to simplify bring‑up and deployment.
