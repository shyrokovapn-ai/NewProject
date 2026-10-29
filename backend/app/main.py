import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Agenda, Meeting
from app.schemas import AgendaIn, AgendaOut, MeetingCreate, MeetingOut

DB = Annotated[Session, Depends(get_db)]

app = FastAPI(title="Spry")

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"]
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/meetings", response_model=list[MeetingOut])
def list_meetings(db: DB):
    return db.scalars(select(Meeting).order_by(Meeting.starts_at)).all()


@app.post("/api/meetings", response_model=MeetingOut, status_code=201)
def create_meeting(data: MeetingCreate, db: DB):
    meeting = Meeting(**data.model_dump())
    db.add(meeting)
    db.commit()
    return meeting


@app.get("/api/meetings/{meeting_id}/agenda", response_model=AgendaOut)
def get_agenda(meeting_id: int, db: DB):
    agenda = db.scalar(select(Agenda).where(Agenda.meeting_id == meeting_id))
    if agenda is None:
        raise HTTPException(404, "no agenda yet")
    return agenda


@app.post("/api/meetings/{meeting_id}/agenda", response_model=AgendaOut)
def save_agenda(meeting_id: int, data: AgendaIn, db: DB):
    """The only place an agenda is written. The AI parser never writes, it only suggests."""
    if db.get(Meeting, meeting_id) is None:
        raise HTTPException(404, "meeting not found")
    agenda = db.scalar(select(Agenda).where(Agenda.meeting_id == meeting_id))
    if agenda is None:
        agenda = Agenda(meeting_id=meeting_id)
        db.add(agenda)
    agenda.items = [i.model_dump(mode="json") for i in data.items]
    agenda.action_items = [a.model_dump(mode="json") for a in data.action_items]
    agenda.ai_suggestion = data.ai_suggestion
    db.commit()
    return agenda
