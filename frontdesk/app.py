"""FastAPI app: chat API, hosted booking page, embeddable widget and a small admin page.

No `from __future__ import annotations` here on purpose: FastAPI and pydantic inspect the
annotations in this file at runtime, so they must be real types, not strings."""

import html
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import Receptionist
from .calendar import make_calendar
from .config import Settings, load_business
from .db import Store
from .page import render_site

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("frontdesk")


class RateLimiter:
    """Sliding window per client: at most `limit` hits per `window` seconds. In memory; fine for one process."""

    def __init__(self, limit: int, window: int = 600):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


class ChatIn(BaseModel):
    conversation_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=2000)


def create_app(business=None, calendar=None, store=None, client=None, settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings()
    business = business or load_business()
    calendar = calendar or make_calendar(business, settings)
    store = store or Store(settings.database_path)
    if client is None:
        if not settings.anthropic_api_key:
            raise SystemExit("ANTHROPIC_API_KEY is not set. Put it in .env (see .env.example) and start again.")
        import anthropic
        # The SDK waits up to 10 minutes by default, which looks like a frozen chat. Fail fast instead.
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key,
                                     timeout=settings.effective_model_timeout, max_retries=1)
        warm = settings.is_local_model
    else:
        warm = False
    receptionist = Receptionist(business, calendar, store, client, settings.model)
    limiter = RateLimiter(settings.rate_limit_per_10min)
    if warm:
        def _warm() -> None:
            try:
                receptionist.warm_up()
                log.warning("local model %s is ready", settings.model)
            except Exception:
                log.exception("could not warm up local model %s", settings.model)
        threading.Thread(target=_warm, daemon=True).start()

    app = FastAPI(title=f"{business.name} front desk", docs_url=None, redoc_url=None)
    # The widget runs on the clinic's own domain, so the browser needs these headers to call us.
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    security = HTTPBasic()

    @app.get("/", response_class=HTMLResponse)
    def booking_page() -> str:
        """The hosted page: a small site for the business, generated from business.yaml, with the chat on it.
        Clinics with no website link to this from their Google listing and Instagram."""
        return render_site((STATIC / "site.html").read_text(encoding="utf-8"), business, calendar)

    @app.get("/widget.js")
    def widget_js() -> FileResponse:
        return FileResponse(STATIC / "widget.js", media_type="application/javascript")

    @app.get("/api/config")
    def config() -> dict:
        return {"name": business.name, "greeting": f"Hi, welcome to {business.name}. I can answer questions "
                                                   f"or book an appointment. How can I help?"}

    @app.post("/api/chat")
    def chat(body: ChatIn, request: Request):
        cid = body.conversation_id or store.new_conversation()
        if store.get_messages(cid) is None:
            cid = store.new_conversation()
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
            (request.client.host if request.client else "unknown")
        if not limiter.allow(client_ip):
            return JSONResponse(status_code=429, content={"conversation_id": cid, "reply":
                f"You've sent quite a few messages. Please call {business.phone} and the team will help you directly."})
        try:
            text = receptionist.reply(cid, body.message)
            app.state.last_error = None
        except Exception as e:  # model or network failure: fail safe, keep the lead path open
            text = (f"Sorry, I'm having trouble right now. Please call {business.phone} or leave your name "
                    f"and number here and the team will get back to you.")
            app.state.last_error = repr(e)
            log.exception("chat reply failed (model %s)", settings.model)
        return {"conversation_id": cid, "reply": text}

    def admin_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
        ok = secrets.compare_digest(credentials.password.encode(), settings.admin_password.encode())
        if not ok:
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})

    @app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(admin_auth)])
    def admin() -> str:
        bookings, leads = store.list_bookings(), store.list_leads()
        for b in bookings:
            try:
                b["start"] = datetime.fromisoformat(b["start"]).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")
            except (TypeError, ValueError):
                pass
        def rows(items, cols):  # visitor-typed text ends up here, so it is escaped
            return "".join("<tr>" + "".join(f"<td>{html.escape(str(r.get(c) or ''))}</td>" for c in cols) + "</tr>"
                           for r in items)
        page = (STATIC / "admin.html").read_text(encoding="utf-8")
        return (page.replace("{{BUSINESS_NAME}}", business.name)
                    .replace("{{BOOKING_ROWS}}", rows(bookings, ["start", "name", "phone", "service", "status", "created_at"]))
                    .replace("{{LEAD_ROWS}}", rows(leads, ["created_at", "name", "phone", "interest", "notes"])))

    @app.get("/api/admin/bookings", dependencies=[Depends(admin_auth)])
    def admin_bookings() -> JSONResponse:
        return JSONResponse({"bookings": store.list_bookings(), "leads": store.list_leads()})

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "business": business.name, "calendar": settings.calendar_backend,
                "model": settings.model, "chat_failing": bool(getattr(app.state, "last_error", None))}

    return app
