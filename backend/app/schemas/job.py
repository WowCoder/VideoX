"""任务 Schema。"""

from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional


class JobCreate(BaseModel):
    project_id: Optional[str] = None
    subject_type: Optional[str] = None
    subject_id: Optional[str] = None
    name: str
    type: str  # 素材处理/AI 脚本生成/镜头匹配/AI 生图分镜/分镜图 AI 生视频/示意图特效视频/AI 初剪生成
    detail: str = ""
    stages: list[str] = []
    result_detail: str = ""


class ExportMetadata(BaseModel):
    format: str
    resolution: str
    aspect_ratio: str


class ShotDescriptionProposalItem(BaseModel):
    shot_id: str
    original_description: str
    proposed_description: str


class JobReviewProposal(BaseModel):
    type: Literal["shot_description"]
    status: Literal["pending", "accepted", "rejected"] = "pending"
    base_revision: int
    items: list[ShotDescriptionProposalItem]


class JobOut(BaseModel):
    id: str
    owner_id: str
    project_id: Optional[str] = None
    subject_type: Optional[str] = None
    subject_id: Optional[str] = None
    name: str
    type: str
    status: str
    stage: str
    stages: list[str]
    stage_index: int
    progress: int
    detail: str
    eta: str
    logs: list[str]
    result: Optional[str] = None
    result_detail: str
    result_url: Optional[str] = None
    export_metadata: Optional[ExportMetadata] = None
    review_proposal: Optional[JobReviewProposal] = None
    payload: dict = Field(default_factory=dict, exclude=True, repr=False)
    attempts: int = 0
    max_attempts: int = 3
    quoted_credits: int = 0
    billed_credits: int = 0
    is_simulated: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="after")
    def derive_safe_metadata(self):
        """只暴露经过校验的展示字段，不向客户端泄露通用任务 payload。"""
        if self.type == "导出" and self.export_metadata is None:
            payload = self.payload or {}
            self.export_metadata = ExportMetadata(
                format=str(payload.get("format") or "mp4"),
                resolution=str(payload.get("resolution") or "1080p"),
                aspect_ratio=str(payload.get("aspect_ratio") or "16:9"),
            )
        if self.type == "AI 分镜完善" and self.review_proposal is None:
            proposal = (self.payload or {}).get("review_proposal")
            if isinstance(proposal, dict):
                self.review_proposal = JobReviewProposal.model_validate(proposal)
        return self

    class Config:
        from_attributes = True


class JobListOut(BaseModel):
    items: list[JobOut]
    total: int


class VideoGenerationBatchOut(BaseModel):
    id: str
    project_id: str
    scope_type: str
    status: str
    total_count: int
    succeeded_count: int
    failed_count: int
    cancelled_count: int
    created_at: datetime
    updated_at: datetime
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True
