"""Opt-in call audio capture, for turn-detection research only.

## Why this exists

The stress harness cannot tell us whether Smart Turn v3 is right, because it
has no audio — it *asserts* a verdict per segment and the pipeline believes it.
That is how a defaulted `incomplete=False` came to declare twelve mid-thought
clauses to be finished turns, which made the model look useless and led to it
being replaced by a 1.5-2.6s stopwatch. The only way to check what the model
actually says about real speech is to replay real speech through it.

## Consent

This is OFF unless RECORD_CALLS=true is explicitly set in the environment, and
it is never set in normal operation. That flag is the technical guard.

It is NOT consent. Consent is telling the people on the call, before the call,
that it is being recorded — a human step this module cannot perform and does
not pretend to. The flag exists so that recording can never happen by accident;
it does not make recording appropriate on its own.

Scope agreed for this experiment: internal calls only, no external users,
2-3 calls, short retention. RECORDING_RETENTION_NOTE below is written into the
directory so nobody finds these files later without knowing what they are.
"""

from __future__ import annotations

import os
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "recordings"

RETENTION_NOTE = """These are voice-call recordings captured ONLY to validate
Smart Turn v3 turn-detection against real speech (see call_recorder.py).

Internal participants only, recorded with their prior knowledge.
Delete once the turn-detection work is finished. Do not use for anything else.
"""


def recording_enabled() -> bool:
    """Off unless deliberately switched on. Read at call time, not import time,
    so flipping the flag doesn't need a code change."""
    return os.getenv("RECORD_CALLS", "").strip().lower() == "true"


class CallRecorder:
    """Collects audio for one call and writes a WAV at the end.

    Deliberately does no processing on the hot path — it appends bytes and
    nothing else. Anything expensive here would change the very timings this
    recording exists to measure, which would make the data worthless.
    """

    def __init__(self, visitor_id: str, sample_rate: int = 16000):
        self._visitor_id = visitor_id
        self._sample_rate = sample_rate
        self._chunks: list[bytes] = []
        self._bytes = 0

    def append(self, audio: bytes) -> None:
        self._chunks.append(audio)
        self._bytes += len(audio)

    def save(self) -> Optional[Path]:
        """Writes the WAV. Returns its path, or None if nothing was captured.

        Every failure is swallowed and logged: a research capture must never be
        able to take down the hang-up path of a real call.
        """
        if not self._chunks:
            return None
        try:
            RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
            note = RECORDINGS_DIR / "README.txt"
            if not note.exists():
                note.write_text(RETENTION_NOTE)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = RECORDINGS_DIR / f"{stamp}_{self._visitor_id[:8]}.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)          # 16-bit PCM, what the pipeline carries
                w.setframerate(self._sample_rate)
                w.writeframes(b"".join(self._chunks))
            secs = self._bytes / (self._sample_rate * 2)
            logger.info(
                f"[{self._visitor_id}] call recording saved: {path.name} "
                f"({secs:.1f}s, {self._bytes/1024:.0f}KB)"
            )
            return path
        except Exception:
            logger.exception(f"[{self._visitor_id}] failed to save call recording")
            return None
