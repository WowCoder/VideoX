"""项目成员、邀请和角色管理。"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.collaboration import ProjectInvitation, ProjectMember
from app.models.project import Project
from app.models.user import User
from app.schemas.collaboration import (
    InvitationAcceptOut,
    InvitationPreviewOut,
    ProjectCollaborationOut,
    ProjectInvitationCreate,
    ProjectInvitationOut,
    ProjectMemberOut,
    ProjectMemberRoleUpdate,
)
from app.services.project_access import require_project_access
from app.services.team_seats import (
    TeamMembershipRequiredError,
    TeamSeatLimitExceededError,
    load_team_owner,
    require_team_membership,
    require_team_seat_capacity,
    team_seat_snapshot,
)


router = APIRouter()
settings = get_settings()


def _team_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TeamMembershipRequiredError):
        return HTTPException(status_code=403, detail="项目协作仅对 Team 会员开放")
    return HTTPException(status_code=409, detail="Team 席位已用完，请先移除成员或撤销邀请")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _masked_email(email: str) -> str:
    local, _, domain = email.partition("@")
    visible = local[:2]
    return f"{visible}{'*' * max(2, len(local) - len(visible))}@{domain}"


def _invitation_url(token: str) -> str:
    origin = settings.cors_origin_list[0].rstrip("/") if settings.cors_origin_list else ""
    return f"{origin}/invite/{token}" if origin else f"/invite/{token}"


def _derived_status(invitation: ProjectInvitation) -> str:
    if invitation.status == "pending" and invitation.expires_at <= _now():
        return "expired"
    return invitation.status


def _member_out(member: ProjectMember) -> ProjectMemberOut:
    return ProjectMemberOut(
        id=member.id,
        user_id=member.user.id,
        name=member.user.name,
        email=member.user.email,
        avatar_initial=member.user.avatar_initial,
        role=member.role,
        joined_at=member.joined_at,
    )


def _owner_out(project: Project) -> ProjectMemberOut:
    return ProjectMemberOut(
        id=f"owner-{project.owner.id}",
        user_id=project.owner.id,
        name=project.owner.name,
        email=project.owner.email,
        avatar_initial=project.owner.avatar_initial,
        role="owner",
        joined_at=project.created_at,
    )


@router.get("/{project_id}/collaboration", response_model=ProjectCollaborationOut)
async def get_project_collaboration(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    access = await require_project_access(project_id, user, db)
    project_result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.owner),
            selectinload(Project.project_members).selectinload(ProjectMember.user),
        )
    )
    project = project_result.scalar_one()
    owner, membership = await load_team_owner(db, project.owner_id)
    seats = await team_seat_snapshot(db, owner, membership)
    invitations: list[ProjectInvitationOut] = []
    if access.role == "owner":
        invitation_result = await db.execute(
            select(ProjectInvitation)
            .where(ProjectInvitation.project_id == project_id)
            .order_by(ProjectInvitation.created_at.desc())
        )
        invitations = [
            ProjectInvitationOut(
                id=item.id,
                email=item.email,
                role=item.role,
                status=_derived_status(item),
                expires_at=item.expires_at,
                created_at=item.created_at,
            )
            for item in invitation_result.scalars().all()
        ]

    return ProjectCollaborationOut(
        project_id=project.id,
        current_user_role=access.role,
        members=[_owner_out(project)] + [_member_out(item) for item in project.project_members],
        invitations=invitations,
        seats_used=seats.used,
        seat_quota=seats.quota,
        can_manage_members=access.role == "owner" and seats.can_manage,
        management_message=(
            "Team 会员可在所有项目间共享 5 个席位（含所有者）"
            if seats.can_manage
            else "邀请和管理成员需要 Team 会员"
        ),
    )


@router.post(
    "/{project_id}/invitations",
    response_model=ProjectInvitationOut,
    status_code=201,
)
async def create_project_invitation(
    project_id: str,
    req: ProjectInvitationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    access = await require_project_access(project_id, user, db, "owner")
    email = str(req.email).strip().lower()
    owner = await db.get(User, access.project.owner_id)
    if owner and owner.email.lower() == email:
        raise HTTPException(status_code=409, detail="项目所有者已在成员列表中")

    invited_user = (
        await db.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()
    if invited_user:
        existing_member = (
            await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == invited_user.id,
                )
            )
        ).scalar_one_or_none()
        if existing_member:
            raise HTTPException(status_code=409, detail="该用户已经是项目成员")

    pending = (
        await db.execute(
            select(ProjectInvitation).where(
                ProjectInvitation.project_id == project_id,
                ProjectInvitation.email == email,
                ProjectInvitation.status == "pending",
            )
        )
    ).scalars().all()
    now = _now()
    for item in pending:
        item.status = "revoked"
        item.revoked_at = now
    await db.flush()
    try:
        await require_team_seat_capacity(
            db,
            access.project.owner_id,
            prospective_email=email,
        )
    except (TeamMembershipRequiredError, TeamSeatLimitExceededError) as exc:
        raise _team_error(exc) from exc

    token = secrets.token_urlsafe(32)
    invitation = ProjectInvitation(
        project_id=project_id,
        email=email,
        role=req.role,
        token_hash=_token_hash(token),
        status="pending",
        inviter_id=user.id,
        expires_at=now + timedelta(days=7),
    )
    db.add(invitation)
    await db.flush()
    return ProjectInvitationOut(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        invitation_url=_invitation_url(token),
    )


@router.delete("/{project_id}/invitations/{invitation_id}", status_code=204)
async def revoke_project_invitation(
    project_id: str,
    invitation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    access = await require_project_access(project_id, user, db, "owner")
    try:
        await require_team_membership(db, access.project.owner_id)
    except TeamMembershipRequiredError as exc:
        raise _team_error(exc) from exc
    invitation = (
        await db.execute(
            select(ProjectInvitation).where(
                ProjectInvitation.id == invitation_id,
                ProjectInvitation.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=404, detail="邀请不存在")
    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail="该邀请已不在待接受状态")
    invitation.status = "revoked"
    invitation.revoked_at = _now()


@router.patch("/{project_id}/members/{member_id}", response_model=ProjectMemberOut)
async def update_project_member_role(
    project_id: str,
    member_id: str,
    req: ProjectMemberRoleUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    access = await require_project_access(project_id, user, db, "owner")
    try:
        await require_team_membership(db, access.project.owner_id)
    except TeamMembershipRequiredError as exc:
        raise _team_error(exc) from exc
    member = (
        await db.execute(
            select(ProjectMember)
            .where(ProjectMember.id == member_id, ProjectMember.project_id == project_id)
            .options(selectinload(ProjectMember.user))
        )
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="项目成员不存在")
    member.role = req.role
    await db.flush()
    return _member_out(member)


@router.delete("/{project_id}/members/{member_id}", status_code=204)
async def remove_project_member(
    project_id: str,
    member_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    access = await require_project_access(project_id, user, db, "owner")
    try:
        await require_team_membership(db, access.project.owner_id)
    except TeamMembershipRequiredError as exc:
        raise _team_error(exc) from exc
    member = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.id == member_id,
                ProjectMember.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="项目成员不存在")
    await db.delete(member)


@router.get("/invitations/{token}", response_model=InvitationPreviewOut)
async def preview_project_invitation(token: str, db: AsyncSession = Depends(get_db)):
    invitation = (
        await db.execute(
            select(ProjectInvitation)
            .where(ProjectInvitation.token_hash == _token_hash(token))
            .options(
                selectinload(ProjectInvitation.project),
                selectinload(ProjectInvitation.inviter),
            )
        )
    ).scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=404, detail="邀请链接无效")
    return InvitationPreviewOut(
        project_id=invitation.project_id,
        project_name=invitation.project.name,
        inviter_name=invitation.inviter.name if invitation.inviter else "项目管理员",
        role=invitation.role,
        recipient=_masked_email(invitation.email),
        status=_derived_status(invitation),
        expires_at=invitation.expires_at,
    )


@router.post("/invitations/{token}/accept", response_model=InvitationAcceptOut)
async def accept_project_invitation(
    token: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    invitation = (
        await db.execute(
            select(ProjectInvitation)
            .where(ProjectInvitation.token_hash == _token_hash(token))
            .options(selectinload(ProjectInvitation.project))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=404, detail="邀请链接无效")
    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail="该邀请已被接受或撤销")
    now = _now()
    if invitation.expires_at <= now:
        raise HTTPException(status_code=410, detail="邀请已过期，请联系项目所有者重新邀请")
    if user.email.strip().lower() != invitation.email:
        raise HTTPException(status_code=403, detail="当前登录邮箱与邀请邮箱不一致")
    if invitation.project.owner_id == user.id:
        raise HTTPException(status_code=409, detail="你已经是该项目所有者")

    try:
        await require_team_seat_capacity(db, invitation.project.owner_id)
    except (TeamMembershipRequiredError, TeamSeatLimitExceededError) as exc:
        raise _team_error(exc) from exc

    member = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == invitation.project_id,
                ProjectMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not member:
        member = ProjectMember(
            project_id=invitation.project_id,
            user_id=user.id,
            role=invitation.role,
            invited_by_id=invitation.inviter_id,
            joined_at=now,
        )
        db.add(member)
    invitation.status = "accepted"
    invitation.accepted_user_id = user.id
    invitation.accepted_at = now
    await db.flush()
    return InvitationAcceptOut(
        project_id=invitation.project_id,
        project_name=invitation.project.name,
        role=invitation.role,
        message="已加入项目",
    )
