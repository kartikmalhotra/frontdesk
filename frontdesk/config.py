"""Loads the business profile (business.yaml) and environment settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

load_dotenv()

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass
class Service:
    name: str
    minutes: int
    price: str
    notes: str = ""


@dataclass
class Business:
    name: str
    timezone: str
    phone: str
    address: str
    hours: dict[str, str]  # "mon" -> "10:00-20:00" or "closed"
    services: list[Service]
    policies: dict[str, str]
    slot_minutes: int = 30
    booking_lead_hours: int = 2
    max_days_ahead: int = 14
    email: str = ""
    out_of_scope: str = ""

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def service(self, name: str) -> Service | None:
        wanted = name.strip().lower()
        for s in self.services:
            if s.name.lower() == wanted:
                return s
        for s in self.services:
            if wanted in s.name.lower() or s.name.lower() in wanted:
                return s
        return None

    def open_hours(self, day_key: str) -> tuple[str, str] | None:
        """Return ("10:00", "20:00") for an open day, None for a closed one."""
        raw = self.hours.get(day_key, "closed")
        if not raw or str(raw).strip().lower() == "closed":
            return None
        start, end = str(raw).split("-")
        return start.strip(), end.strip()

    def describe(self) -> str:
        """Plain-text facts for the system prompt. Only what is in the file."""
        lines = [f"Business name: {self.name}", f"Phone: {self.phone}", f"Address: {self.address}"]
        if self.email:
            lines.append(f"Email: {self.email}")
        lines.append("Opening hours:")
        for key in DAY_KEYS:
            lines.append(f"  {key}: {self.hours.get(key, 'closed')}")
        lines.append("Services (name, duration, price):")
        for s in self.services:
            extra = f" — {s.notes}" if s.notes else ""
            lines.append(f"  {s.name}: {s.minutes} min, {s.price}{extra}")
        if self.policies:
            lines.append("Policies:")
            for k, v in self.policies.items():
                lines.append(f"  {k}: {v}")
        lines.append(f"Appointments are booked in {self.slot_minutes}-minute slots, at least "
                     f"{self.booking_lead_hours} hours ahead and up to {self.max_days_ahead} days ahead.")
        return "\n".join(lines)


def _expand_hours(raw: dict) -> dict[str, str]:
    """Allow 'mon-sat: 10:00-20:00' shorthand as well as one key per day."""
    out: dict[str, str] = {}
    for key, value in (raw or {}).items():
        key = str(key).lower()
        if "-" in key and key.split("-")[0] in DAY_KEYS:
            a, b = key.split("-")
            ia, ib = DAY_KEYS.index(a), DAY_KEYS.index(b)
            for d in DAY_KEYS[ia:ib + 1]:
                out[d] = str(value)
        else:
            out[key] = str(value)
    for d in DAY_KEYS:
        out.setdefault(d, "closed")
    return out


def load_business(path: str | os.PathLike | None = None) -> Business:
    path = Path(path or os.environ.get("BUSINESS_FILE", "business.yaml"))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = [Service(name=s["name"], minutes=int(s["minutes"]), price=str(s["price"]),
                        notes=str(s.get("notes", ""))) for s in data.get("services", [])]
    return Business(
        name=data["name"],
        timezone=data.get("timezone", "UTC"),
        phone=str(data.get("phone", "")),
        address=str(data.get("address", "")),
        hours=_expand_hours(data.get("hours", {})),
        services=services,
        policies={str(k): str(v) for k, v in (data.get("policies") or {}).items()},
        slot_minutes=int(data.get("slot_minutes", 30)),
        booking_lead_hours=int(data.get("booking_lead_hours", 2)),
        max_days_ahead=int(data.get("max_days_ahead", 14)),
        email=str(data.get("email", "")),
        out_of_scope=str(data.get("out_of_scope", "")),
    )


@dataclass
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.environ.get("MODEL", "claude-sonnet-5-5"))
    calendar_backend: str = field(default_factory=lambda: os.environ.get("CALENDAR_BACKEND", "fake"))
    google_calendar_id: str = field(default_factory=lambda: os.environ.get("GOOGLE_CALENDAR_ID", ""))
    google_service_account_file: str = field(
        default_factory=lambda: os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json"))
    database_path: str = field(default_factory=lambda: os.environ.get("DATABASE_PATH", "frontdesk.db"))
    admin_password: str = field(default_factory=lambda: os.environ.get("ADMIN_PASSWORD", "change-me"))
