import asyncio
import logging

import aiohttp

from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from ..agent.runtime import run_turn
from ..context.store import get_session

logger = logging.getLogger(__name__)

REST_API_URL = "http://localhost:8787"


class AgentRuntimeProcessor(FrameProcessor):
    """Bridges the voice pipeline to the existing Agent Runtime.

    Sits where an LLM service normally would: it takes the STT's finalized
    transcript, calls the exact same `run_turn()` used by the text chat (same
    registry, same session store, same Claude tool-use + keyword fallback),
    and pushes the reply downstream as a TextFrame for TTS to speak.

    If the turn produced a UI action, it's reported to the main REST API
    (a separate process on :8787) so the frontend's existing polling can pick
    it up and drive the product the same way a chat-triggered action does.
    """

    def __init__(self, visitor_id: str):
        super().__init__()
        self._visitor_id = visitor_id

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            session = get_session(self._visitor_id)
            try:
                result = await asyncio.to_thread(run_turn, frame.text, session)
            except Exception:
                logger.exception("run_turn failed for visitor %s", self._visitor_id)
                result = {"reply": "Sorry, I lost my train of thought — could you say that again?"}

            action = result.get("action")
            if action:
                asyncio.create_task(self._report_action(action))

            await self.push_frame(TextFrame(result["reply"]), direction)
            return

        await self.push_frame(frame, direction)

    async def _report_action(self, action: dict) -> None:
        try:
            async with aiohttp.ClientSession() as http:
                await http.post(
                    f"{REST_API_URL}/internal/voice-action",
                    json={"visitorId": self._visitor_id, "action": action},
                    timeout=aiohttp.ClientTimeout(total=3),
                )
        except Exception:
            logger.exception("Failed to report voice action for visitor %s", self._visitor_id)
