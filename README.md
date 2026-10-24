# Front Desk — after-hours receptionist agent

A web-chat receptionist for a clinic, salon or any appointment business. It answers
questions from the business's own details (hours, services, prices, location), captures
the visitor's name and phone, checks real availability and books the appointment into
Google Calendar. Every booking is written to a local database and the owner gets an
email or WhatsApp-ready summary.

Built by AIVETech as a demo and pilot product. Python, FastAPI, SQLite, the Anthropic
API with tool calling, Google Calendar API.

## What it does

- Answers hours, services, prices, location, parking, cancellation policy — only from
  `business.yaml`, never invented.
- Offers real slots from Google Calendar (or a built-in fake calendar for demos).
- Collects name and phone before booking, confirms, books, and shows the confirmation.
- Stores every conversation, lead and booking in SQLite (`frontdesk.db`).
- Owner dashboard at `/admin` lists leads and bookings.
- Demo mode: no Google account needed; a fake calendar with sensible slots.

## Run it in five minutes

```bash
git clone https://github.com/kartikmalhotra/frontdesk.git
cd frontdesk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add ANTHROPIC_API_KEY
python -m frontdesk              # http://localhost:8000
```

Open http://localhost:8000 and type "what are your hours" or "I want to book a cleaning
tomorrow evening".

Demo mode is on by default (`CALENDAR_BACKEND=fake`). To book into a real Google Calendar,
see "Google Calendar" below.

## Configure a business

Edit `business.yaml`. Everything the agent is allowed to say about the business comes
from this file. Example:

```yaml
name: Bright Smile Dental
timezone: Asia/Kolkata
phone: "+91 98765 43210"
address: 14 Green Park, New Delhi, 5 min from the metro
hours:
  mon-sat: "10:00-20:00"
  sun: closed
services:
  - name: Consultation
    minutes: 30
    price: "₹600"
  - name: Cleaning
    minutes: 45
    price: "₹1,500"
policies:
  cancellation: Free up to 24 hours before the appointment.
  parking: Street parking on Green Park Road.
slot_minutes: 30
booking_lead_hours: 2
```

## Google Calendar

1. In Google Cloud, create a project, enable the Google Calendar API, create a
   **service account** and download its JSON key as `service-account.json`.
2. Share the clinic's calendar with the service account's email (Make changes to events).
3. In `.env`: `CALENDAR_BACKEND=google`, `GOOGLE_CALENDAR_ID=<calendar id>`,
   `GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json`.

## Tests

```bash
pytest
```

The tests run the whole booking flow against the fake calendar and a scripted model,
so they need no API key.

## Embed on a website

```html
<script src="https://YOUR-HOST/widget.js" data-frontdesk="https://YOUR-HOST"></script>
```

## Deploy

Any host that runs Python works. `Dockerfile` included: `docker build -t frontdesk . && docker run -p 8000:8000 --env-file .env frontdesk`.
