"""任务 Schema。"""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class JobCreate(BaseModel):
    project_id: str
    name: str
    type: str  # 素材处理/AI 脚本生成/镜头匹配/AI 生图分镜/分镜图 AI 生视频/示意图特效视频/AI 初剪生成
    detail: str = ""
    stages: list[str] = []
    result_detail: str = ""


class JobOut(BaseModel):
    id: str
    project_id: str
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
    attempts: int = 0
    max_attempts: int = 3
    is_simulated: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class JobListOut(BaseModel):
    items: list[JobOut]
    total: int
