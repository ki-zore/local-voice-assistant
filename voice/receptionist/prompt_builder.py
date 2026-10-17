"""Builds dynamic system prompts by injecting runtime business context and verified FAQs."""

from datetime import datetime
import os
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from backend.app.utils.time import get_zone_info, now_in_tz


def format_opening_hours(hours_dict: Dict[str, Any]) -> str:
    """Format opening hours into a clear, readable text block."""
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    lines = []
    for day in weekdays:
        day_sched = hours_dict.get(day)
        day_title = day.capitalize()
        if not day_sched or not day_sched.get("open") or not day_sched.get("close"):
            lines.append(f"- {day_title}: Closed")
        else:
            lines.append(f"- {day_title}: {day_sched['open']} - {day_sched['close']}")
    return "\n".join(lines)


def format_faqs(faqs_list: list) -> str:
    """Format FAQ list into Q&A bullet points."""
    if not faqs_list:
        return "No specific FAQs listed."
    lines = []
    for item in faqs_list:
        q = item.get("question", "")
        a = item.get("answer", "")
        lines.append(f"- Q: {q}\n  A: {a}")
    return "\n".join(lines)


def build_system_prompt(
    business: Dict[str, Any],
    template_path: Optional[str] = None,
    mock_now: Optional[datetime] = None,
) -> str:
    """Read the prompt template and inject business context and current datetime."""
    if template_path is None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.abspath(os.path.join(current_dir, "..", "prompts", "receptionist.md"))

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    tz_name = business.get("timezone", "Asia/Kolkata")
    if mock_now is not None:
        current_dt = mock_now
    else:
        current_dt = now_in_tz(tz_name)

    current_dt_str = current_dt.strftime("%A, %d %B %Y, %H:%M")
    opening_hours_str = format_opening_hours(business.get("opening_hours", {}))
    faqs_str = format_faqs(business.get("faqs", []))

    replacements = {
        "{{business_name}}": business.get("name", "Demo Cafe"),
        "{{timezone}}": tz_name,
        "{{current_datetime}}": current_dt_str,
        "{{opening_hours}}": opening_hours_str,
        "{{slot_minutes}}": str(business.get("slot_minutes", 60)),
        "{{booking_policy}}": business.get("booking_policy", "Standard reservation rules apply."),
        "{{menu_summary}}": business.get("menu_summary", "Seasonal cafe menu."),
        "{{faqs}}": faqs_str,
    }

    prompt = template
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)

    return prompt
