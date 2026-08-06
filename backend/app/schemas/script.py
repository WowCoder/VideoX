"""脚本与分镜 Schema。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any, Literal


# ── 候选镜头 ──
class CandidateCreate(BaseModel):
    clip_id: Optional[str] = None
    title: str = ""
    source: str = ""
    range_start: str = ""
    range_end: str = ""
    score: int = 0
    reason: str = ""
    variant: str = "stage"
    low_confidence: bool = False


class CandidateOut(BaseModel):
    id: str
    shot_id: Optional[str] = None
    unit_id: Optional[str] = None
    clip_id: Optional[str] = None
    title: str
    source: str
    range_start: str
    range_end: str
    score: int
    reason: str
    variant: str
    low_confidence: bool

    class Config:
        from_attributes = True


# ── 分镜（Shot）──
class ShotCreate(BaseModel):
    description: str = ""
    duration: int = 8
    notes: str = ""
    visual_mode: Optional[str] = None


class ShotUpdate(BaseModel):
    description: Optional[str] = None
    status: Optional[str] = None
    selected_clip_id: Optional[str] = None
    visual_mode: Optional[str] = None
    duration: Optional[int] = None
    notes: Optional[str] = None
    generated_image_path: Optional[str] = None
    generated_video_path: Optional[str] = None
    generated_effect_video_path: Optional[str] = None
    sketch_data: Optional[str] = None


class ShotOut(BaseModel):
    id: str
    unit_id: str
    source_shot_id: Optional[str] = None
    index: int
    description: str
    status: str
    selected_clip_id: Optional[str] = None
    visual_mode: Optional[str] = None
    duration: int
    notes: str
    generated_image_path: Optional[str] = None
    generated_video_path: Optional[str] = None
    generated_effect_video_path: Optional[str] = None
    candidates: list[dict] = []

    @field_validator(
        "generated_image_path",
        "generated_video_path",
        "generated_effect_video_path",
        mode="before",
    )
    @classmethod
    def sign_generated_object(cls, value):
        if not value or str(value).startswith(("http://", "https://", "data:")):
            return value
        from app.utils.storage import get_file_url

        try:
            return get_file_url(str(value))
        except Exception:
            return None

    class Config:
        from_attributes = True


# ── 脚本单元（ScriptUnit）──
class ScriptUnitCreate(BaseModel):
    outline: str = ""
    text: str = ""
    intent: str = ""
    duration: int = 8
    notes: str = ""


class ScriptUnitOut(BaseModel):
    id: str
    script_id: str
    source_unit_id: Optional[str] = None
    index: int
    outline: str
    text: str
    intent: str
    status: str
    selected_clip_id: Optional[str] = None
    duration: int
    notes: str
    candidates: list[dict] = []
    shots: list[ShotOut] = []

    class Config:
        from_attributes = True


class ScriptUnitBatchUpdate(BaseModel):
    """批量更新分镜单元。"""
    units: list[dict]  # [{ id, outline, text, intent, duration, notes, shots: [...] }]


# ── 脚本（Script）──
class VisualReference(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    category: Optional[Literal["characters", "objects", "spaces"]] = None
    assetId: Optional[str] = Field(None, max_length=64)
    clipId: Optional[str] = Field(None, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    detail: str = Field("", max_length=2000)
    variant: str = Field("stage", max_length=50)
    locked: bool = False


class VisualReferences(BaseModel):
    characters: list[VisualReference] = Field(default_factory=list, max_length=100)
    objects: list[VisualReference] = Field(default_factory=list, max_length=100)
    spaces: list[VisualReference] = Field(default_factory=list, max_length=100)


class VisualConfigUpdate(BaseModel):
    stylePreset: Optional[str] = None
    aspectRatio: Optional[str] = None
    palette: Optional[str] = None
    cameraRhythm: Optional[str] = None
    consistencyEnabled: Optional[bool] = None
    generationPolicy: Optional[str] = None
    references: Optional[VisualReferences] = None


class ScriptCreate(BaseModel):
    project_id: str
    title: str
    summary: str = ""
    format: str = "横屏 16:9"
    source_type: str = "blank"  # blank / paste / spreadsheet / ai
    visual_config: Optional[dict] = None
    units: list[ScriptUnitCreate] = []


class ScriptUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None
    format: Optional[str] = None
    visual_config: Optional[VisualConfigUpdate] = None
    needs_initial_save: Optional[bool] = None


class ScriptOut(BaseModel):
    id: str
    project_id: str
    title: str
    summary: str
    status: str
    duration: str
    unit_count: int
    matched_count: int
    progress: int
    variant: str
    format: str
    visual_config: dict
    needs_initial_save: bool
    source_type: str
    is_snapshot: bool = False
    parent_script_id: Optional[str] = None
    updated_at: datetime
    units: list[ScriptUnitOut] = []

    class Config:
        from_attributes = True


class ScriptListOut(BaseModel):
    items: list[ScriptOut]
    total: int


class LinkedCutOut(BaseModel):
    project_id: str
    name: str
    status: str
    aspect_ratio: Optional[str] = None
    timeline_version: int = 0
    current_user_role: Literal["owner", "editor", "viewer"]
    updated_at: datetime
