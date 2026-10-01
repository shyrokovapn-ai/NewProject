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
