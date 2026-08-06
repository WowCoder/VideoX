"""项目协作 Schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


ProjectRole = Literal["owner", "editor", "viewer"]
AssignableRole = Literal["editor", "viewer"]


class ProjectMemberOut(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    avatar_initial: str
    role: ProjectRole
    joined_at: datetime


class ProjectInvitationCreate(BaseModel):
    email: EmailStr
    role: AssignableRole = "viewer"


class ProjectInvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: AssignableRole
    status: str
    expires_at: datetime
    created_at: datetime
    invitation_url: str | None = None
    delivery: str = "link_only"
    delivery_message: str = "邮件服务未配置，请复制邀请链接发送给成员"


class ProjectCollaborationOut(BaseModel):
    project_id: str
    current_user_role: ProjectRole
    members: list[ProjectMemberOut]
    invitations: list[ProjectInvitationOut]


class ProjectMemberRoleUpdate(BaseModel):
    role: AssignableRole


class InvitationPreviewOut(BaseModel):
    project_id: str
    project_name: str
    inviter_name: str
    role: AssignableRole
    recipient: str
    status: str
    expires_at: datetime


class InvitationAcceptOut(BaseModel):
    project_id: str
    project_name: str
    role: AssignableRole
    message: str
