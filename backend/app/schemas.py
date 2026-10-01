from datetime import datetime

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
