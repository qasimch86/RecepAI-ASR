# Actions (Schema + Prompts)

This folder contains versioned **assets** used by the Voice Gateway action layer.

## Purpose

- `Contracts/VoiceIntent.v1.schema.json` defines the stable JSON contract for an extracted voice intent (`intent` + `slots`).
- `Prompts/` contains the prompt assets used to instruct an LLM to emit JSON that conforms to that contract.

These files are added ahead of wiring them into runtime code (no behavior changes in this step).

## Versioning rule

- Filenames with `v1` are **immutable** once published.
- To change schema or prompt behavior, create new files with `v2` (and so on) rather than editing `v1`.
