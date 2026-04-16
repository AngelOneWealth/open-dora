from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Commit, PullRequest, Review, User
from app.models.team import Team
from app.schemas.teams import (
    CreateTeamRequest,
    TeamDetailResponse,
    TeamSummary,
    TeamsListResponse,
    UserStatRow,
    WeeklyUserStat,
)

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=TeamsListResponse, summary="List teams")
async def list_teams(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamsListResponse:
    total = (await db.execute(select(func.count()).select_from(Team))).scalar_one()
    teams = (await db.execute(select(Team).order_by(Team.name))).scalars().all()

    stats: dict[int, dict] = {}
    if teams:
        since = datetime.now(timezone.utc) - timedelta(days=180)
        team_ids = [t.id for t in teams]

        # Active member count per team
        for row in (
            await db.execute(
                select(User.team_id, func.count().label("member_count"))
                .where(User.team_id.in_(team_ids), User.active == True)  # noqa: E712
                .group_by(User.team_id)
            )
        ).fetchall():
            stats.setdefault(row.team_id, {})["member_count"] = row.member_count

        # Commits + net lines
        for row in (
            await db.execute(
                select(
                    User.team_id,
                    func.count().label("commits"),
                    func.coalesce(func.sum(Commit.additions - Commit.deletions), 0).label("net_lines"),
                )
                .select_from(Commit)
                .join(User, User.id == Commit.author_id)
                .where(User.team_id.in_(team_ids), Commit.committed_at >= since)
                .group_by(User.team_id)
            )
        ).fetchall():
            stats.setdefault(row.team_id, {})["commits"] = row.commits
            stats[row.team_id]["net_lines"] = row.net_lines

        # PRs opened
        for row in (
            await db.execute(
                select(User.team_id, func.count().label("prs_opened"))
                .select_from(PullRequest)
                .join(User, User.id == PullRequest.author_id)
                .where(User.team_id.in_(team_ids), PullRequest.opened_at >= since)
                .group_by(User.team_id)
            )
        ).fetchall():
            stats.setdefault(row.team_id, {})["prs_opened"] = row.prs_opened

        # Reviews
        for row in (
            await db.execute(
                select(User.team_id, func.count().label("reviews"))
                .select_from(Review)
                .join(User, User.id == Review.reviewer_id)
                .where(User.team_id.in_(team_ids), Review.submitted_at >= since)
                .group_by(User.team_id)
            )
        ).fetchall():
            stats.setdefault(row.team_id, {})["reviews"] = row.reviews

    zero = {"member_count": 0, "commits": 0, "net_lines": 0, "prs_opened": 0, "reviews": 0}
    summaries = [
        TeamSummary.model_validate({
            **{c.key: getattr(t, c.key) for c in t.__table__.columns},
            **{**zero, **stats.get(t.id, {})},
        })
        for t in teams
    ]
    return TeamsListResponse(teams=summaries, total=total)


@router.get("/{team_id}", response_model=TeamDetailResponse, summary="Get team with member stats")
async def get_team(
    team_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> TeamDetailResponse:
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=180)

    team = (
        await db.execute(
            select(Team).options(selectinload(Team.users)).where(Team.id == team_id)
        )
    ).scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    user_ids = [u.id for u in team.users]
    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)

    stats: dict[int, dict] = {
        u.id: {
            "id": u.id,
            "login": u.login,
            "name": u.name,
            "full_name": u.full_name,
            "avatar_url": u.avatar_url,
            "commits": 0,
            "additions": 0,
            "deletions": 0,
            "prs_opened": 0,
            "prs_merged": 0,
            "reviews": 0,
        }
        for u in team.users
    }

    if user_ids:
        # Commits
        for row in (
            await db.execute(
                select(
                    Commit.author_id,
                    func.count().label("commits"),
                    func.coalesce(func.sum(Commit.additions), 0).label("additions"),
                    func.coalesce(func.sum(Commit.deletions), 0).label("deletions"),
                )
                .where(
                    Commit.author_id.in_(user_ids),
                    Commit.committed_at >= start_dt,
                    Commit.committed_at <= end_dt,
                )
                .group_by(Commit.author_id)
            )
        ).fetchall():
            if row.author_id in stats:
                stats[row.author_id]["commits"] = row.commits
                stats[row.author_id]["additions"] = row.additions
                stats[row.author_id]["deletions"] = row.deletions

        # PRs
        for row in (
            await db.execute(
                select(
                    PullRequest.author_id,
                    func.count().label("prs_opened"),
                    func.coalesce(
                        func.sum(case((PullRequest.merged_at.isnot(None), 1), else_=0)), 0
                    ).label("prs_merged"),
                )
                .where(
                    PullRequest.author_id.in_(user_ids),
                    PullRequest.opened_at >= start_dt,
                    PullRequest.opened_at <= end_dt,
                )
                .group_by(PullRequest.author_id)
            )
        ).fetchall():
            if row.author_id in stats:
                stats[row.author_id]["prs_opened"] = row.prs_opened
                stats[row.author_id]["prs_merged"] = row.prs_merged

        # Reviews
        for row in (
            await db.execute(
                select(Review.reviewer_id, func.count().label("reviews"))
                .where(
                    Review.reviewer_id.in_(user_ids),
                    Review.submitted_at >= start_dt,
                    Review.submitted_at <= end_dt,
                )
                .group_by(Review.reviewer_id)
            )
        ).fetchall():
            if row.reviewer_id in stats:
                stats[row.reviewer_id]["reviews"] = row.reviews

    # Weekly breakdown per user (for line chart)
    weekly: list[WeeklyUserStat] = []
    if user_ids:
        _week = literal_column("'week'")
        week_trunc = func.date_trunc(_week, Commit.committed_at)
        week_rows = (
            await db.execute(
                select(
                    Commit.author_id,
                    week_trunc.label("week_start"),
                    func.count().label("commits"),
                    func.coalesce(
                        func.sum(Commit.additions - Commit.deletions), 0
                    ).label("net_lines"),
                )
                .where(
                    Commit.author_id.in_(user_ids),
                    Commit.committed_at >= start_dt,
                    Commit.committed_at <= end_dt,
                )
                .group_by(Commit.author_id, week_trunc)
                .order_by(week_trunc)
            )
        ).fetchall()
        for row in week_rows:
            if row.author_id in stats:
                ws = row.week_start
                weekly.append(
                    WeeklyUserStat(
                        week_start=ws.date() if hasattr(ws, "date") else ws,
                        user_id=row.author_id,
                        commits=row.commits,
                        net_lines=row.net_lines,
                    )
                )

    members = [UserStatRow(**s) for s in stats.values()]
    totals = UserStatRow(
        id=-1,
        login="Total",
        name=None,
        avatar_url=None,
        commits=sum(m.commits for m in members),
        additions=sum(m.additions for m in members),
        deletions=sum(m.deletions for m in members),
        prs_opened=sum(m.prs_opened for m in members),
        prs_merged=sum(m.prs_merged for m in members),
        reviews=sum(m.reviews for m in members),
    )

    return TeamDetailResponse(
        id=team.id,
        name=team.name,
        created_at=team.created_at,
        start_date=start_date,
        end_date=end_date,
        members=members,
        totals=totals,
        weekly=weekly,
    )


@router.post("", response_model=TeamSummary, status_code=201, summary="Create a team")
async def create_team(
    req: CreateTeamRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamSummary:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Team name cannot be blank")
    existing = (await db.execute(select(Team).where(Team.name == name))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A team with that name already exists")
    team = Team(name=name)
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return TeamSummary.model_validate(team)
