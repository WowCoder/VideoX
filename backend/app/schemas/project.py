"""项目 Schema。"""

from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional

from app.schemas.asset import AssetOut


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = "AI 科技 / 产品讲解"
    description: str = ""
    variant: str = "stage"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    name: str
    initial: str
    type: str
    description: str
    status: str
    asset_count: int
    clip_count: int
    script_count: int
    variant: str
    members: list[str] = []
    current_user_role: Literal["owner", "editor", "viewer"] = "owner"
    is_new: bool = False
    source_script_id: Optional[str] = None
    visual_style: Optional[str] = None
    aspect_ratio: Optional[str] = None
    ai_shot_count: int = 0
    updated_at: datetime
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjectListOut(BaseModel):
    items: list[ProjectOut]
    total: int


class TimelineCrop(BaseModel):
    l: float = Field(0, ge=0, le=100)
    t: float = Field(0, ge=0, le=100)
    r: float = Field(0, ge=0, le=100)
    b: float = Field(0, ge=0, le=100)

    @model_validator(mode="after")
    def validate_remaining_area(self):
        if self.l + self.r >= 100 or self.t + self.b >= 100:
            raise ValueError("裁剪后必须保留有效画面区域")
        return self


class TimelineTransform(BaseModel):
    scale: float = Field(100, ge=1, le=1000)
    x: float = Field(0, ge=-500, le=500)
    y: float = Field(0, ge=-500, le=500)
    rotation: float = Field(0, ge=-360, le=360)
    opacity: float = Field(100, ge=0, le=100)
    crop: TimelineCrop = TimelineCrop()


class TimelineAdjust(BaseModel):
    brightness: float = Field(100, ge=0, le=300)
    contrast: float = Field(100, ge=0, le=300)
    saturation: float = Field(100, ge=0, le=300)


class TimelineAudio(BaseModel):
    volume: float = Field(100, ge=0, le=200)
    muted: bool = False
    denoise: bool = False
    fade_in: float = Field(0, ge=0, le=30)
    fade_out: float = Field(0, ge=0, le=30)


class TimelineTransition(BaseModel):
    type: Literal["none", "fade_black", "fade_white"] = "none"
    duration: float = Field(0.5, ge=0.1, le=3)


class TimelineClip(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    track: Literal["video", "audio", "subtitle"]
    start: float = Field(..., ge=0)
    duration: float = Field(..., gt=0, le=86400)
    name: str = Field(..., min_length=1, max_length=255)
    variant: str = Field("stage", max_length=50)
    asset_id: Optional[str] = Field(None, max_length=64)
    source_clip_id: Optional[str] = Field(None, max_length=64)
    source_start: float = Field(0, ge=0)
    source_script_id: Optional[str] = Field(None, max_length=64)
    source_unit_id: Optional[str] = Field(None, max_length=64)
    source_shot_id: Optional[str] = Field(None, max_length=64)
    snapshot_script_id: Optional[str] = Field(None, max_length=64)
    snapshot_unit_id: Optional[str] = Field(None, max_length=64)
    snapshot_shot_id: Optional[str] = Field(None, max_length=64)
    generated_media_path: Optional[str] = Field(None, max_length=1000)
    generated_media_url: Optional[str] = Field(None, max_length=2000)
    generated_media_type: Optional[Literal["image", "video"]] = None
    origin: Literal[
        "script_match",
        "script_generated",
        "script_placeholder",
        "script_subtitle",
        "manual_asset",
        "manual_generated",
    ] = "manual_asset"
    sync_status: Literal[
        "synced",
        "script_changed",
        "timeline_changed",
        "detached",
    ] = "detached"
    text: Optional[str] = Field(None, max_length=10000)
    transform: TimelineTransform = TimelineTransform()
    adjust: TimelineAdjust = TimelineAdjust()
    audio: TimelineAudio = TimelineAudio()
    transition: TimelineTransition = TimelineTransition()


class ProjectTimelineUpdate(BaseModel):
    version: int = Field(..., ge=0)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:3"] = "16:9"
    clips: list[TimelineClip] = Field(default_factory=list, max_length=2000)


class ProjectTimelineOut(BaseModel):
    project_id: str
    version: int
    aspect_ratio: str
    clips: list[TimelineClip]
    updated_at: Optional[datetime] = None


class ProjectMediaItemOut(BaseModel):
    id: str
    project_id: str
    kind: Literal["source_asset", "ai_image", "ai_video", "ai_effect_video"]
    asset_id: Optional[str] = None
    storage_path: Optional[str] = None
    media_type: Literal["image", "video", "audio"]
    source_project_id: Optional[str] = None
    source_script_id: Optional[str] = None
    source_shot_id: Optional[str] = None
    name: str
    duration: float
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    asset: Optional[AssetOut] = None
    created_at: datetime


class ProjectMediaListOut(BaseModel):
    items: list[ProjectMediaItemOut]
    total: int
