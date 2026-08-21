"""Per-turn latency telemetry.

Exists because on 2026-08-21 the question "how long before she made a sound?"
could not be answered from production logs at all. The only turn-level timing
in the log was `heard` -> `replying`, and `replying` fires after the WHOLE
response has finished streaming — so the one number available (median 9.9s)
described completion, not responsiveness, and optimising against it would have
been optimising the wrong thing.

Every stage gets its own timestamp so the four latencies can be attributed
separately: turn detection is ours, LLM first-token is the model's, TTS is
Cartesia's, and only the sum decides how the call feels.

## On naming

`time_to_first_tts_enqueue` is NOT time-to-first-audio, and is deliberately not
called that. It measures when text was handed to the TTS service — sound leaves
the speaker some unmeasured amount later. `acoustic_ttfa_ms` is the real thing
and is populated only when the pipeline actually reports first output audio;
when it is None, it is None rather than quietly falling back to the enqueue
number. Conflating the two would bake an unknown constant into every
measurement we then tuned against.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from loguru import logger


def _ms(a: Optional[float], b: Optional[float]) -> Optional[int]:
    """Milliseconds between two monotonic marks, or None if either is missing.

    None propagates on purpose: a derived latency built on a stage that never
    fired is not zero, it is unknown, and the difference matters when these
    get averaged.
    """
    if a is None or b is None:
        return None
    # round, not int: truncating turns 689.99ms into 689 and quietly biases
    # every measurement downward by up to a millisecond.
    return round((b - a) * 1000)


@dataclass
class TurnTelemetry:
    """One conversational turn, from the prospect starting to speak to the
    agent finishing its reply. Timestamps are `time.monotonic()` marks."""

    visitor_id: str
    turn_id: int

    # --- stage marks -------------------------------------------------------
    t_user_speech_start: Optional[float] = None
    t_user_speech_end: Optional[float] = None
    t_stt_final: Optional[float] = None
    t_smart_turn_verdict: Optional[float] = None
    t_turn_committed: Optional[float] = None
    t_llm_request: Optional[float] = None
    t_llm_first_token: Optional[float] = None
    t_first_tts_enqueue: Optional[float] = None
    t_first_output_audio: Optional[float] = None
    t_reply_complete: Optional[float] = None

    # --- categorical -------------------------------------------------------
    smart_turn_verdict: Optional[str] = None      # COMPLETE | INCOMPLETE
    released_by: Optional[str] = None             # settle | stall_backstop | fast_track | fast_commit
    source: str = "voice"                         # voice | chat | auto_continue
    backchannel_count: int = 0
    backchannel_suppressed_by_lead: int = 0
    consecutive_auto_beats: int = 0
    fragments: int = 0
    interrupted: bool = False
    # Named a possibility, not a fact. The prospect speaking again right after
    # the agent starts MAY mean we cut them off — or may just be an ordinary
    # interruption, which is normal conversation. Calling this `false_cutoff`
    # would assert something we cannot know without ground truth.
    early_commit_followup: bool = False

    _emitted: bool = field(default=False, repr=False)

    # --- derived -----------------------------------------------------------
    def derived(self) -> dict:
        return {
            # Ours. The 1.5-2.6s window lives here.
            "turn_detection_ms": _ms(self.t_user_speech_end, self.t_turn_committed),
            # The model's.
            "llm_first_token_ms": _ms(self.t_llm_request, self.t_llm_first_token),
            # Cartesia's, once first output audio is actually reported.
            "tts_ms": _ms(self.t_first_tts_enqueue, self.t_first_output_audio),
            # Everything before the first text reaches TTS. NOT audio.
            "time_to_first_tts_enqueue_ms": _ms(self.t_user_speech_end, self.t_first_tts_enqueue),
            # The real one. None unless the pipeline reported output audio.
            "acoustic_ttfa_ms": _ms(self.t_user_speech_end, self.t_first_output_audio),
            # What I previously mislabelled as latency.
            "ttfc_ms": _ms(self.t_user_speech_end, self.t_reply_complete),
            "user_speech_ms": _ms(self.t_user_speech_start, self.t_user_speech_end),
        }

    def mark(self, field_name: str) -> None:
        """Stamps a stage, first write wins. Later duplicates are ignored so a
        retry or a second fragment can't overwrite the true first occurrence."""
        if getattr(self, field_name, None) is None:
            setattr(self, field_name, time.monotonic())

    def emit(self) -> None:
        """One JSON line per turn. Idempotent — a turn that ends via both the
        normal path and a disconnect must not be counted twice."""
        if self._emitted:
            return
        self._emitted = True
        payload = {
            k: v for k, v in asdict(self).items()
            if not k.startswith(("t_", "_"))
        }
        payload.update(self.derived())
        logger.info("TURN_TELEMETRY " + json.dumps(payload, separators=(",", ":")))
