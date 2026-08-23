"""全局素材库 Schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MediaType = Literal["image", "video", "audio"]


class AssetSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    asset_id: str
    start_ms: int
    end_ms: int
    duration_ms: int
    title: str
    transcript: str
    ocr_text: str
    tags: list = []
    recognition: dict = {}
    quality_score: float
    thumbnail_url: str | None = None


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    name: str
    media_type: MediaType
    source_type: str
    source_category: Literal["ai", "non-ai"] = "non-ai"
    content_types: list[Literal["scene", "role", "object", "event"]] = []
    status: str
    processing_status: str
    mime_type: str | None = None
    duration_ms: int
    width: int | None = None
    height: int | None = None
    has_audio: bool
    file_size_mb: float
    tags: list = []
    recognition: dict = {}
    asset_metadata: dict = {}
    media_url: str | None = None
    thumbnail_url: str | None = None
    match_field: str | None = None
    match_excerpt: str | None = None
    matched_segment_id: str | None = None
    project_ids: list[str] = []
    segments: list[AssetSegmentOut] = []
    created_at: datetime
    updated_at: datetime


class AssetCursorListOut(BaseModel):
    items: list[AssetOut]
    next_cursor: str | None = None
    has_more: bool = False


class UploadResponse(BaseModel):
    asset_id: str
    name: str
    media_type: MediaType
    status: str
    job_id: str | None = None


class AssetLinkRequest(BaseModel):
    role: str = Field("source", pattern="^(source|reference|shot_media|audio|cover|render_output)$")


class AssetDeleteImpactOut(BaseModel):
    can_delete: bool
    project_count: int
    shot_count: int
    composition_count: int
    blockers: list[str] = []
