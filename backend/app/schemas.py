from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime
    attendee_count: int = Field(ge=0, default=0)

    @model_validator(mode="after")
    def check_dates(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    attendee_count: int


class AgendaItemIn(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    owner: str | None = Field(default=None, max_length=200)
    minutes: int | None = Field(default=None, ge=1, le=480)


class ActionItemIn(BaseModel):
    task: str = Field(min_length=1, max_length=300)
    owner: str | None = Field(default=None, max_length=200)
    due: date | None = None


class AgendaIn(BaseModel):
    items: list[AgendaItemIn] = Field(max_length=50)
    action_items: list[ActionItemIn] = Field(default=[], max_length=50)
    ai_suggestion: dict | None = None


class AgendaOut(AgendaIn):
    model_config = ConfigDict(from_attributes=True)
