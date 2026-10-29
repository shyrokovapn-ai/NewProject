from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(engine, expire_on_commit=False)
Base.metadata.create_all(engine)


def override_db():
    with Session() as db:
        yield db


app.dependency_overrides[get_db] = override_db
client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_list():
    body = {
        "title": "Sprint planning",
        "starts_at": "2026-10-05T09:00:00Z",
        "ends_at": "2026-10-05T10:00:00Z",
        "attendee_count": 5,
    }
    r = client.post("/api/meetings", json=body)
    assert r.status_code == 201
    assert r.json()["title"] == "Sprint planning"
    assert len(client.get("/api/meetings").json()) == 1


def test_end_before_start_is_rejected():
    body = {"title": "x", "starts_at": "2026-10-05T10:00:00Z", "ends_at": "2026-10-05T09:00:00Z"}
    assert client.post("/api/meetings", json=body).status_code == 422


def _meeting():
    body = {
        "title": "Pricing sync",
        "starts_at": "2026-10-19T10:00:00Z",
        "ends_at": "2026-10-19T10:45:00Z",
    }
    return client.post("/api/meetings", json=body).json()["id"]


def test_agenda_save_and_update():
    mid = _meeting()
    assert client.get(f"/api/meetings/{mid}/agenda").status_code == 404
    body = {
        "items": [{"topic": "Pro pricing", "owner": "Олена", "minutes": 15}],
        "action_items": [{"task": "Compare", "owner": "Taras", "due": "2026-10-23"}],
        "ai_suggestion": {"model": "m", "prompt_version": "agenda-v1", "agenda": {"items": []}},
    }
    r = client.post(f"/api/meetings/{mid}/agenda", json=body)
    assert r.status_code == 200 and r.json()["ai_suggestion"]["prompt_version"] == "agenda-v1"
    body["items"] = [{"topic": "Changed"}]
    client.post(f"/api/meetings/{mid}/agenda", json=body)
    got = client.get(f"/api/meetings/{mid}/agenda").json()
    assert got["items"][0]["topic"] == "Changed"


def test_agenda_validation_and_404():
    mid = _meeting()
    bad = {"items": [{"topic": "x", "minutes": 9999}]}
    assert client.post(f"/api/meetings/{mid}/agenda", json=bad).status_code == 422
    assert client.post("/api/meetings/99999/agenda", json={"items": []}).status_code == 404
