"""FastAPI app: chat API, demo site, embeddable widget and a small admin page."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import Receptionist
from .calendar import make_calendar
from .config import Settings, load_business
from .db import Store

STATIC = Path(__file__).parent / "static"


def create_app(business=None, calendar=None, store=None, client=None, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    business = business or load_business()
    calendar = calendar or make_calendar(business, settings)
    store = store or Store(settings.database_path)
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    receptionist = Receptionist(business, calendar, store, client, settings.model)

    app = FastAPI(title=f"{business.name} front desk", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    security = HTTPBasic()

    class ChatIn(BaseModel):
        conversation_id: str | None = None
        message: str = Field(min_length=1, max_length=2000)

    @app.get("/", response_class=HTMLResponse)
    def demo_site() -> str:
        html = (STATIC / "site.html").read_text(encoding="utf-8")
        return html.replace("{{BUSINESS_NAME}}", business.name).replace("{{PHONE}}", business.phone) \
                   .replace("{{ADDRESS}}", business.address)

    @app.get("/widget.js")
    def widget_js() -> FileResponse:
        return FileResponse(STATIC / "widget.js", media_type="application/javascript")

    @app.get("/api/config")
    def config() -> dict:
        return {"name": business.name, "greeting": f"Hi, welcome to {business.name}. I can answer questions "
                                                   f"or book an appointment. How can I help?"}

    @app.post("/api/chat")
    def chat(body: ChatIn) -> dict:
        cid = body.conversation_id or store.new_conversation()
        if store.get_messages(cid) is None:
            cid = store.new_conversation()
        try:
            text = receptionist.reply(cid, body.message)
        except Exception as e:  # model or network failure: fail safe, keep the lead path open
            text = (f"Sorry, I'm having trouble right now. Please call {business.phone} or leave your name "
                    f"and number here and the team will get back to you.")
            app.state.last_error = repr(e)
        return {"conversation_id": cid, "reply": text}

    def admin_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
        ok = secrets.compare_digest(credentials.password.encode(), settings.admin_password.encode())
        if not ok:
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})

    @app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(admin_auth)])
    def admin() -> str:
        bookings, leads = store.list_bookings(), store.list_leads()
        def rows(items, cols):
            return "".join("<tr>" + "".join(f"<td>{(r.get(c) or '')}</td>" for c in cols) + "</tr>" for r in items)
        html = (STATIC / "admin.html").read_text(encoding="utf-8")
        return (html.replace("{{BUSINESS_NAME}}", business.name)
                    .replace("{{BOOKING_ROWS}}", rows(bookings, ["start", "name", "phone", "service", "status", "created_at"]))
                    .replace("{{LEAD_ROWS}}", rows(leads, ["created_at", "name", "phone", "interest", "notes"])))

    @app.get("/api/admin/bookings", dependencies=[Depends(admin_auth)])
    def admin_bookings() -> JSONResponse:
        return JSONResponse({"bookings": store.list_bookings(), "leads": store.list_leads()})

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "business": business.name, "calendar": settings.calendar_backend}

    return app


app = create_app()
