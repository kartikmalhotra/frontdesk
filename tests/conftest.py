import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontdesk.calendar import FakeCalendar  # noqa: E402
from frontdesk.config import load_business  # noqa: E402
from frontdesk.db import Store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# A fixed "now": Thursday 22 Oct 2026, 21:30 IST — after hours, the case the product exists for.
NOW = datetime(2026, 10, 22, 21, 30, tzinfo=ZoneInfo("Asia/Kolkata"))


@pytest.fixture
def business():
    return load_business(ROOT / "business.delhi.yaml")


@pytest.fixture
def calendar(business):
    return FakeCalendar(business, now=NOW, prebook=False)


@pytest.fixture
def store():
    return Store(":memory:")
