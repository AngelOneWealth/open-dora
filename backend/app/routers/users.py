from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, literal_column, select, update
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Commit, PullRequest, Repository, Review, User, UserEmail
from app.schemas.users import (
    ActivityTotals,
    LinkMissingAuthorRequest,
    LinkMissingAuthorResponse,
    MergeUsersRequest,
    MissingAuthor,
    MissingAuthorsResponse,
    RepoStatRow,
    ReviewerInfo,
    UpdateUserRequest,
    UserDetailResponse,
    UserPRItem,
    UserPRsResponse,
    UserReviewItem,
    UserReviewsResponse,
    UserSummary,
    UsersListResponse,
    WeekActivity,
    WeeklyRepoStat,
)

router = APIRouter(prefix="/users", tags=["users"])


# ── helpers ───────────────────────────────────────────────────────────────────


def _user_summary(u: User) -> UserSummary:
    """Build a UserSummary including team_name from the loaded relationship."""
    return UserSummary.model_validate({
        **{c.key: getattr(u, c.key) for c in u.__table__.columns},
        "team_name": u.team.name if u.team else None,
    })


def _to_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _week_range(start: date, end: date) -> list[date]:
    """
    Return every Monday in the range of weeks that covers [start, end].
    The first Monday is the one on or before `start`; subsequent Mondays
    are added until the Monday is beyond `end`.
    """
    monday = start - timedelta(days=start.weekday())  # snap back to Monday
    weeks: list[date] = []
    while monday <= end:
        weeks.append(monday)
        monday += timedelta(weeks=1)
    return weeks


# ── routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=UsersListResponse, summary="List users")
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(None, description="Filter by login or name (case-insensitive)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=500, description="Max results to return"),
    active: bool = Query(True, description="Filter by active status"),
) -> UsersListResponse:
    """Return a paginated list of all synced GitHub users."""
    base = select(User).where(User.active == active)
    if q:
        pattern = f"%{q}%"
        base = base.where(User.login.ilike(pattern) | User.name.ilike(pattern))

    total: int = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        await db.execute(
            base.options(selectinload(User.team))
            .order_by(User.login).offset(offset).limit(limit)
        )
    ).scalars().all()

    # For active users, attach 6-month activity stats in parallel GROUP BY queries
    stats: dict[int, dict] = {}
    if active and rows:
        since = datetime.now(timezone.utc) - timedelta(days=180)
        user_ids = [u.id for u in rows]

        # Commits + net lines
        for stat in (
            await db.execute(
                select(
                    Commit.author_id,
                    func.count().label("commits"),
                    func.coalesce(func.sum(Commit.additions - Commit.deletions), 0).label("net_lines"),
                )
                .where(Commit.author_id.in_(user_ids), Commit.committed_at >= since)
                .group_by(Commit.author_id)
            )
        ).fetchall():
            stats.setdefault(stat.author_id, {})["commits"] = stat.commits
            stats[stat.author_id]["net_lines"] = stat.net_lines

        # PRs opened
        for stat in (
            await db.execute(
                select(PullRequest.author_id, func.count().label("prs_opened"))
                .where(PullRequest.author_id.in_(user_ids), PullRequest.opened_at >= since)
                .group_by(PullRequest.author_id)
            )
        ).fetchall():
            stats.setdefault(stat.author_id, {})["prs_opened"] = stat.prs_opened

        # Reviews
        for stat in (
            await db.execute(
                select(Review.reviewer_id, func.count().label("reviews"))
                .where(Review.reviewer_id.in_(user_ids), Review.submitted_at >= since)
                .group_by(Review.reviewer_id)
            )
        ).fetchall():
            stats.setdefault(stat.reviewer_id, {})["reviews"] = stat.reviews

    zero = {"commits": 0, "net_lines": 0, "prs_opened": 0, "reviews": 0}

    return UsersListResponse(
        users=[
            UserSummary.model_validate({
                **{c.key: getattr(u, c.key) for c in u.__table__.columns},
                "team_name": u.team.name if u.team else None,
                **{**zero, **stats.get(u.id, {})},
            })
            for u in rows
        ],
        total=total,
    )


@router.get("/missing", response_model=MissingAuthorsResponse, summary="Commits with no linked user")
async def list_missing_authors(
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> MissingAuthorsResponse:
    """Return distinct git author identities (name + email) that have no linked GitHub user."""
    base = (
        select(
            Commit.author_name,
            Commit.author_email,
            func.count().label("commit_count"),
        )
        .where(Commit.author_id.is_(None))
        .group_by(Commit.author_name, Commit.author_email)
        .order_by(func.count().desc())
    )
    total: int = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (await db.execute(base.offset(offset).limit(limit))).fetchall()
    return MissingAuthorsResponse(
        authors=[
            MissingAuthor(
                author_name=r.author_name,
                author_email=r.author_email,
                commit_count=r.commit_count,
            )
            for r in rows
        ],
        total=total,
    )


@router.post("/missing/link", response_model=LinkMissingAuthorResponse, summary="Link a git identity to a user")
async def link_missing_author(
    req: LinkMissingAuthorRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LinkMissingAuthorResponse:
    """Assign author_id on all matching commits and persist the email in user_emails."""
    user = (await db.execute(select(User).where(User.id == req.user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Persist the alternate email so future syncs resolve it automatically
    if req.author_email:
        existing = (
            await db.execute(select(UserEmail).where(UserEmail.email == req.author_email))
        ).scalar_one_or_none()
        if not existing:
            db.add(UserEmail(user_id=req.user_id, email=req.author_email))

    # Backfill existing commits that match this git identity
    result = await db.execute(
        update(Commit)
        .where(
            Commit.author_id.is_(None),
            Commit.author_name == req.author_name,
            Commit.author_email == req.author_email,
        )
        .values(author_id=req.user_id)
    )
    await db.commit()
    return LinkMissingAuthorResponse(updated_count=result.rowcount)


@router.patch("/{user_id}", response_model=UserSummary, summary="Update user fields")
async def update_user(
    user_id: int,
    req: UpdateUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSummary:
    """Update active status and/or team assignment for a user."""
    user = (
        await db.execute(
            select(User).options(selectinload(User.team)).where(User.id == user_id)
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if req.active is not None:
        user.active = req.active
    if req.team_id is not None:
        user.team_id = None if req.team_id == -1 else req.team_id
    if req.full_name is not None:
        user.full_name = req.full_name.strip() or None  # empty string → NULL
    await db.commit()
    await db.refresh(user)
    # Reload team relationship after refresh
    await db.refresh(user, ["team"])
    return _user_summary(user)


@router.post("/{target_id}/merge", response_model=UserSummary, summary="Merge a duplicate user into this one")
async def merge_users(
    target_id: int,
    req: MergeUsersRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSummary:
    """
    Reassign all activity (commits, PRs, reviews, emails) from source_id → target_id,
    then deactivate the source user.
    """
    if req.source_id == target_id:
        raise HTTPException(status_code=400, detail="source_id and target_id must differ")

    # Load both users (with team relationship for response)
    target = (await db.execute(
        select(User).options(selectinload(User.team)).where(User.id == target_id)
    )).scalar_one_or_none()
    source = (await db.execute(
        select(User).where(User.id == req.source_id)
    )).scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")
    if not source:
        raise HTTPException(status_code=404, detail="Source user not found")

    # 1. Reassign commits (author + committer)
    await db.execute(
        update(Commit).where(Commit.author_id == req.source_id).values(author_id=target_id)
    )
    await db.execute(
        update(Commit).where(Commit.committer_id == req.source_id).values(committer_id=target_id)
    )

    # 2. Reassign pull requests
    await db.execute(
        update(PullRequest).where(PullRequest.author_id == req.source_id).values(author_id=target_id)
    )

    # 3. Reassign reviews
    await db.execute(
        update(Review).where(Review.reviewer_id == req.source_id).values(reviewer_id=target_id)
    )

    # 4. Move emails — skip any that already exist on the target to avoid unique conflicts
    existing_emails = (await db.execute(
        select(UserEmail.email).where(UserEmail.user_id == target_id)
    )).scalars().all()
    existing_set = set(existing_emails)

    source_emails = (await db.execute(
        select(UserEmail).where(UserEmail.user_id == req.source_id)
    )).scalars().all()

    for ue in source_emails:
        if ue.email not in existing_set:
            ue.user_id = target_id
        else:
            await db.delete(ue)

    # 5. Deactivate source
    source.active = False

    await db.commit()
    await db.refresh(target)
    await db.refresh(target, ["team"])
    return _user_summary(target)


@router.get(
    "/{user_id}",
    response_model=UserDetailResponse,
    summary="User activity by week",
)
async def get_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    start_date: date = Query(..., description="Start date (inclusive), e.g. 2024-01-01"),
    end_date: date = Query(..., description="End date (inclusive), e.g. 2024-12-31"),
) -> UserDetailResponse:
    """
    Return a user's commit, PR, and review counts grouped by ISO week
    (Monday → Sunday).  Every week between `start_date` and `end_date` is
    included even if the user had no activity — those weeks show zeros.
    """
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be >= start_date")

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Convert inclusive date range to a half-open UTC datetime range
    start_dt = _to_utc(start_date)
    end_dt = _to_utc(end_date) + timedelta(days=1)

    # ── commits authored per week ─────────────────────────────────────────────
    commit_rows = (
        await db.execute(
            select(
                func.date_trunc("week", Commit.authored_at).label("week_start"),
                func.count().label("commits"),
                func.coalesce(func.sum(Commit.additions), 0).label("additions"),
                func.coalesce(func.sum(Commit.deletions), 0).label("deletions"),
            )
            .where(
                Commit.author_id == user_id,
                Commit.authored_at >= start_dt,
                Commit.authored_at < end_dt,
            )
            .group_by("week_start")
            .order_by("week_start")
        )
    ).fetchall()

    # ── pull requests opened per week ─────────────────────────────────────────
    pr_rows = (
        await db.execute(
            select(
                func.date_trunc("week", PullRequest.opened_at).label("week_start"),
                func.count().label("prs_opened"),
                # COUNT on a nullable column counts only non-null values
                func.count(PullRequest.merged_at).label("prs_merged"),
            )
            .where(
                PullRequest.author_id == user_id,
                PullRequest.opened_at >= start_dt,
                PullRequest.opened_at < end_dt,
            )
            .group_by("week_start")
            .order_by("week_start")
        )
    ).fetchall()

    # ── reviews submitted per week ────────────────────────────────────────────
    review_rows = (
        await db.execute(
            select(
                func.date_trunc("week", Review.submitted_at).label("week_start"),
                func.count().label("reviews"),
            )
            .where(
                Review.reviewer_id == user_id,
                Review.submitted_at >= start_dt,
                Review.submitted_at < end_dt,
            )
            .group_by("week_start")
            .order_by("week_start")
        )
    ).fetchall()

    # ── merge results into a full week time series ────────────────────────────
    commit_by_week = {r.week_start.date(): r for r in commit_rows}
    pr_by_week = {r.week_start.date(): r for r in pr_rows}
    review_by_week = {r.week_start.date(): r for r in review_rows}

    weeks: list[WeekActivity] = []
    for monday in _week_range(start_date, end_date):
        c = commit_by_week.get(monday)
        p = pr_by_week.get(monday)
        r = review_by_week.get(monday)
        weeks.append(
            WeekActivity(
                week_start=monday,
                commits=c.commits if c else 0,
                additions=c.additions if c else 0,
                deletions=c.deletions if c else 0,
                prs_opened=p.prs_opened if p else 0,
                prs_merged=p.prs_merged if p else 0,
                reviews=r.reviews if r else 0,
            )
        )

    totals = ActivityTotals(
        commits=sum(w.commits for w in weeks),
        additions=sum(w.additions for w in weeks),
        deletions=sum(w.deletions for w in weeks),
        prs_opened=sum(w.prs_opened for w in weeks),
        prs_merged=sum(w.prs_merged for w in weeks),
        reviews=sum(w.reviews for w in weeks),
    )

    # ── per-repo stats ────────────────────────────────────────────────────────
    repo_commit_rows = (
        await db.execute(
            select(
                Commit.repository_id,
                Repository.full_name.label("repo_name"),
                func.count().label("commits"),
                func.coalesce(func.sum(Commit.additions), 0).label("additions"),
                func.coalesce(func.sum(Commit.deletions), 0).label("deletions"),
            )
            .join(Repository, Repository.id == Commit.repository_id)
            .where(
                Commit.author_id == user_id,
                Commit.authored_at >= start_dt,
                Commit.authored_at < end_dt,
            )
            .group_by(Commit.repository_id, Repository.full_name)
        )
    ).fetchall()

    repo_pr_rows = (
        await db.execute(
            select(
                PullRequest.repository_id,
                func.count().label("prs_opened"),
                func.count(PullRequest.merged_at).label("prs_merged"),
            )
            .where(
                PullRequest.author_id == user_id,
                PullRequest.opened_at >= start_dt,
                PullRequest.opened_at < end_dt,
            )
            .group_by(PullRequest.repository_id)
        )
    ).fetchall()

    repo_review_rows = (
        await db.execute(
            select(PullRequest.repository_id, func.count().label("reviews"))
            .select_from(Review)
            .join(PullRequest, PullRequest.id == Review.pull_request_id)
            .where(
                Review.reviewer_id == user_id,
                Review.submitted_at >= start_dt,
                Review.submitted_at < end_dt,
            )
            .group_by(PullRequest.repository_id)
        )
    ).fetchall()

    # Build repo stats dict keyed by repo_id
    repo_stats: dict[int, dict] = {
        row.repository_id: {
            "repo_id": row.repository_id,
            "repo_name": row.repo_name,
            "commits": row.commits,
            "additions": row.additions,
            "deletions": row.deletions,
            "prs_opened": 0,
            "prs_merged": 0,
            "reviews": 0,
        }
        for row in repo_commit_rows
    }
    for row in repo_pr_rows:
        if row.repository_id in repo_stats:
            repo_stats[row.repository_id]["prs_opened"] = row.prs_opened
            repo_stats[row.repository_id]["prs_merged"] = row.prs_merged
        else:
            # PRs in repos with no commits in range — still worth showing
            repo_stats[row.repository_id] = {
                "repo_id": row.repository_id,
                "repo_name": str(row.repository_id),
                "commits": 0,
                "additions": 0,
                "deletions": 0,
                "prs_opened": row.prs_opened,
                "prs_merged": row.prs_merged,
                "reviews": 0,
            }
    for row in repo_review_rows:
        if row.repository_id in repo_stats:
            repo_stats[row.repository_id]["reviews"] = row.reviews

    repos = [RepoStatRow(**s) for s in repo_stats.values()]

    # ── per-repo weekly breakdown ─────────────────────────────────────────────
    _week = literal_column("'week'")
    week_trunc = func.date_trunc(_week, Commit.authored_at)
    weekly_repo_rows = (
        await db.execute(
            select(
                Commit.repository_id,
                week_trunc.label("week_start"),
                func.count().label("commits"),
                func.coalesce(
                    func.sum(Commit.additions - Commit.deletions), 0
                ).label("net_lines"),
            )
            .where(
                Commit.author_id == user_id,
                Commit.authored_at >= start_dt,
                Commit.authored_at < end_dt,
            )
            .group_by(Commit.repository_id, week_trunc)
            .order_by(week_trunc)
        )
    ).fetchall()

    weekly_by_repo = [
        WeeklyRepoStat(
            week_start=row.week_start.date() if hasattr(row.week_start, "date") else row.week_start,
            repo_id=row.repository_id,
            commits=row.commits,
            net_lines=row.net_lines,
        )
        for row in weekly_repo_rows
    ]

    return UserDetailResponse(
        id=user.id,
        github_id=user.github_id,
        login=user.login,
        name=user.name,
        full_name=user.full_name,
        email=user.email,
        avatar_url=user.avatar_url,
        start_date=start_date,
        end_date=end_date,
        weeks=weeks,
        totals=totals,
        repos=repos,
        weekly_by_repo=weekly_by_repo,
    )


# ── per-user PR list ──────────────────────────────────────────────────────────


@router.get("/{user_id}/prs", response_model=UserPRsResponse)
async def list_user_prs(
    user_id: int,
    status: str | None = Query(default=None),  # "open" | "merged" | "closed"
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=180)

    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    end_dt   = datetime(end_date.year,   end_date.month,   end_date.day, 23, 59, 59, tzinfo=timezone.utc)

    stmt = (
        select(PullRequest, Repository.full_name.label("repo_full_name"))
        .join(Repository, Repository.id == PullRequest.repository_id)
        .where(
            PullRequest.author_id == user_id,
            PullRequest.opened_at >= start_dt,
            PullRequest.opened_at <= end_dt,
        )
    )
    if status == "open":
        stmt = stmt.where(PullRequest.state == "open")
    elif status == "merged":
        stmt = stmt.where(PullRequest.state == "merged")
    elif status == "closed":
        stmt = stmt.where(PullRequest.state == "closed")

    stmt = stmt.order_by(PullRequest.opened_at.desc())

    rows = (await db.execute(stmt)).all()

    # ── batch-load reviewers (single query, no N+1) ───────────────────────────
    pr_ids = [row.PullRequest.id for row in rows]
    # dict: pr_id → {user_id → latest ReviewerInfo dict}
    # ordered by submitted_at so later overwrites earlier (keeps final state)
    reviewers_by_pr: dict[int, dict[int, dict]] = {}
    if pr_ids:
        rev_rows = (
            await db.execute(
                select(
                    Review.pull_request_id,
                    Review.state,
                    User.id.label("user_id"),
                    User.login,
                    User.name,
                    User.full_name,
                    User.avatar_url,
                )
                .select_from(Review)
                .join(User, User.id == Review.reviewer_id)
                .where(Review.pull_request_id.in_(pr_ids))
                .order_by(Review.pull_request_id, Review.submitted_at)
            )
        ).all()

        for r in rev_rows:
            pr_map = reviewers_by_pr.setdefault(r.pull_request_id, {})
            pr_map[r.user_id] = {   # overwrite keeps the latest review state
                "id": r.user_id,
                "login": r.login,
                "name": r.name,
                "full_name": r.full_name,
                "avatar_url": r.avatar_url,
                "state": r.state,
            }

    prs = [
        UserPRItem(
            id=row.PullRequest.id,
            number=row.PullRequest.number,
            title=row.PullRequest.title,
            state=row.PullRequest.state,
            repo_full_name=row.repo_full_name,
            github_url=f"https://github.com/{row.repo_full_name}/pull/{row.PullRequest.number}",
            opened_at=row.PullRequest.opened_at,
            merged_at=row.PullRequest.merged_at,
            closed_at=row.PullRequest.closed_at,
            additions=row.PullRequest.additions or 0,
            deletions=row.PullRequest.deletions or 0,
            changed_files=row.PullRequest.changed_files or 0,
            commits_count=row.PullRequest.commits_count or 0,
            reviewers=[
                ReviewerInfo(**v)
                for v in reviewers_by_pr.get(row.PullRequest.id, {}).values()
            ],
        )
        for row in rows
    ]

    return UserPRsResponse(prs=prs, total=len(prs))


# ── per-user review list ──────────────────────────────────────────────────────


@router.get("/{user_id}/reviews", response_model=UserReviewsResponse)
async def list_user_reviews(
    user_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=180)

    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    end_dt   = datetime(end_date.year,   end_date.month,   end_date.day, 23, 59, 59, tzinfo=timezone.utc)

    PRAuthor = aliased(User, flat=True)

    rows = (
        await db.execute(
            select(
                Review,
                PullRequest.number.label("pr_number"),
                PullRequest.title.label("pr_title"),
                PullRequest.state.label("pr_state"),
                Repository.full_name.label("repo_full_name"),
                PRAuthor.login.label("pr_author_login"),
                PRAuthor.name.label("pr_author_name"),
                PRAuthor.full_name.label("pr_author_full_name"),
                PRAuthor.avatar_url.label("pr_author_avatar_url"),
            )
            .select_from(Review)
            .join(PullRequest, PullRequest.id == Review.pull_request_id)
            .join(Repository, Repository.id == PullRequest.repository_id)
            .outerjoin(PRAuthor, PRAuthor.id == PullRequest.author_id)
            .where(
                Review.reviewer_id == user_id,
                Review.submitted_at >= start_dt,
                Review.submitted_at <= end_dt,
            )
            .order_by(Review.submitted_at.desc())
        )
    ).all()

    reviews = [
        UserReviewItem(
            id=row.Review.id,
            state=row.Review.state,
            submitted_at=row.Review.submitted_at,
            pr_number=row.pr_number,
            pr_title=row.pr_title,
            pr_state=row.pr_state,
            repo_full_name=row.repo_full_name,
            github_url=f"https://github.com/{row.repo_full_name}/pull/{row.pr_number}",
            pr_author_login=row.pr_author_login,
            pr_author_name=row.pr_author_full_name or row.pr_author_name,
            pr_author_avatar_url=row.pr_author_avatar_url,
        )
        for row in rows
    ]

    return UserReviewsResponse(reviews=reviews, total=len(reviews))
