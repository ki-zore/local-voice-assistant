"""Pipecat FrameProcessor bridging Whisper STT, ReceptionistAgent, and Piper TTS."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    TranscriptionFrame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame,
    InterruptionFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from voice.receptionist.agent import ReceptionistAgent

logger = logging.getLogger("voice_assistant.voice_processor")


class ReceptionistVoiceProcessor(FrameProcessor):
    """Pipeline processor that routes speech transcriptions into ReceptionistAgent

    and streams spoken responses to Text-to-Speech (Piper).
    """

    def __init__(
        self,
        agent: ReceptionistAgent,
        greeting_text: Optional[str] = None,
        verbose: bool = True,
    ) -> None:
        super().__init__()
        self.agent = agent
        self.verbose = verbose
        self.greeting_text = greeting_text or "Hello! Thank you for calling Demo Cafe. How can I help you today?"
        self._greeting_sent: bool = False
        self._is_responding: bool = False

        # Latency tracking telemetry
        self.turn_latencies: List[Dict[str, Any]] = []

    async def send_greeting(self) -> None:
        """Send the initial receptionist greeting over TTS and log it to call transcript."""
        if self._greeting_sent:
            return

        self._greeting_sent = True
        logger.info("[CALL GREETING] %s", self.greeting_text)

        # Append greeting to call transcript document in MongoDB
        if self.agent.call_id:
            try:
                await self.agent.backend.append_transcript_turn(
                    call_id=self.agent.call_id,
                    speaker="assistant",
                    text=self.greeting_text,
                )
            except Exception as e:
                logger.warning("Failed to record greeting transcript: %s", e)

        # Push greeting down to TTS
        await self.push_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
        await self.push_frame(TextFrame(text=self.greeting_text), FrameDirection.DOWNSTREAM)
        await self.push_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Handle incoming pipeline frames, transcribing text and generating spoken replies."""
        await super().process_frame(frame, direction)

        if isinstance(frame, InterruptionFrame):
            logger.info("[VOICE] User barge-in / interruption detected!")
            self._is_responding = False
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            user_text = (frame.text or "").strip()
            if not user_text:
                await self.push_frame(frame, direction)
                return

            t_start = time.perf_counter()
            self._is_responding = True

            logger.info("[USER SPOKE] '%s'", user_text)
            if self.verbose:
                print(f"\n[Caller]: {user_text}")

            try:
                # Call the Phase 2 ReceptionistAgent engine (handles tool calling loop & DB)
                assistant_reply = await self.agent.respond(user_text)
                turn_dur_ms = (time.perf_counter() - t_start) * 1000

                ttft_ms = self.agent.ttft_history_ms[-1] if self.agent.ttft_history_ms else turn_dur_ms
                total_llm_ms = self.agent.total_duration_history_ms[-1] if self.agent.total_duration_history_ms else turn_dur_ms

                self.turn_latencies.append(
                    {
                        "user_text": user_text,
                        "assistant_reply": assistant_reply,
                        "turn_duration_ms": turn_dur_ms,
                        "ttft_ms": ttft_ms,
                        "llm_total_ms": total_llm_ms,
                        "tool_calls_count": len(self.agent.recorded_tool_calls),
                    }
                )

                if self.verbose:
                    print(f"[Receptionist]: {assistant_reply}")
                    print(f"  └─ Turn Latency: {turn_dur_ms:.1f}ms (TTFT: {ttft_ms:.1f}ms, LLM: {total_llm_ms:.1f}ms)")

                # Forward clean spoken text to Piper TTS for audio synthesis
                if assistant_reply:
                    await self.push_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
                    await self.push_frame(TextFrame(text=assistant_reply), FrameDirection.DOWNSTREAM)
                    await self.push_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)

            except Exception as exc:
                logger.error("Error processing user speech in receptionist agent: %s", exc, exc_info=True)
                error_msg = "I'm sorry, I encountered a temporary issue. Could you please repeat that?"
                await self.push_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
                await self.push_frame(TextFrame(text=error_msg), FrameDirection.DOWNSTREAM)
                await self.push_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)
            finally:
                self._is_responding = False

            # We consumed and processed the transcription
            return

        # Forward all other frames downstream
        await self.push_frame(frame, direction)
