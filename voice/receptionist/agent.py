"""I/O-independent Receptionist Agent with tool loop, latency logging, and call tracking."""

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional
import ollama

from voice.receptionist.backend_client import BackendClient
from voice.receptionist.config import get_voice_config
from voice.receptionist.prompt_builder import build_system_prompt
from voice.receptionist.tools import (
    TOOL_SCHEMAS,
    ToolHandler,
    clean_spoken_text,
)

logger = logging.getLogger("voice_assistant.agent")


class ReceptionistAgent:
    """Core conversational agent handling tool loops, prompts, and metrics."""

    def __init__(
        self,
        business_id: Optional[str] = None,
        model: Optional[str] = None,
        backend_url: Optional[str] = None,
        temperature: Optional[float] = None,
        keep_alive: Optional[str] = None,
    ) -> None:
        config = get_voice_config()
        self.business_id = business_id or config.default_business_id
        self.model = model or config.ollama_model
        self.backend_url = backend_url or config.backend_url
        self.temperature = temperature if temperature is not None else config.temperature
        self.keep_alive = keep_alive or config.ollama_keep_alive

        self.backend = BackendClient(base_url=self.backend_url)
        self.ollama_client = ollama.AsyncClient(host=config.ollama_base_url)

        self.business_data: Dict[str, Any] = {}
        self.system_prompt: str = ""
        self.messages: List[Dict[str, Any]] = []
        self.call_id: Optional[str] = None
        self.tool_handler: Optional[ToolHandler] = None

        # Latency and telemetry metrics
        self.total_llm_calls: int = 0
        self.ttft_history_ms: List[float] = []
        self.total_duration_history_ms: List[float] = []
        self.recorded_tool_calls: List[Dict[str, Any]] = []

    async def initialize(self, mock_now: Optional[datetime] = None) -> None:
        """Fetch business details, construct system prompt, and register call session."""
        logger.info("Initializing agent for business '%s' using model '%s'...", self.business_id, self.model)
        biz_resp = await self.backend.get_business(self.business_id)
        self.business_data = biz_resp.get("business", {})

        self.system_prompt = build_system_prompt(self.business_data, mock_now=mock_now)
        self.messages = [{"role": "system", "content": self.system_prompt}]

        try:
            call_resp = await self.backend.create_call(self.business_id)
            self.call_id = call_resp.get("id")
            logger.info("Created call session with ID: %s", self.call_id)
        except Exception as e:
            logger.warning("Could not register backend call session: %s", e)
            self.call_id = None

        self.tool_handler = ToolHandler(
            backend_client=self.backend,
            business_id=self.business_id,
            call_id=self.call_id,
        )

    async def respond(self, user_text: str) -> str:
        """Process user input through Ollama with automatic tool loop execution."""
        clean_user = user_text.strip()
        self.messages.append({"role": "user", "content": clean_user})

        # Append to backend call transcript
        if self.call_id:
            try:
                await self.backend.update_call(
                    call_id=self.call_id,
                    transcript_item={
                        "role": "customer",
                        "message": clean_user,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as e:
                logger.debug("Failed to append customer transcript: %s", e)

        # Loop up to 4 iterations for tool-calling
        max_iterations = 4
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            t0 = time.perf_counter()

            try:
                response = await self.ollama_client.chat(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOL_SCHEMAS,
                    options={"temperature": self.temperature},
                    keep_alive=self.keep_alive,
                )
            except Exception as exc:
                logger.error("Ollama chat API error: %s", exc)
                return "I'm having a slight connection problem. Could you please repeat that?"

            t1 = time.perf_counter()
            self.total_llm_calls += 1

            # Compute latency
            if getattr(response, "prompt_eval_duration", None):
                ttft_ms = response.prompt_eval_duration / 1e6
            else:
                ttft_ms = (t1 - t0) * 1000

            total_ms = (t1 - t0) * 1000
            self.ttft_history_ms.append(ttft_ms)
            self.total_duration_history_ms.append(total_ms)

            logger.info(
                "LLM turn finished (TTFT: %.1fms, Total: %.1fms)",
                ttft_ms,
                total_ms,
            )

            msg = response.message

            # Check if model requested tool execution
            if msg.tool_calls:
                # Convert message object to dict for message history
                assistant_tool_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": msg.tool_calls,
                }
                self.messages.append(assistant_tool_msg)

                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    tool_args = tc.function.arguments

                    t_start = time.perf_counter()
                    tool_result = await self.tool_handler.execute(
                        tool_name=tool_name,
                        args=tool_args,
                        messages_history=self.messages,
                    )
                    t_dur = (time.perf_counter() - t_start) * 1000

                    self.recorded_tool_calls.append(
                        {
                            "name": tool_name,
                            "args": tool_args,
                            "result": tool_result,
                            "duration_ms": t_dur,
                        }
                    )

                    logger.info(
                        "Tool '%s' executed in %.1fms -> %s",
                        tool_name,
                        t_dur,
                        tool_result,
                    )

                    # Append tool result to messages
                    self.messages.append(
                        {
                            "role": "tool",
                            "content": tool_result,
                            "tool_name": tool_name,
                        }
                    )

                # Continue loop so model can digest the tool output
                continue

            # No tool calls: model returned natural language text
            final_text = clean_spoken_text(msg.content or "")

            # CODE-LEVEL SAFEGUARD: Auto-log unverified inquiries if the model declined or lacked info
            if not any(t["name"] == "log_unanswered_question" for t in self.recorded_tool_calls):
                unanswered_indicators = [
                    "don't offer", "do not offer", "don't have", "do not have", "don't sell",
                    "not sure", "don't specify", "don't allow", "do not allow", "leave a message",
                    "take a message", "don't currently", "no information",
                ]
                lower_reply = final_text.lower()
                if any(ind in lower_reply for ind in unanswered_indicators):
                    logger.info("Code-level safeguard: Auto-logging unverified inquiry '%s'", clean_user)
                    t_start = time.perf_counter()
                    tool_res = await self.tool_handler.execute(
                        tool_name="log_unanswered_question",
                        args={"question": clean_user},
                        messages_history=self.messages,
                    )
                    t_dur = (time.perf_counter() - t_start) * 1000
                    self.recorded_tool_calls.append(
                        {
                            "name": "log_unanswered_question",
                            "args": {"question": clean_user},
                            "result": tool_res,
                            "duration_ms": t_dur,
                        }
                    )

            self.messages.append({"role": "assistant", "content": final_text})

            # Append to backend call transcript
            if self.call_id:
                try:
                    await self.backend.update_call(
                        call_id=self.call_id,
                        transcript_item={
                            "role": "assistant",
                            "message": final_text,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                except Exception as e:
                    logger.debug("Failed to append assistant transcript: %s", e)

            return final_text

        # If loop capped out at 4 iterations
        fallback = "I apologize for the delay. Shall I go ahead and confirm that reservation for you?"
        self.messages.append({"role": "assistant", "content": fallback})
        return fallback

    async def end_call(self, outcome: str = "completed") -> None:
        """Mark call as finished with outcome."""
        if self.call_id:
            try:
                await self.backend.update_call(
                    call_id=self.call_id,
                    outcome=outcome,
                    ended_at=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.debug("Failed to finalize call: %s", e)

    async def close(self) -> None:
        """Clean up backend client sessions."""
        await self.backend.close()
