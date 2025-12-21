# Phase 0 Non-Functional Requirements

- Scale: design for 10k–100k concurrent sessions with multi-node horizontal scaling.
- Latency: < 500–800 ms from end-of-speech to first audio chunk.
- Availability: 99.9%+ for the voice path.
- Platform: Kubernetes, Redis, managed Postgres; stateless services; multi-region future-safe.
