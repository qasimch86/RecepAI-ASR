import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Directory layout
DIRS = [
    ROOT / "gateway" / "RecepAI.VoiceGateway",
    ROOT / "services" / "asr" / "recepai_asr_service",
    ROOT / "services" / "llm" / "recepai_llm_orchestrator",
    ROOT / "services" / "tts" / "recepai_tts_service",
    ROOT / "services" / "rag" / "recepai_rag_service",
    ROOT / "shared" / "dotnet" / "RecepAI.Shared",
    ROOT / "shared" / "python" / "recepai_shared",
    ROOT / "infra" / "k8s",
    ROOT / "infra" / "helm",
    ROOT / "infra" / "env" / "dev",
    ROOT / "infra" / "env" / "staging",
    ROOT / "infra" / "env" / "prod",
    ROOT / "docs",
]

README_TOP = """# RecepAI Voice Stack

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
"""

NFRS_MD = """# Phase 0 Non-Functional Requirements

- Scale: design for 10k–100k concurrent sessions with multi-node horizontal scaling.
- Latency: < 500–800 ms from end-of-speech to first audio chunk.
- Availability: 99.9%+ for the voice path.
- Platform: Kubernetes, Redis, managed Postgres; stateless services; multi-region future-safe.
"""

ARCH_MD = """# Architecture

## Overview
High-level layout of gateway, Python services, shared libraries, and infra.

## Components
VoiceGateway (ASP.NET Core), ASR, LLM Orchestrator, TTS, RAG, shared libraries.

## Data Flow (Client <-> Gateway <-> Python services <-> VoiceAgent)
Sequence from client input through Gateway to services and back to client.

## Deployment Model
Kubernetes-based deployment with Helm charts and environment overlays.

## Multi-Region Strategy
Future-safe design for active-active or active-passive multi-region setups.
"""

GITIGNORE = """# .NET / Visual Studio
[Bb]in/
[Oo]bj/
*.user
*.suo
*.userosscache
*.sln.docstates
.vs/
*.cache
*.log

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.env/
.venv/
venv/
ENV/

# Node
node_modules/

# VS Code
.vscode/

# OS junk
.DS_Store
Thumbs.db
ehthumbs.db
Icon?

# Coverage / test artifacts
coverage/
.dist/

# Temporary files
*.tmp
*.swp
"""

# Per-folder placeholder README content
PLACEHOLDERS = {
    ROOT / "gateway" / "RecepAI.VoiceGateway" / "README.md": "# RecepAI.VoiceGateway\n\nPlaceholder for the ASP.NET Core Voice Gateway project.\n",
    ROOT / "services" / "asr" / "recepai_asr_service" / "README.md": "# recepai_asr_service\n\nPlaceholder for ASR FastAPI service.\n",
    ROOT / "services" / "llm" / "recepai_llm_orchestrator" / "README.md": "# recepai_llM_orchestrator\n\nPlaceholder for LLM Orchestrator FastAPI service.\n",
    ROOT / "services" / "tts" / "recepai_tts_service" / "README.md": "# recepai_tts_service\n\nPlaceholder for TTS FastAPI service.\n",
    ROOT / "services" / "rag" / "recepai_rag_service" / "README.md": "# recepai_rag_service\n\nPlaceholder for optional RAG service.\n",
    ROOT / "shared" / "dotnet" / "RecepAI.Shared" / "README.md": "# RecepAI.Shared (.NET)\n\nPlaceholder for .NET shared library (DTOs, correlation utils, etc.).\n",
    ROOT / "shared" / "python" / "recepai_shared" / "README.md": "# recepai_shared (Python)\n\nPlaceholder for Python shared package (models, config).\n",
    ROOT / "infra" / "k8s" / "README.md": "# k8s Manifests\n\nPlace raw Kubernetes manifests for services and infrastructure here.\n",
    ROOT / "infra" / "helm" / "README.md": "# Helm Charts\n\nPlace Helm charts (one per service/component) here.\n",
    ROOT / "infra" / "env" / "dev" / "README.md": "# Dev Environment\n\nEnvironment-specific values and overlays for development.\n",
    ROOT / "infra" / "env" / "staging" / "README.md": "# Staging Environment\n\nEnvironment-specific values and overlays for staging.\n",
    ROOT / "infra" / "env" / "prod" / "README.md": "# Prod Environment\n\nEnvironment-specific values and overlays for production.\n",
}

def ensure_dirs():
    for d in DIRS:
        d.mkdir(parents=True, exist_ok=True)

def write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def main():
    ensure_dirs()

    # Top-level files
    write_text(ROOT / "README.md", README_TOP)
    write_text(ROOT / ".gitignore", GITIGNORE)

    # Docs
    write_text(ROOT / "docs" / "NFRS.md", NFRS_MD)
    write_text(ROOT / "docs" / "ARCHITECTURE.md", ARCH_MD)

    # Folder placeholders
    for p, text in PLACEHOLDERS.items():
        write_text(p, text)

    print("RecepAI scaffold created under:", ROOT)
    print("Directories and placeholders are ready.")

if __name__ == "__main__":
    main()