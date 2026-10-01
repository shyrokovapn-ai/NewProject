import os
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Meeting
from app.schemas import MeetingCreate, MeetingOut

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
