"""The hosted booking page, rendered from business.yaml and live availability. No web framework
needed here, so it is easy to test."""

from __future__ import annotations

import html
from datetime import datetime, timedelta

from .config import DAY_KEYS

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def hours_rows(business) -> str:
    """Group consecutive days with the same hours: 'Monday – Friday · 10:00 – 20:00'."""
    groups: list[list] = []
    for i, key in enumerate(DAY_KEYS):
        raw = business.hours.get(key, "closed")
        if groups and groups[-1][2] == raw:
            groups[-1][1] = i
        else:
            groups.append([i, i, raw])
    rows = []
    for a, b, raw in groups:
        days = DAY_NAMES[a] if a == b else f"{DAY_NAMES[a]} – {DAY_NAMES[b]}"
        shown = "Closed" if str(raw).strip().lower() == "closed" else str(raw).replace("-", " – ")
        rows.append(f"<tr><td>{html.escape(days)}</td><td>{html.escape(shown)}</td></tr>")
    return "".join(rows)


def next_slots(business, calendar, limit: int = 4, now: datetime | None = None) -> tuple[str, list[str]]:
    """Real availability for the page's 'next available' card: label and up to `limit` times."""
    today = (now or datetime.now(business.tz)).date()
    for offset in range(0, business.max_days_ahead + 1):
        day = today + timedelta(days=offset)
        try:
            slots = calendar.free_slots(day)
        except Exception:
            return "", []
        if slots:
            when = "Today" if offset == 0 else "Tomorrow" if offset == 1 else slots[0].strftime("%A %d %B")
            times = [s.strftime("%I:%M %p").lstrip("0") for s in slots]
            return f"{when}, {times[0]}", times[:limit]
    return "", []


def render_site(template: str, business, calendar, now: datetime | None = None) -> str:
    e = html.escape
    first = business.services[0] if business.services else None
    label, times = next_slots(business, calendar, now=now)
    if label and first:
        chips = "".join(f'<i class="{"on" if i == 0 else ""}">{e(t)}</i>' for i, t in enumerate(times))
        card = (f'<div class="slotcard" aria-hidden="true"><small>Next available</small><b>{e(label)}</b>'
                f'<span>{e(first.name)} · {first.minutes} min · {e(first.price)}</span><div class="chips">{chips}</div></div>')
    else:
        card = ""
    services = "".join(f'<div class="card"><b>{e(s.name)}</b><span>{e(s.notes)}</span><em>{e(s.price)} · {s.minutes} min</em></div>'
                       for s in business.services)
    highlights = "".join(f"<span>{e(h)}</span>" for h in business.highlights)
    return (template.replace("{{BUSINESS_NAME}}", e(business.name)).replace("{{PHONE}}", e(business.phone))
            .replace("{{ADDRESS}}", e(business.address))
            .replace("{{TAGLINE}}", e(business.tagline or f"Welcome to {business.name}."))
            .replace("{{INTRO}}", e(business.intro or "Ask a question or book an appointment, any time of day."))
            .replace("{{HIGHLIGHTS}}", highlights).replace("{{SLOTCARD}}", card)
            .replace("{{SERVICES}}", services).replace("{{HOURS_ROWS}}", hours_rows(business)))
