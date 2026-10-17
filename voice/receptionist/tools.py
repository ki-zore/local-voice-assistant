"""Tool definitions, argument validation, confirmation gates, and plain-English handlers."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from voice.receptionist.backend_client import BackendClient

logger = logging.getLogger("voice_assistant.tools")

AFFIRMATIVE_WORDS = {
    "yes", "yeah", "yep", "yup", "sure", "correct", "that's right", "thats right",
    "please do", "confirm", "confirmed", "please confirm", "go ahead", "sounds good",
    "perfect", "ok", "okay", "right", "yes please", "absolutely", "definitely", "y", "ya",
}

NEGATIVE_WORDS = {
    "no", "nope", "nah", "don't", "dont", "wait", "cancel", "wrong", "change", "stop", "nevermind",
}

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check if a dining table is open for a party size, date, and time. Call this whenever the customer asks about availability or requests a reservation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format (e.g. 2026-10-20)",
                    },
                    "time": {
                        "type": "string",
                        "description": "Start time in 24-hour HH:MM format (e.g. 19:00)",
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of guests (must be at least 1)",
                    },
                },
                "required": ["date", "party_size"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_table",
            "description": (
                "Reserve a table for the customer. Call this ONLY after reading back the details "
                "to the customer and getting their explicit confirmation ('yes'). NEVER call this on the first turn when details are provided; check availability first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "Full name of the guest",
                    },
                    "customer_phone": {
                        "type": "string",
                        "description": "Customer telephone number",
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of guests",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format",
                    },
                    "time": {
                        "type": "string",
                        "description": "Time in 24-hour HH:MM format",
                    },
                },
                "required": ["customer_name", "customer_phone", "party_size", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_booking",
            "description": "Cancel an existing reservation. Requires only customer phone, date, and time. Call immediately when the customer wants to cancel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_phone": {
                        "type": "string",
                        "description": "Phone number for the reservation",
                    },
                    "date": {
                        "type": "string",
                        "description": "Booking date in YYYY-MM-DD format",
                    },
                    "time": {
                        "type": "string",
                        "description": "Booking time in 24-hour HH:MM format",
                    },
                },
                "required": ["customer_phone", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_unanswered_question",
            "description": "CRITICAL: Call this function whenever a customer asks ANY question, policy, or menu item not answered in the verified FAQs above. You must call this function before or while offering to take a message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The unanswered question asked by the customer",
                    },
                },
                "required": ["question"],
            },
        },
    },
]


def clean_spoken_text(text: str) -> str:
    """Strip emojis, markdown formatting, lists, and extra whitespace for clean speech output."""
    if not text:
        return ""

    # Remove code blocks and inline backticks
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

    # Remove markdown headers (#, ##, etc.)
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)

    # Remove bold, italics, strikethrough (*, _, ~)
    cleaned = re.sub(r"[*_~]{1,3}", "", cleaned)

    # Remove bullet points and numbered list markers
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned, flags=re.MULTILINE)

    # Remove emojis (Unicode symbols and pictographs)
    emoji_pattern = re.compile(
        "[\U00010000-\U0010ffff"
        "\U00002600-\U000027bf"
        "\U00002300-\U000023ff"
        "\U00002b50\U00002b55]+",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", cleaned)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def is_user_affirmative(user_text: str) -> bool:
    """Check if the user utterance represents a clear positive confirmation."""
    clean = re.sub(r"[^\w\s']", " ", user_text.lower()).strip()
    words = clean.split()

    # Check for negative indicators first
    if any(neg in words for neg in NEGATIVE_WORDS):
        return False

    # Check for exact keyword match or phrase match
    if clean in AFFIRMATIVE_WORDS:
        return True

    return any(aff in clean for aff in AFFIRMATIVE_WORDS)


def did_assistant_read_back(assistant_text: str) -> bool:
    """Check if the assistant provided a read-back of booking details and asked for confirmation."""
    text = assistant_text.lower()

    # Confirmation keywords
    has_confirm_prompt = any(
        kw in text
        for kw in [
            "confirm", "shall i", "should i", "is that right", "correct",
            "ready to", "book that", "lock that in", "proceed",
            "would you like", "can i book", "may i book", "book this", "go ahead",
        ]
    )

    # Detail indicators (must mention at least 2 of these: party, time/date, name, phone)
    detail_count = 0
    if any(p in text for p in ["table for", "party of", "guests", "people", "table"]):
        detail_count += 1
    if any(t in text for t in ["at ", ":", "am", "pm", "o'clock", "18", "19", "20", "15", "14"]):
        detail_count += 1
    if any(d in text for d in ["on ", "tomorrow", "tonight", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "2026", "october"]):
        detail_count += 1
    if any(n in text for n in ["under", "name", "for "]):
        detail_count += 1

    return has_confirm_prompt and (detail_count >= 1)


class ToolHandler:
    """Executes tools against the backend client with code-level validation and safety gates."""

    def __init__(self, backend_client: BackendClient, business_id: str, call_id: Optional[str] = None) -> None:
        self.backend = backend_client
        self.business_id = business_id
        self.call_id = call_id

    async def execute(
        self,
        tool_name: str,
        args: Dict[str, Any],
        messages_history: List[Dict[str, Any]],
    ) -> str:
        """Validate arguments, check confirmation gate, execute tool, and return readable text."""
        logger.info("Executing tool '%s' with args %s", tool_name, args)

        if tool_name == "check_availability":
            return await self._handle_check_availability(args)
        elif tool_name == "book_table":
            return await self._handle_book_table(args, messages_history)
        elif tool_name == "cancel_booking":
            return await self._handle_cancel_booking(args)
        elif tool_name == "log_unanswered_question":
            return await self._handle_log_unanswered_question(args)
        else:
            return f"Error: Unknown tool '{tool_name}'."

    async def _handle_check_availability(self, args: Dict[str, Any]) -> str:
        date_str = str(args.get("date", "")).strip()
        time_str = str(args.get("time", "")).strip() if args.get("time") else None
        party_size = args.get("party_size")

        # Validate date
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return "Error: Date must be in YYYY-MM-DD format (e.g. 2026-10-15). Please provide the resolved date."

        # Validate time if provided
        if time_str and not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", time_str):
            return "Error: Time must be in 24-hour HH:MM format (e.g. 19:00)."

        # Validate party_size
        try:
            party_int = int(party_size)
            if party_int < 1:
                return "Error: Party size must be at least 1 guest."
        except (ValueError, TypeError):
            return "Error: Party size must be a valid number."

        res = await self.backend.check_availability(
            business_id=self.business_id,
            date=date_str,
            party_size=party_int,
            time=time_str,
        )

        if "error" in res:
            return f"Availability check failed: {res.get('message', 'Unknown error')}."

        if time_str:
            if res.get("is_available"):
                return f"Available: A table for {party_int} is open on {date_str} at {time_str}."
            else:
                alts = res.get("alternative_slots", [])
                alt_txt = f" Nearest alternative times today are: {', '.join(alts)}." if alts else ""
                return f"Unavailable: No tables for {party_int} at {time_str} on {date_str}.{alt_txt}"
        else:
            open_slots = res.get("open_slots", [])
            if open_slots:
                return f"Available slots for party of {party_int} on {date_str}: {', '.join(open_slots)}."
            return f"No open slots available for a party of {party_int} on {date_str}."

    async def _handle_book_table(
        self,
        args: Dict[str, Any],
        messages_history: List[Dict[str, Any]],
    ) -> str:
        # 1. CODE-LEVEL CONFIRMATION GATE
        # Find the last user turn and previous assistant turn
        last_user_msg = None
        prev_assistant_msg = None

        for msg in reversed(messages_history):
            role = msg.get("role")
            if role == "user" and last_user_msg is None:
                last_user_msg = msg.get("content", "")
            elif role == "assistant" and last_user_msg is not None and prev_assistant_msg is None:
                prev_assistant_msg = msg.get("content", "")

        user_confirmed = is_user_affirmative(last_user_msg or "")
        assistant_read_back = did_assistant_read_back(prev_assistant_msg or "")

        if not user_confirmed or not assistant_read_back:
            logger.warning(
                "Confirmation Gate REJECTED book_table. User affirmed: %s, Assistant read back: %s",
                user_confirmed,
                assistant_read_back,
            )
            return (
                "Error: You must read back the complete reservation details (name, party size, "
                "date, time, and phone) to the caller and receive an explicit 'yes' or positive "
                "confirmation before calling book_table. Please read back the details now and ask the caller to confirm."
            )

        # 2. Argument validation
        name = str(args.get("customer_name", "")).strip()
        phone = str(args.get("customer_phone", "")).strip()
        party_size = args.get("party_size")
        date_str = str(args.get("date", "")).strip()
        time_str = str(args.get("time", "")).strip()

        if len(name) < 2:
            return "Error: Customer name is required."

        clean_digits = re.sub(r"\D", "", phone)
        if len(clean_digits) < 6:
            return "Error: Customer phone number must have at least 6 digits."

        try:
            party_int = int(party_size)
            if party_int < 1:
                return "Error: Party size must be at least 1."
        except (ValueError, TypeError):
            return "Error: Party size must be a number."

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return "Error: Date must be YYYY-MM-DD format."

        if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", time_str):
            return "Error: Time must be 24h HH:MM format."

        res = await self.backend.book_table(
            business_id=self.business_id,
            customer_name=name,
            customer_phone=phone,
            party_size=party_int,
            date=date_str,
            time=time_str,
            call_id=self.call_id,
        )

        if "error" in res:
            alts = res.get("alternative_slots", [])
            alt_txt = f" Nearest available slots: {', '.join(alts)}." if alts else ""
            return f"Reservation conflict: {res.get('message', 'Booking failed')}.{alt_txt}"

        tbl_num = res.get("table_number", "reserved")
        bkg_id = res.get("id", "")
        return (
            f"Booking confirmed: Table {tbl_num} for {party_int} guests on {date_str} "
            f"at {time_str} under the name {name}."
        )

    async def _handle_cancel_booking(self, args: Dict[str, Any]) -> str:
        phone = str(args.get("customer_phone", "")).strip()
        date_str = str(args.get("date", "")).strip()
        time_str = str(args.get("time", "")).strip()

        clean_digits = re.sub(r"\D", "", phone)
        if len(clean_digits) < 6:
            return "Error: Please provide a valid phone number with at least 6 digits."

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return "Error: Date must be in YYYY-MM-DD format."

        if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", time_str):
            return "Error: Time must be in 24-hour HH:MM format."

        res = await self.backend.cancel_booking(
            business_id=self.business_id,
            customer_phone=phone,
            date=date_str,
            time=time_str,
        )

        if "error" in res:
            return f"Cancellation failed: {res.get('message', 'No booking found')}."

        return f"Cancelled: The reservation on {date_str} at {time_str} under phone {phone} has been cancelled."

    async def _handle_log_unanswered_question(self, args: Dict[str, Any]) -> str:
        question = str(args.get("question", "")).strip()
        if len(question) < 3:
            return "Error: Question text too short."

        if self.call_id:
            try:
                await self.backend.log_unanswered_question(self.call_id, question)
            except Exception as e:
                logger.error("Failed to log unanswered question to backend: %s", e)

        return f"Logged question '{question}' for management review."
