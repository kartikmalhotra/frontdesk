"""The receptionist agent: a Claude model with four tools, run in a bounded loop.

Guardrails:
  - Facts come only from business.yaml (in the system prompt). Nothing else is asserted.
  - The model cannot book without a name, a phone number and a slot the calendar says is free.
  - At most MAX_TOOL_ROUNDS tool calls per user message, so a confused model cannot loop.
  - Every tool call and result is recorded in the conversation.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable

from .calendar import Calendar
from .config import Business, DAY_KEYS
from .db import Store

MAX_TOOL_ROUNDS = 6
MAX_HISTORY = 40          # messages sent to the model per turn; older ones stay in the database

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_available_slots",
        "description": "List open appointment start times for a given date. Call this before offering any time. "
                       "Dates are YYYY-MM-DD in the business's timezone.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["date"],
        },
    },
    {
        "name": "save_lead",
        "description": "Record the visitor's contact details and what they are interested in, as soon as you have "
                       "them, even if no booking happens. Call again if details change.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "phone": {"type": "string"},
                "interest": {"type": "string", "description": "What they asked about, in a few words"},
            },
            "required": ["interest"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Book a confirmed appointment. Only call after the visitor has given their name and phone "
                       "number and has explicitly agreed to a specific start time you offered.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "phone": {"type": "string"},
                "service": {"type": "string", "description": "One of the business's service names"},
                "start": {"type": "string", "description": "ISO 8601 start time with timezone offset, from get_available_slots"},
            },
            "required": ["name", "phone", "service", "start"],
        },
    },
    {
        "name": "handoff_to_human",
        "description": "Use when the visitor needs something you cannot do: medical advice, a complaint, a refund, "
                       "anything outside the business facts you were given. Records the request for staff.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}, "name": {"type": "string"}, "phone": {"type": "string"}},
            "required": ["reason"],
        },
    },
]

PHONE_RE = re.compile(r"[+\d][\d\s\-()]{7,}\d")


def build_system_prompt(business: Business, now: datetime) -> str:
    today = now.strftime("%A %d %B %Y, %H:%M")
    return f"""You are the online receptionist for {business.name}. You are chatting with a visitor on the business's website.

Current date and time: {today} ({business.timezone}).

Your job: answer questions about the business, capture the visitor's details, and book appointments.

Rules you must follow:
1. Only state facts that appear in the business details below. If something is not there (for example a service, a price, a doctor's name, an insurance scheme), say you don't have that information and offer to have the team call them back.
2. Never give medical, clinical or health advice. {business.out_of_scope}
3. Before offering any appointment time, call get_available_slots for the date. Offer at most three or four options, in plain language ("tomorrow at 6:30 pm"). Never invent a time.
4. To book you need the visitor's name, phone number, the service, and their clear yes to one specific time. Ask for what is missing, one thing at a time. Then call book_appointment.
5. After booking, confirm in one short message: service, day, time, and that they'll get a confirmation. Mention the cancellation policy in one line.
6. As soon as you learn a name or phone number, call save_lead so the team has it even if the chat ends.
7. If the visitor asks for something you can't do, call handoff_to_human and tell them the team will follow up.
8. Keep replies short: two or three sentences, like a good receptionist. No bullet lists unless listing services or prices. No emoji. Be warm, not chatty.
9. Dates: "today" is {now.strftime('%Y-%m-%d')}. Work out dates like "tomorrow" or "Friday" from that. The business is closed on days marked closed; say so and offer the next open day.

Business details:
{business.describe()}
"""


def _resolve_date(text: str, today: date) -> date | None:
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None


class ToolExecutor:
    """Runs tool calls against the calendar and the store. Pure Python, no model."""

    def __init__(self, business: Business, calendar: Calendar, store: Store, conversation_id: str,
                 now: Callable[[], datetime]):
        self.business, self.calendar, self.store, self.cid, self.now = business, calendar, store, conversation_id, now

    def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return {"error": f"unknown tool {name}"}
        try:
            return handler(**args)
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}
        except ValueError as e:
            return {"error": str(e)}

    def tool_get_available_slots(self, date: str) -> dict[str, Any]:
        today = self.now().date()
        day = _resolve_date(date, today)
        if day is None:
            return {"error": "date must be YYYY-MM-DD"}
        if day < today:
            return {"error": "that date is in the past", "today": today.isoformat()}
        if day > today + timedelta(days=self.business.max_days_ahead):
            return {"error": f"bookings open only {self.business.max_days_ahead} days ahead"}
        if not self.business.open_hours(DAY_KEYS[day.weekday()]):
            return {"date": day.isoformat(), "open": False, "slots": [],
                    "note": f"{self.business.name} is closed on {day.strftime('%A')}s"}
        slots = self.calendar.free_slots(day)
        return {"date": day.isoformat(), "open": True, "weekday": day.strftime("%A"),
                "slots": [s.isoformat() for s in slots],
                "slots_readable": [s.strftime("%I:%M %p").lstrip("0") for s in slots]}

    def tool_save_lead(self, interest: str, name: str | None = None, phone: str | None = None) -> dict[str, Any]:
        lead_id = self.store.save_lead(self.cid, name, phone, interest)
        return {"saved": True, "lead_id": lead_id}

    def tool_book_appointment(self, name: str, phone: str, service: str, start: str) -> dict[str, Any]:
        if not name.strip():
            return {"error": "name is required"}
        if not PHONE_RE.search(phone or ""):
            return {"error": "a valid phone number is required"}
        svc = self.business.service(service)
        if svc is None:
            return {"error": f"unknown service '{service}'", "services": [s.name for s in self.business.services]}
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError:
            return {"error": "start must be ISO 8601 from get_available_slots"}
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=self.business.tz)
        start_dt = start_dt.astimezone(self.business.tz)
        if start_dt not in self.calendar.free_slots(start_dt.date()):
            return {"error": "that time is not available any more; call get_available_slots again"}
        title = f"{svc.name}: {name.strip()}"
        description = f"Booked by the website receptionist.\nPhone: {phone.strip()}\nService: {svc.name} ({svc.price})"
        event_id = self.calendar.book(start_dt, svc.minutes, title, description)
        booking_id = self.store.save_booking(self.cid, name.strip(), phone.strip(), svc.name,
                                             start_dt.isoformat(), svc.minutes, event_id)
        self.store.save_lead(self.cid, name.strip(), phone.strip(), svc.name, notes=f"booked #{booking_id}")
        return {"booked": True, "booking_id": booking_id, "service": svc.name, "price": svc.price,
                "start": start_dt.isoformat(), "start_readable": start_dt.strftime("%A %d %B, %I:%M %p").replace(" 0", " "),
                "minutes": svc.minutes, "cancellation": self.business.policies.get("cancellation", "")}

    def tool_handoff_to_human(self, reason: str, name: str | None = None, phone: str | None = None) -> dict[str, Any]:
        self.store.save_lead(self.cid, name, phone, "needs a human", notes=reason)
        return {"recorded": True, "phone_to_call": self.business.phone}


class Receptionist:
    """Drives one conversation turn: user text in, assistant text out, tools in between."""

    def __init__(self, business: Business, calendar: Calendar, store: Store, client, model: str,
                 now: Callable[[], datetime] | None = None):
        self.business, self.calendar, self.store, self.client, self.model = business, calendar, store, client, model
        self.now = now or (lambda: datetime.now(business.tz))

    @staticmethod
    def _plain(block):
        """Keep only the fields the API expects back, whatever extras the SDK's objects carry.
        Thinking blocks (local models via Ollama emit them) and empty text are dropped: None."""
        b = block.model_dump() if hasattr(block, "model_dump") else dict(block)
        if b.get("type") == "tool_use":
            return {"type": "tool_use", "id": b["id"], "name": b["name"], "input": b.get("input") or {}}
        if b.get("type") == "text" and (b.get("text") or "").strip():
            return {"type": "text", "text": b["text"]}
        return None

    @staticmethod
    def _trim(messages: list[dict], keep: int = MAX_HISTORY) -> list[dict]:
        """Bound the context sent to the model. Cuts only at a plain user message, so a tool call
        is never separated from its result."""
        if len(messages) <= keep:
            return messages
        start = len(messages) - keep
        while start < len(messages) and not (messages[start]["role"] == "user"
                                             and isinstance(messages[start]["content"], str)):
            start += 1
        return messages[start:] if start < len(messages) else messages[-1:]

    def reply(self, conversation_id: str, user_text: str) -> str:
        messages = self.store.get_messages(conversation_id)
        if messages is None:
            raise KeyError("unknown conversation")
        messages.append({"role": "user", "content": user_text.strip()[:2000]})
        executor = ToolExecutor(self.business, self.calendar, self.store, conversation_id, self.now)
        system = build_system_prompt(self.business, self.now())
        if "qwen3" in self.model.lower():  # Qwen3 thinks by default; the soft switch turns it off
            system += "\n/no_think"

        final_text = ""
        for _ in range(MAX_TOOL_ROUNDS + 1):
            response = self.client.messages.create(
                model=self.model, max_tokens=1000, system=system, tools=TOOLS, messages=self._trim(messages))
            content = [p for p in (self._plain(b) for b in response.content) if p]
            if not content:  # a model that only "thought" and said nothing
                content = [{"type": "text", "text": "Sorry, could you say that again?"}]
            messages.append({"role": "assistant", "content": content})
            tool_uses = [b for b in content if b.get("type") == "tool_use"]
            final_text = " ".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            if not tool_uses or response.stop_reason != "tool_use":
                break
            results = []
            for tu in tool_uses:
                out = executor.run(tu["name"], tu.get("input") or {})
                results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": json.dumps(out)})
            messages.append({"role": "user", "content": results})
        else:
            final_text = final_text or "Let me get a team member to help with that. They'll call you back shortly."

        self.store.save_messages(conversation_id, messages)
        return final_text or "Sorry, could you say that again?"
