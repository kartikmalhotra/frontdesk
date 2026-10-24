"""End-to-end: hours question, slot lookup, lead capture, booking, and the guardrails."""

import json
from datetime import date, timedelta

from frontdesk.agent import Receptionist, ToolExecutor, build_system_prompt
from tests.conftest import NOW
from tests.scripted_model import ScriptedClient, ScriptedMessages, text, tool


def executor(business, calendar, store):
    cid = store.new_conversation()
    return cid, ToolExecutor(business, calendar, store, cid, lambda: NOW)


def test_system_prompt_only_contains_file_facts(business):
    prompt = build_system_prompt(business, NOW)
    assert "Bright Smile Dental" in prompt
    assert "₹1,500" in prompt
    assert "Never give medical" in prompt
    assert "2026-10-22" in prompt


def test_slots_respect_hours_lead_time_and_closed_days(business, calendar, store):
    _, ex = executor(business, calendar, store)
    tomorrow = (NOW + timedelta(days=1)).date()           # Friday, open 10-20
    out = ex.run("get_available_slots", {"date": tomorrow.isoformat()})
    assert out["open"] and out["slots"]
    assert out["slots_readable"][0] == "10:00 AM" and out["slots_readable"][-1] == "7:30 PM"
    assert len(out["slots"]) == 20                        # 10 hours of 30-minute slots
    sunday = tomorrow + timedelta(days=2)
    assert sunday.strftime("%A") == "Sunday"
    out = ex.run("get_available_slots", {"date": sunday.isoformat()})
    assert out["open"] is False and out["slots"] == []
    # Tonight, after hours: lead time of 2 hours pushes everything to tomorrow.
    out = ex.run("get_available_slots", {"date": NOW.date().isoformat()})
    assert out["slots"] == []
    out = ex.run("get_available_slots", {"date": "2020-01-01"})
    assert "past" in out["error"]
    out = ex.run("get_available_slots", {"date": (NOW + timedelta(days=60)).date().isoformat()})
    assert "days ahead" in out["error"]


def test_booking_requires_name_phone_known_service_and_free_slot(business, calendar, store):
    cid, ex = executor(business, calendar, store)
    tomorrow = (NOW + timedelta(days=1)).date()
    slot = ex.run("get_available_slots", {"date": tomorrow.isoformat()})["slots"][5]
    assert "phone" in ex.run("book_appointment", {"name": "Asha", "phone": "call me", "service": "Cleaning", "start": slot})["error"]
    assert "name" in ex.run("book_appointment", {"name": " ", "phone": "+91 98765 43210", "service": "Cleaning", "start": slot})["error"]
    assert "unknown service" in ex.run("book_appointment", {"name": "Asha", "phone": "+91 98765 43210", "service": "Botox", "start": slot})["error"]
    out = ex.run("book_appointment", {"name": "Asha Verma", "phone": "+91 98765 43210", "service": "cleaning", "start": slot})
    assert out["booked"] and out["service"] == "Cleaning" and out["minutes"] == 45
    # The same slot cannot be booked twice.
    again = ex.run("book_appointment", {"name": "Ravi", "phone": "+91 91234 56789", "service": "Cleaning", "start": slot})
    assert "not available" in again["error"]
    # Stored for the owner.
    bookings = store.list_bookings()
    assert len(bookings) == 1 and bookings[0]["name"] == "Asha Verma" and bookings[0]["calendar_event_id"] == "fake-1"
    assert any(l["notes"] == "booked #1" for l in store.list_leads())


def test_handoff_records_a_lead_for_staff(business, calendar, store):
    cid, ex = executor(business, calendar, store)
    out = ex.run("handoff_to_human", {"reason": "asks about a root canal cost not listed", "phone": "+91 90000 00000"})
    assert out["recorded"] and out["phone_to_call"] == business.phone
    assert store.list_leads()[0]["interest"] == "needs a human"


def test_full_conversation_through_the_agent_loop(business, calendar, store):
    """Hours → book → slots → details → confirmed, driven by a scripted model."""
    tomorrow = (NOW + timedelta(days=1)).date().isoformat()
    script = [
        [text("We're open 10 am to 8 pm Monday to Friday and until 6 pm on Saturday. Would you like to book?")],
        [tool("get_available_slots", "t1", date=tomorrow)],
        [text("Tomorrow I have 10:00 am, 10:30 am or 6:30 pm. Which suits? I'll also need your name and phone number.")],
        [tool("save_lead", "t2", name="Asha Verma", phone="+91 98765 43210", interest="Cleaning"),
         tool("book_appointment", "t3", name="Asha Verma", phone="+91 98765 43210", service="Cleaning",
              start=f"{tomorrow}T18:30:00+05:30")],
        [text("Done. Cleaning tomorrow at 6:30 pm for Asha Verma. You'll get a confirmation shortly. Free cancellation up to 24 hours before.")],
    ]
    client = ScriptedClient(ScriptedMessages(script))
    bot = Receptionist(business, calendar, store, client, "scripted", now=lambda: NOW)
    cid = store.new_conversation()

    r1 = bot.reply(cid, "what are your hours?")
    assert "10 am to 8 pm" in r1
    r2 = bot.reply(cid, "I want a cleaning tomorrow evening")
    assert "6:30 pm" in r2
    r3 = bot.reply(cid, "6:30 works. Asha Verma, +91 98765 43210")
    assert "6:30 pm" in r3 and "Asha" in r3

    # The tool results the model saw were real, not scripted: find the slots result in the transcript.
    results = [b for call in client.messages.calls for m in call["messages"]
               if isinstance(m["content"], list) for b in m["content"] if b.get("type") == "tool_result"]
    slots_result = json.loads(results[0]["content"])
    assert slots_result["open"] is True and f"{tomorrow}T18:30:00+05:30" in slots_result["slots"]
    booked_result = json.loads(results[-1]["content"])
    assert booked_result["booked"] is True and booked_result["service"] == "Cleaning"
    booking = store.list_bookings()[0]
    assert booking["service"] == "Cleaning" and booking["start"].startswith(f"{tomorrow}T18:30")
    # Conversation persisted with tool calls in it.
    saved = store.get_messages(cid)
    assert any(isinstance(m["content"], list) and any(b.get("type") == "tool_use" for b in m["content"]) for m in saved)


def test_tool_loop_is_bounded(business, calendar, store):
    tomorrow = (NOW + timedelta(days=1)).date().isoformat()
    script = [[tool("get_available_slots", f"t{i}", date=tomorrow)] for i in range(10)]
    client = ScriptedClient(ScriptedMessages(script))
    bot = Receptionist(business, calendar, store, client, "scripted", now=lambda: NOW)
    cid = store.new_conversation()
    reply = bot.reply(cid, "hi")
    assert len(client.messages.calls) == 7            # MAX_TOOL_ROUNDS + 1
    assert "team member" in reply
