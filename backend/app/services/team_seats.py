"""Team collaboration eligibility and owner-wide seat accounting."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.collaboration import ProjectInvitation, ProjectMember
from app.models.project import Project
from app.models.user import Membership, User
from app.services.subscriptions import reconcile_user_subscription


class TeamMembershipRequiredError(Exception):
    """The project owner does not currently have Team collaboration access."""


class TeamSeatLimitExceededError(Exception):
    """A collaboration mutation would exceed the owner's Team seat limit."""


@dataclass(frozen=True)
class TeamSeatSnapshot:
    used: int
    quota: int
    membership_rank: int

    @property
    def available(self) -> int:
        return max(0, self.quota - self.used)

    @property
    def can_manage(self) -> bool:
        return self.membership_rank >= 2


def normalized_seat_email(email: str) -> str:
    return email.strip().lower()


def seat_count(owner_email: str, member_emails: list[str], pending_emails: list[str]) -> int:
    """Count unique people; the owner always consumes one seat."""
    emails = {normalized_seat_email(owner_email)}
    emails.update(normalized_seat_email(email) for email in member_emails if email.strip())
    emails.update(normalized_seat_email(email) for email in pending_emails if email.strip())
    return len(emails)


async def load_team_owner(
    db: AsyncSession,
    owner_id: str,
    *,
    lock: bool = False,
) -> tuple[User, Membership]:
    query = (
        select(User)
        .where(User.id == owner_id)
        .options(
            selectinload(User.membership),
            selectinload(User.subscription),
        )
    )
    if lock:
        query = query.with_for_update()
    owner = (await db.execute(query)).scalar_one()
    await reconcile_user_subscription(db, owner)
    membership = owner.membership
    if membership is None:
        membership = (
            await db.execute(select(Membership).where(Membership.id == owner.membership_id))
        ).scalar_one()
        owner.membership = membership
    return owner, membership


async def team_seat_snapshot(
    db: AsyncSession,
    owner: User,
    membership: Membership,
    *,
    prospective_email: str | None = None,
    now: datetime | None = None,
) -> TeamSeatSnapshot:
    now = now or datetime.now(timezone.utc)
    member_emails = list(
        (
            await db.execute(
                select(User.email)
                .select_from(ProjectMember)
                .join(Project, Project.id == ProjectMember.project_id)
                .join(User, User.id == ProjectMember.user_id)
                .where(Project.owner_id == owner.id)
            )
        ).scalars().all()
    )
    pending_emails = list(
        (
            await db.execute(
                select(ProjectInvitation.email)
                .join(Project, Project.id == ProjectInvitation.project_id)
                .where(
                    Project.owner_id == owner.id,
                    ProjectInvitation.status == "pending",
                    ProjectInvitation.expires_at > now,
                )
            )
        ).scalars().all()
    )
    if prospective_email:
        pending_emails.append(prospective_email)
    return TeamSeatSnapshot(
        used=seat_count(owner.email, member_emails, pending_emails),
        quota=max(1, membership.seat_quota),
        membership_rank=membership.rank,
    )


async def require_team_seat_capacity(
    db: AsyncSession,
    owner_id: str,
    *,
    prospective_email: str | None = None,
) -> TeamSeatSnapshot:
    """Serialize seat mutations on the owner row and validate Team capacity."""
    owner, membership = await load_team_owner(db, owner_id, lock=True)
    if membership.rank < 2:
        raise TeamMembershipRequiredError
    snapshot = await team_seat_snapshot(
        db,
        owner,
        membership,
        prospective_email=prospective_email,
    )
    if snapshot.used > snapshot.quota:
        raise TeamSeatLimitExceededError
    return snapshot


async def require_team_membership(
    db: AsyncSession,
    owner_id: str,
) -> TeamSeatSnapshot:
    """Validate management eligibility without blocking actions that free seats."""
    owner, membership = await load_team_owner(db, owner_id, lock=True)
    if membership.rank < 2:
        raise TeamMembershipRequiredError
    return await team_seat_snapshot(db, owner, membership)
