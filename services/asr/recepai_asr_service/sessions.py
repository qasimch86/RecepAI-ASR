from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple


class SessionNotFound(Exception):
    pass


class SequenceConflict(Exception):
    pass


class AlreadyFinalized(Exception):
    pass


class TooLarge(Exception):
    pass


@dataclass
class AsrSessionState:
    asr_session_id: str
    created_at: datetime
    expires_at: datetime
    format: str
    sample_rate: int
    channels: int
    audio: bytearray = field(default_factory=bytearray)
    last_sequence: int = -1
    chunk_count: int = 0
    finalized: bool = False
    max_bytes: int = 5 * 1024 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SessionStore:
    def __init__(self, ttl_seconds: int = 60, max_bytes_default: int = 5 * 1024 * 1024):
        self._sessions: Dict[str, AsrSessionState] = {}
        self.ttl_seconds = ttl_seconds
        self.max_bytes_default = max_bytes_default

    def cleanup_expired(self) -> None:
        now = _now()
        expired = [sid for sid, s in self._sessions.items() if s.expires_at <= now]
        for sid in expired:
            self._sessions.pop(sid, None)

    def active_session_count(self) -> int:
        """Return count of active (non-expired, non-finalized) sessions.

        Read-only: does not expose internal session storage.
        """

        self.cleanup_expired()
        # Iterate over a snapshot view to avoid issues if the dict changes
        # during iteration in concurrent environments.
        sessions = list(self._sessions.values())
        return sum(1 for s in sessions if not s.finalized)

    def start_session(self, session_id: str, turn_id: Optional[str], fmt: str, sample_rate: int, channels: int) -> AsrSessionState:
        if fmt != "pcm16":
            raise ValueError("Only format 'pcm16' is supported")
        self.cleanup_expired()
        sid = str(uuid.uuid4())
        now = _now()
        state = AsrSessionState(
            asr_session_id=sid,
            created_at=now,
            expires_at=now,
            format=fmt,
            sample_rate=sample_rate,
            channels=channels,
        )
        # Set expiry using ttl_seconds
        state.expires_at = datetime.fromtimestamp(time.time() + self.ttl_seconds, tz=timezone.utc)
        state.max_bytes = self.max_bytes_default
        self._sessions[sid] = state
        return state

    def add_chunk(self, asr_session_id: str, sequence: int, is_last: bool, audio_b64: str) -> Tuple[str, float]:
        self.cleanup_expired()
        s = self._sessions.get(asr_session_id)
        if not s:
            raise SessionNotFound()
        if s.finalized:
            raise AlreadyFinalized()
        if sequence != s.last_sequence + 1:
            raise SequenceConflict()

        try:
            chunk = base64.b64decode(audio_b64, validate=True)
        except Exception:
            raise ValueError("invalid_base64")

        if len(s.audio) + len(chunk) > s.max_bytes:
            raise TooLarge()

        s.audio.extend(chunk)
        s.last_sequence = sequence
        s.chunk_count += 1

        partial_text = f"[mock-asr partial] chunks={s.chunk_count} bytes={len(s.audio)}"
        stability = min(0.95, 0.2 + 0.1 * s.chunk_count) if s.chunk_count > 0 else 0.2
        return partial_text, stability

    def finalize(self, asr_session_id: str) -> Tuple[bytes, str, int, int, int]:
        self.cleanup_expired()
        s = self._sessions.get(asr_session_id)
        if not s:
            raise SessionNotFound()
        if s.finalized:
            raise AlreadyFinalized()

        s.finalized = True
        audio_bytes = bytes(s.audio)
        return audio_bytes, s.format, s.sample_rate, s.channels, s.chunk_count
