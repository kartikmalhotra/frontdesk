"""Calendar backends: a fake one for demos and tests, and Google Calendar for real use.

Both expose the same three operations the agent needs:
  free_slots(day) -> list of ISO start times that are open
  is_free(start, minutes) -> bool
  book(start, minutes, title, description) -> event id
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Protocol

from .config import Business, DAY_KEYS


class Calendar(Protocol):
    def free_slots(self, day: date) -> list[datetime]: ...
    def is_free(self, start: datetime, minutes: int) -> bool: ...
    def book(self, start: datetime, minutes: int, title: str, description: str) -> str: ...


def _day_slots(business: Business, day: date) -> list[datetime]:
    """All slot start times inside opening hours for a given day."""
    hours = business.open_hours(DAY_KEYS[day.weekday()])
    if not hours:
        return []
    start_s, end_s = hours
    tz = business.tz
    start = datetime.combine(day, time.fromisoformat(start_s), tz)
    end = datetime.combine(day, time.fromisoformat(end_s), tz)
    out, cur = [], start
    step = timedelta(minutes=business.slot_minutes)
    while cur + step <= end:
        out.append(cur)
        cur += step
    return out


def _earliest_allowed(business: Business, now: datetime) -> datetime:
    return now + timedelta(hours=business.booking_lead_hours)


class FakeCalendar:
    """In-memory calendar. Pre-books a few slots so the demo looks lived-in."""

    def __init__(self, business: Business, now: datetime | None = None, prebook: bool = True):
        self.business = business
        self._now = now
        self.events: list[dict] = []
        if prebook:
            self._seed()

    def now(self) -> datetime:
        return self._now or datetime.now(self.business.tz)

    def _seed(self) -> None:
        # Take a couple of popular slots on each of the next three open days.
        day, taken = self.now().date(), 0
        while taken < 3:
            day += timedelta(days=1)
            slots = _day_slots(self.business, day)
            if not slots:
                continue
            for idx in (1, len(slots) // 2, len(slots) - 2):
                if 0 <= idx < len(slots):
                    self.events.append({"start": slots[idx], "minutes": self.business.slot_minutes,
                                        "title": "Existing appointment"})
            taken += 1

    def is_free(self, start: datetime, minutes: int) -> bool:
        end = start + timedelta(minutes=minutes)
        for ev in self.events:
            ev_end = ev["start"] + timedelta(minutes=ev["minutes"])
            if start < ev_end and ev["start"] < end:
                return False
        return True

    def free_slots(self, day: date) -> list[datetime]:
        earliest = _earliest_allowed(self.business, self.now())
        latest_day = self.now().date() + timedelta(days=self.business.max_days_ahead)
        if day > latest_day:
            return []
        return [s for s in _day_slots(self.business, day)
                if s >= earliest and self.is_free(s, self.business.slot_minutes)]

    def book(self, start: datetime, minutes: int, title: str, description: str) -> str:
        if not self.is_free(start, minutes):
            raise ValueError("slot no longer free")
        event_id = f"fake-{len(self.events) + 1}"
        self.events.append({"id": event_id, "start": start, "minutes": minutes,
                            "title": title, "description": description})
        return event_id


class GoogleCalendar:
    """Google Calendar through a service account that the clinic's calendar is shared with."""

    def __init__(self, business: Business, calendar_id: str, service_account_file: str):
        from google.oauth2 import service_account  # imported here so tests need no google libs
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=["https://www.googleapis.com/auth/calendar"])
        self.business = business
        self.calendar_id = calendar_id
        self.service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    def now(self) -> datetime:
        return datetime.now(self.business.tz)

    def _busy(self, day_start: datetime, day_end: datetime) -> list[tuple[datetime, datetime]]:
        body = {"timeMin": day_start.isoformat(), "timeMax": day_end.isoformat(),
                "timeZone": self.business.timezone, "items": [{"id": self.calendar_id}]}
        resp = self.service.freebusy().query(body=body).execute()
        out = []
        for b in resp["calendars"][self.calendar_id].get("busy", []):
            out.append((datetime.fromisoformat(b["start"]).astimezone(self.business.tz),
                        datetime.fromisoformat(b["end"]).astimezone(self.business.tz)))
        return out

    def is_free(self, start: datetime, minutes: int) -> bool:
        end = start + timedelta(minutes=minutes)
        for b_start, b_end in self._busy(start, end):
            if start < b_end and b_start < end:
                return False
        return True

    def free_slots(self, day: date) -> list[datetime]:
        slots = _day_slots(self.business, day)
        if not slots:
            return []
        earliest = _earliest_allowed(self.business, self.now())
        latest_day = self.now().date() + timedelta(days=self.business.max_days_ahead)
        if day > latest_day:
            return []
        busy = self._busy(slots[0], slots[-1] + timedelta(minutes=self.business.slot_minutes))
        out = []
        for s in slots:
            if s < earliest:
                continue
            e = s + timedelta(minutes=self.business.slot_minutes)
            if all(not (s < b_end and b_start < e) for b_start, b_end in busy):
                out.append(s)
        return out

    def book(self, start: datetime, minutes: int, title: str, description: str) -> str:
        if not self.is_free(start, minutes):
            raise ValueError("slot no longer free")
        end = start + timedelta(minutes=minutes)
        event = {"summary": title, "description": description,
                 "start": {"dateTime": start.isoformat(), "timeZone": self.business.timezone},
                 "end": {"dateTime": end.isoformat(), "timeZone": self.business.timezone}}
        created = self.service.events().insert(calendarId=self.calendar_id, body=event).execute()
        return created["id"]


def make_calendar(business: Business, settings) -> Calendar:
    if settings.calendar_backend == "google":
        return GoogleCalendar(business, settings.google_calendar_id, settings.google_service_account_file)
    return FakeCalendar(business)
