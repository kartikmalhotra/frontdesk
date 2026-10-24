"""HTTP layer: demo site, widget, chat endpoint with a scripted model, admin auth."""

import base64

from fastapi.testclient import TestClient

from frontdesk.app import create_app
from frontdesk.config import Settings
from tests.conftest import NOW
from tests.scripted_model import ScriptedClient, ScriptedMessages, text


def make_client(business, calendar, store, script):
    settings = Settings()
    settings.admin_password = "secret"
    app = create_app(business=business, calendar=calendar, store=store,
                     client=ScriptedClient(ScriptedMessages(script)), settings=settings)
    return TestClient(app)


def test_site_and_widget_serve(business, calendar, store):
    c = make_client(business, calendar, store, [])
    r = c.get("/")
    assert r.status_code == 200 and "Bright Smile Dental" in r.text and "widget.js" in r.text
    r = c.get("/widget.js")
    assert r.status_code == 200 and "fd-launch" in r.text
    r = c.get("/api/config")
    assert r.json()["name"] == "Bright Smile Dental"


def test_chat_creates_conversation_and_replies(business, calendar, store):
    c = make_client(business, calendar, store, [[text("We're open until 8 pm today.")], [text("Sure.")]])
    r = c.post("/api/chat", json={"message": "are you open?"})
    body = r.json()
    assert r.status_code == 200 and body["reply"] == "We're open until 8 pm today." and body["conversation_id"]
    r2 = c.post("/api/chat", json={"conversation_id": body["conversation_id"], "message": "thanks"})
    assert r2.json()["conversation_id"] == body["conversation_id"]
    assert len(store.get_messages(body["conversation_id"])) == 4


def test_chat_fails_safe_when_model_errors(business, calendar, store):
    class Boom:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("api down")
    settings = Settings()
    app = create_app(business=business, calendar=calendar, store=store, client=Boom(), settings=settings)
    c = TestClient(app)
    r = c.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 200 and business.phone in r.json()["reply"]


def test_admin_requires_password(business, calendar, store):
    c = make_client(business, calendar, store, [])
    assert c.get("/admin").status_code == 401
    auth = base64.b64encode(b"owner:secret").decode()
    r = c.get("/admin", headers={"Authorization": f"Basic {auth}"})
    assert r.status_code == 200 and "Bookings" in r.text


def test_admin_escapes_visitor_text(business, calendar, store):
    cid = store.new_conversation()
    store.save_lead(cid, "<script>alert(1)</script>", "+91 90000 00000", "Cleaning", notes="x")
    c = make_client(business, calendar, store, [])
    auth = base64.b64encode(b"owner:secret").decode()
    r = c.get("/admin", headers={"Authorization": f"Basic {auth}"})
    assert "<script>alert(1)" not in r.text and "&lt;script&gt;" in r.text


def test_widget_can_be_embedded_cross_origin(business, calendar, store):
    c = make_client(business, calendar, store, [])
    r = c.get("/api/config", headers={"Origin": "https://clinic.example"})
    assert r.headers.get("access-control-allow-origin") == "*"


def test_chat_is_rate_limited(business, calendar, store):
    settings = Settings()
    settings.rate_limit_per_10min = 2
    script = [[text("one")], [text("two")], [text("three")]]
    app = create_app(business=business, calendar=calendar, store=store,
                     client=ScriptedClient(ScriptedMessages(script)), settings=settings)
    c = TestClient(app)
    assert c.post("/api/chat", json={"message": "a"}).status_code == 200
    assert c.post("/api/chat", json={"message": "b"}).status_code == 200
    r = c.post("/api/chat", json={"message": "c"})
    assert r.status_code == 429 and business.phone in r.json()["reply"]
