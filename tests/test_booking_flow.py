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


def test_slots_offered_must_fit_the_whole_service(business, calendar, store):
    """A 45-minute cleaning on a 30-minute grid needs two slots, and must end before closing.

    Regression: 9:00 was offered for a cleaning with 9:30 already booked, and book_appointment
    then failed with "slot no longer free" after the visitor had given their details."""
    cid, ex = executor(business, calendar, store)
    tomorrow = (NOW + timedelta(days=1)).date()           # Friday, open 10:00-20:00
    grid = calendar.free_slots(tomorrow)
    busy = grid[1]                                        # 10:30; blocks a 45-min booking at 10:00
    calendar.events.append({"start": busy, "minutes": business.slot_minutes, "title": "Existing appointment"})

    # book_appointment must judge the whole 45 minutes itself, whatever was asked of the calendar:
    # 10:00 is on the free 30-minute grid, but a cleaning there would run into the 10:30 appointment.
    assert grid[0] in calendar.free_slots(tomorrow)
    refused = ex.run("book_appointment", {"name": "Asha Verma", "phone": "+91 98765 43210",
                                          "service": "Cleaning", "start": grid[0].isoformat()})
    assert "not available" in refused["error"], refused
    assert refused["slots_readable"] and grid[0].isoformat() not in refused["slots"]

    # The invariant: every time the agent offers for a service can actually be booked for it.
    cleaning = ex.run("get_available_slots", {"date": tomorrow.isoformat(), "service": "Cleaning"})
    for start in cleaning["slots"]:
        out = ex.run("book_appointment", {"name": "Asha Verma", "phone": "+91 98765 43210",
                                          "service": "Cleaning", "start": start})
        assert out.get("booked"), f"offered {start} for a cleaning but could not book it: {out}"
        assert out["minutes"] == 45
        break

    consult = ex.run("get_available_slots", {"date": tomorrow.isoformat(), "service": "Consultation"})
    assert consult["minutes"] == 30 and cleaning["minutes"] == 45
    # 10:00 fits a 30-minute consultation but not a 45-minute cleaning.
    assert grid[0].isoformat() in consult["slots"]
    assert grid[0].isoformat() not in cleaning["slots"]
    assert busy.isoformat() not in consult["slots"] and busy.isoformat() not in cleaning["slots"]

    # A 60-minute whitening cannot start in the last half hour before the 20:00 close.
    whitening = ex.run("get_available_slots", {"date": tomorrow.isoformat(), "service": "Whitening"})
    assert whitening["slots_readable"][-1] == "7:00 PM"
    assert grid[-1].isoformat() in consult["slots"]        # 7:30 PM is still fine for 30 minutes
    refused = ex.run("book_appointment", {"name": "Asha Verma", "phone": "+91 98765 43210",
                                          "service": "Whitening", "start": grid[-1].isoformat()})
    assert "not available" in refused["error"] and refused["slots_readable"]


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


def test_history_is_trimmed_without_splitting_tool_calls():
    msgs = []
    for i in range(30):                      # 30 turns of user → assistant(tool) → user(result) → assistant(text)
        msgs += [{"role": "user", "content": f"q{i}"},
                 {"role": "assistant", "content": [tool("get_available_slots", f"t{i}", date="2026-10-23")]},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": "{}"}]},
                 {"role": "assistant", "content": [text("ok")]}]
    trimmed = Receptionist._trim(msgs, keep=10)
    assert len(trimmed) <= 10 and trimmed[0]["role"] == "user" and isinstance(trimmed[0]["content"], str)
    assert trimmed[-1] is msgs[-1]
    assert Receptionist._trim(msgs[:3], keep=10) == msgs[:3]


def test_model_blocks_are_reduced_to_api_fields():
    class Block:
        def model_dump(self):
            return {"type": "text", "text": "hi", "citations": None}
    assert Receptionist._plain(Block()) == {"type": "text", "text": "hi"}
    assert Receptionist._plain({"type": "tool_use", "id": "t1", "name": "save_lead", "input": {"name": "A"}, "extra": 1}) == \
        {"type": "tool_use", "id": "t1", "name": "save_lead", "input": {"name": "A"}}


def test_booking_page_renders_from_business_file(business, calendar):
    from pathlib import Path
    from frontdesk.page import hours_rows, next_slots, render_site
    assert hours_rows(business) == ("<tr><td>Monday – Friday</td><td>10:00 – 20:00</td></tr>"
                                    "<tr><td>Saturday</td><td>10:00 – 18:00</td></tr>"
                                    "<tr><td>Sunday</td><td>Closed</td></tr>")
    label, times = next_slots(business, calendar, now=NOW)       # 21:30 Thursday → nothing left today
    assert label == "Tomorrow, 10:00 AM" and times == ["10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM"]
    template = (Path(__file__).resolve().parents[1] / "frontdesk/static/site.html").read_text()
    page = render_site(template, business, calendar, now=NOW)
    assert "{{" not in page
    assert "Gentle, modern dentistry" in page and "Tomorrow, 10:00 AM" in page
    assert page.count('<div class="card">') == 4 and "₹8,000 · 60 min" in page
    assert "5 min from Green Park metro" in page and "Bright Smile Dental" in page


def test_tool_loop_is_bounded(business, calendar, store):
    tomorrow = (NOW + timedelta(days=1)).date().isoformat()
    script = [[tool("get_available_slots", f"t{i}", date=tomorrow)] for i in range(10)]
    client = ScriptedClient(ScriptedMessages(script))
    bot = Receptionist(business, calendar, store, client, "scripted", now=lambda: NOW)
    cid = store.new_conversation()
    reply = bot.reply(cid, "hi")
    assert len(client.messages.calls) == 7            # MAX_TOOL_ROUNDS + 1
    assert "team member" in reply
