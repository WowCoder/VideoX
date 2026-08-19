"""灵感岛两类正式任务的 API 契约。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


InspirationTaskType = Literal["topic-recommendation", "link-update"]
InspirationScheduleType = Literal["manual", "daily", "weekly"]


class InspirationSchedule(BaseModel):
    type: InspirationScheduleType = "daily"
    time: str = Field("09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    weekday: int = Field(1, ge=0, le=6)
    time_zone: Literal["Asia/Shanghai"] = "Asia/Shanghai"


class InspirationSourceCreate(BaseModel):
    source_type: Literal["web", "rss"] = "web"
    url: HttpUrl
    fetch_config: dict = Field(default_factory=dict)


class InspirationTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    task_type: InspirationTaskType
    topic_brief: str = Field("", max_length=10000)
    topic_count: int | None = Field(None, ge=1, le=20)
    schedule: InspirationSchedule = Field(default_factory=InspirationSchedule)
    enabled: bool = True
    sources: list[InspirationSourceCreate] = Field(..., min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_task_specific_fields(self):
        if self.task_type == "topic-recommendation":
            if not self.topic_brief.strip():
                raise ValueError("选题推荐任务必须填写选题方向")
            if self.topic_count is None:
                self.topic_count = 5
        else:
            self.topic_brief = ""
            self.topic_count = None
        return self


class InspirationTaskUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    task_type: InspirationTaskType | None = None
    topic_brief: str | None = Field(None, max_length=10000)
    topic_count: int | None = Field(None, ge=1, le=20)
    schedule: InspirationSchedule | None = None
    enabled: bool | None = None
    sources: list[InspirationSourceCreate] | None = Field(None, min_length=1, max_length=50)


class InspirationSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: Literal["web", "rss"]
    url: str
    enabled: bool
    last_success_at: datetime | None = None
    last_error: str | None = None


class InspirationTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    task_type: InspirationTaskType
    topic_brief: str
    topic_count: int | None = None
    schedule: InspirationSchedule
    output_format: str
    enabled: bool
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    sources: list[InspirationSourceOut] = Field(default_factory=list)


class InspirationTaskListOut(BaseModel):
    items: list[InspirationTaskOut]
    total: int


class InspirationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    summary: str
    content: dict
    citations: list
    model_provider: str | None = None
    model_name: str | None = None
    project_id: str | None = None
    created_at: datetime


class InspirationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    job_id: str | None = None
    status: str
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    results: list[InspirationResultOut] = Field(default_factory=list)


class InspirationRunListOut(BaseModel):
    items: list[InspirationRunOut]
    total: int
