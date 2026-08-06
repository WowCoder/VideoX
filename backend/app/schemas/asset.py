"""素材 Schema。"""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class ClipOut(BaseModel):
    id: str
    asset_id: str
    start_time: float
    end_time: float
    duration: float
    title: str
    transcript_segment: str
    ocr_segment: str = ""
    scene_type: Optional[str] = None
    shot_type: Optional[str] = None
    camera_motion: Optional[str] = None
    persons: list = []
    objects: list = []
    thumbnail_path: Optional[str] = None
    thumbnail_url: Optional[str] = None
    variant: str
    quality_score: float

    class Config:
        from_attributes = True


class AssetOut(BaseModel):
    id: str
    project_id: str
    name: str
    duration: float
    status: str
    source: str
    variant: str
    media_type: str = "video"
    has_audio: bool = False
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    file_size_mb: float
    resolution: Optional[str] = None
    fps: float
    codec: Optional[str] = None
    audio_codec: Optional[str] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    bitrate: Optional[int] = None
    transcript: Optional[str] = None
    ocr_text: Optional[str] = None
    tags: list = []
    match_field: Optional[str] = None
    match_excerpt: Optional[str] = None
    matched_clip_id: Optional[str] = None
    uploaded_at: datetime
    created_at: Optional[datetime] = None
    clips: list[ClipOut] = []

    class Config:
        from_attributes = True


class AssetListOut(BaseModel):
    items: list[AssetOut]
    total: int


class UploadResponse(BaseModel):
    asset_id: str
    name: str
    status: str
    job_id: str
