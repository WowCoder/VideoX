"""项目聚合与工作区 Schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.asset import AssetOut


ProjectStatus = Literal["draft", "editing", "processing", "ready", "exporting", "failed"]


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field("AI 科技 / 产品讲解", max_length=50)
    description: str = Field("", max_length=5000)
    variant: str = Field("stage", max_length=50)
    script_title: str | None = Field(None, max_length=200)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:3"] = "16:9"
    target_duration_seconds: int = Field(0, ge=0, le=86400)


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    type: str | None = Field(None, max_length=50)
    description: str | None = Field(None, max_length=5000)
    status: ProjectStatus | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    initial: str
    type: str
    description: str
    status: ProjectStatus
    variant: str
    cover_asset_id: str | None = None
    master_output_asset_id: str | None = None
    cover_media_type: str | None = None
    cover_media_url: str | None = None
    cover_thumbnail_url: str | None = None
    asset_count: int = 0
    scene_count: int = 0
    shot_count: int = 0
    duration_ms: int = 0
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:3"] = "16:9"
    matched_percent: int = 0
    active_job_count: int = 0
    updated_at: datetime
    created_at: datetime


class ProjectListOut(BaseModel):
    items: list[ProjectOut]
    total: int


class CandidateDocument(BaseModel):
    id: str
    segment_id: str | None = None
    title: str = ""
    source: str = ""
    range_start_ms: int = 0
    range_end_ms: int = 0
    score: int = 0
    reason: str = ""
    low_confidence: bool = False


class ShotMediaVersionDocument(BaseModel):
    id: str
    asset_id: str
    job_id: str | None = None
    parent_version_id: str | None = None
    kind: str
    operation: str
    parameters: dict = Field(default_factory=dict)
    status: str
    is_selected: bool
    media_url: str | None = None
    created_at: datetime


class ShotDocument(BaseModel):
    id: str | None = None
    index: int = Field(0, ge=0)
    description: str = Field("", max_length=10000)
    status: str = "editing"
    visual_mode: str | None = None
    asset_id: str | None = None
    segment_id: str | None = None
    selected_media_version_id: str | None = None
    source_start_ms: int = Field(0, ge=0)
    source_end_ms: int = Field(0, ge=0)
    duration_ms: int = Field(8000, ge=1, le=86400000)
    locked: bool = False
    transform: dict = Field(default_factory=dict)
    adjust: dict = Field(default_factory=dict)
    audio_settings: dict = Field(default_factory=dict)
    subtitle_settings: dict = Field(default_factory=dict)
    transition: dict = Field(default_factory=dict)
    motion: dict = Field(default_factory=dict)
    subtitle_text: str = Field("", max_length=20000)
    subtitle_overridden: bool = False
    subtitle_source_revision: int = Field(0, ge=0)
    subtitle_outdated: bool = False
    notes: str = Field("", max_length=5000)
    sketch_data: str | None = None
    revision: int = 0
    candidates: list[CandidateDocument] = Field(default_factory=list)
    media_versions: list[ShotMediaVersionDocument] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_range(self):
        if self.source_end_ms and self.source_end_ms < self.source_start_ms:
            raise ValueError("素材结束时间不能早于开始时间")
        return self


class SceneDocument(BaseModel):
    id: str | None = None
    index: int = Field(0, ge=0)
    outline: str = Field("", max_length=200)
    narration_text: str = Field("", max_length=50000)
    intent: str = Field("", max_length=10000)
    status: str = "editing"
    estimated_duration_ms: int = Field(8000, ge=0, le=86400000)
    notes: str = Field("", max_length=5000)
    revision: int = 0
    shots: list[ShotDocument] = Field(default_factory=list, max_length=2000)


class ProjectDocumentSettings(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field("", max_length=10000)
    status: str = "editing"
    target_duration_seconds: int | None = Field(None, ge=0, le=86400)
    estimated_duration_seconds: int = Field(0, ge=0, le=86400)
    source_type: str = "blank"
    visual_config: dict = Field(default_factory=dict)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:3"] = "16:9"
    resolution: str = Field("1920x1080", pattern=r"^\d{2,5}x\d{2,5}$")
    fps: int = Field(25, ge=1, le=120)
    visual_settings: dict = Field(default_factory=dict)
    global_audio: dict = Field(default_factory=dict)
    global_overlays: list = Field(default_factory=list)


class StoryboardDocument(BaseModel):
    scenes: list[SceneDocument] = Field(default_factory=list, max_length=1000)


class TimelineDocument(BaseModel):
    duration_ms: int = Field(0, ge=0, le=86400000)
    tracks: list = Field(default_factory=list, max_length=100)


class VisualLayersDocument(BaseModel):
    items: list = Field(default_factory=list)


class GlobalScopesDocument(BaseModel):
    film: dict = Field(default_factory=dict)
    scenes: dict[str, dict] = Field(default_factory=dict)


class WorkflowGraphDocument(BaseModel):
    nodes: list = Field(default_factory=list)
    edges: list = Field(default_factory=list)


class ProjectDocument(BaseModel):
    id: str
    schema_version: int = Field(1, ge=1)
    revision: int = Field(0, ge=0)
    settings: ProjectDocumentSettings
    storyboard: StoryboardDocument = Field(default_factory=StoryboardDocument)
    timeline: TimelineDocument = Field(default_factory=TimelineDocument)
    visual_layers: VisualLayersDocument = Field(default_factory=VisualLayersDocument)
    global_scopes: GlobalScopesDocument = Field(default_factory=GlobalScopesDocument)
    workflow_graph: WorkflowGraphDocument = Field(default_factory=WorkflowGraphDocument)
    render_settings: dict = Field(default_factory=dict)
    current_render_asset_id: str | None = None


class WorkspaceOut(BaseModel):
    project: ProjectOut
    document: ProjectDocument
    linked_assets: list[AssetOut] = Field(default_factory=list)


class WorkspaceSave(BaseModel):
    expected_revision: int = Field(..., ge=0)
    project: ProjectUpdate | None = None
    document: ProjectDocument
    reason: Literal["autosave", "manual_save", "before_ai_operation"] = "autosave"


class DeleteMutationOut(BaseModel):
    workspace: WorkspaceOut
    undo_token: str
    undo_expires_at: datetime


class UndoRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=100)


class ScopeSelection(BaseModel):
    type: Literal["project", "scene", "shot", "asset"]
    scene_ids: list[str] = Field(default_factory=list, max_length=1000)
    shot_ids: list[str] = Field(default_factory=list, max_length=2000)
    asset_ids: list[str] = Field(default_factory=list, max_length=2000)


class ScopedOperationRequest(BaseModel):
    scope: ScopeSelection
    operation: str = Field(..., min_length=1, max_length=100)
    parameters: dict = Field(default_factory=dict)
    expected_revision: int = Field(..., ge=0)
