import asyncio
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import case, delete as sa_delete, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import job_store
from app.config import settings
from app.database import get_db
from app.models import Commit, PullRequest, PullRequestCommit, PullRequestLabel, Review, User
from app.models.organization import Organization
from app.models.repository import Repository
from app.schemas.repos import RepoDetailResponse, RepoListResponse, RepoSummary  # noqa: F401
from app.schemas.teams import UserStatRow, WeeklyUserStat

router = APIRouter(prefix="/repos", tags=["repos"])


@router.get("", response_model=RepoListResponse)
async def list_repos(
    q: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Repository).where(Repository.active == True)  # noqa: E712
    count_query = select(func.count()).select_from(Repository).where(Repository.active == True)  # noqa: E712
    if q:
        like = f"%{q}%"
        query = query.where(Repository.full_name.ilike(like))
        count_query = count_query.where(Repository.full_name.ilike(like))
    total = (await db.execute(count_query)).scalar_one()
    repos = (
        await db.execute(
            query.order_by(Repository.full_name).offset(offset).limit(limit)
        )
    ).scalars().all()

    stats: dict[int, dict] = {}
    if repos:
        since = datetime.now(timezone.utc) - timedelta(days=180)
        repo_ids = [r.id for r in repos]

        # Commits + net lines
        for row in (
            await db.execute(
                select(
                    Commit.repository_id,
                    func.count().label("commits"),
                    func.coalesce(func.sum(Commit.additions - Commit.deletions), 0).label("net_lines"),
                )
                .where(Commit.repository_id.in_(repo_ids), Commit.committed_at >= since)
                .group_by(Commit.repository_id)
            )
        ).fetchall():
            stats.setdefault(row.repository_id, {})["commits"] = row.commits
            stats[row.repository_id]["net_lines"] = row.net_lines

        # PRs opened
        for row in (
            await db.execute(
                select(PullRequest.repository_id, func.count().label("prs_opened"))
                .where(PullRequest.repository_id.in_(repo_ids), PullRequest.opened_at >= since)
                .group_by(PullRequest.repository_id)
            )
        ).fetchall():
            stats.setdefault(row.repository_id, {})["prs_opened"] = row.prs_opened

        # Reviews (via PR join to scope by repo)
        for row in (
            await db.execute(
                select(PullRequest.repository_id, func.count().label("reviews"))
                .select_from(Review)
                .join(PullRequest, PullRequest.id == Review.pull_request_id)
                .where(PullRequest.repository_id.in_(repo_ids), Review.submitted_at >= since)
                .group_by(PullRequest.repository_id)
            )
        ).fetchall():
            stats.setdefault(row.repository_id, {})["reviews"] = row.reviews

        # Distinct contributors
        for row in (
            await db.execute(
                select(Commit.repository_id, func.count(Commit.author_id.distinct()).label("contributors"))
                .where(
                    Commit.repository_id.in_(repo_ids),
                    Commit.committed_at >= since,
                    Commit.author_id.isnot(None),
                )
                .group_by(Commit.repository_id)
            )
        ).fetchall():
            stats.setdefault(row.repository_id, {})["contributors"] = row.contributors

    zero = {"commits": 0, "net_lines": 0, "prs_opened": 0, "reviews": 0, "contributors": 0}
    summaries = [
        RepoSummary.model_validate({
            **{c.key: getattr(r, c.key) for c in r.__table__.columns},
            "owner": r.owner,   # property derived from full_name, not a DB column
            **{**zero, **stats.get(r.id, {})},
        })
        for r in repos
    ]
    return RepoListResponse(repos=summaries, total=total)


@router.get("/{repo_id}", response_model=RepoDetailResponse, summary="Repo contributor stats")
async def get_repo_detail(
    repo_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> RepoDetailResponse:
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=180)

    repo = (
        await db.execute(select(Repository).where(Repository.id == repo_id))
    ).scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)

    # Discover contributors dynamically — inner join naturally excludes NULL author_id
    contributor_rows = (
        await db.execute(
            select(User.id, User.login, User.name, User.full_name, User.avatar_url)
            .join(Commit, Commit.author_id == User.id)
            .where(
                Commit.repository_id == repo_id,
                Commit.committed_at >= start_dt,
                Commit.committed_at <= end_dt,
            )
            .distinct()
        )
    ).fetchall()

    stats: dict[int, dict] = {
        row.id: {
            "id": row.id,
            "login": row.login,
            "name": row.name,
            "full_name": row.full_name,
            "avatar_url": row.avatar_url,
            "commits": 0,
            "additions": 0,
            "deletions": 0,
            "prs_opened": 0,
            "prs_merged": 0,
            "reviews": 0,
        }
        for row in contributor_rows
    }
    contributor_ids = list(stats.keys())
    weekly: list[WeeklyUserStat] = []

    if contributor_ids:
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
                    Commit.repository_id == repo_id,
                    Commit.author_id.in_(contributor_ids),
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
                    PullRequest.repository_id == repo_id,
                    PullRequest.author_id.in_(contributor_ids),
                    PullRequest.opened_at >= start_dt,
                    PullRequest.opened_at <= end_dt,
                )
                .group_by(PullRequest.author_id)
            )
        ).fetchall():
            if row.author_id in stats:
                stats[row.author_id]["prs_opened"] = row.prs_opened
                stats[row.author_id]["prs_merged"] = row.prs_merged

        # Reviews — JOIN through PullRequest to scope by repo
        for row in (
            await db.execute(
                select(Review.reviewer_id, func.count().label("reviews"))
                .join(PullRequest, PullRequest.id == Review.pull_request_id)
                .where(
                    PullRequest.repository_id == repo_id,
                    Review.reviewer_id.in_(contributor_ids),
                    Review.submitted_at >= start_dt,
                    Review.submitted_at <= end_dt,
                )
                .group_by(Review.reviewer_id)
            )
        ).fetchall():
            if row.reviewer_id in stats:
                stats[row.reviewer_id]["reviews"] = row.reviews

        # Weekly breakdown (literal_column avoids PostgreSQL bind-param GROUP BY error)
        _week = literal_column("'week'")
        week_trunc = func.date_trunc(_week, Commit.committed_at)
        for row in (
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
                    Commit.repository_id == repo_id,
                    Commit.author_id.in_(contributor_ids),
                    Commit.committed_at >= start_dt,
                    Commit.committed_at <= end_dt,
                )
                .group_by(Commit.author_id, week_trunc)
                .order_by(week_trunc)
            )
        ).fetchall():
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

    contributors = [UserStatRow(**s) for s in stats.values()]
    totals = UserStatRow(
        id=-1,
        login="Total",
        name=None,
        avatar_url=None,
        commits=sum(c.commits for c in contributors),
        additions=sum(c.additions for c in contributors),
        deletions=sum(c.deletions for c in contributors),
        prs_opened=sum(c.prs_opened for c in contributors),
        prs_merged=sum(c.prs_merged for c in contributors),
        reviews=sum(c.reviews for c in contributors),
    )

    return RepoDetailResponse(
        id=repo.id,
        owner=repo.owner,
        name=repo.name,
        full_name=repo.full_name,
        default_branch=repo.default_branch,
        start_date=start_date,
        end_date=end_date,
        contributors=contributors,
        totals=totals,
        weekly=weekly,
    )


# ── archive ───────────────────────────────────────────────────────────────────


@router.delete("/{repo_id}", summary="Archive a repository — delete its data and exclude from future syncs")
async def archive_repo(
    repo_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    repo = (await db.execute(select(Repository).where(Repository.id == repo_id))).scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # 1. Fetch PR IDs for this repo
    pr_ids_result = await db.execute(select(PullRequest.id).where(PullRequest.repository_id == repo_id))
    pr_ids = [row[0] for row in pr_ids_result.fetchall()]

    if pr_ids:
        # 2. Delete PR labels
        await db.execute(sa_delete(PullRequestLabel).where(PullRequestLabel.pull_request_id.in_(pr_ids)))
        # 3. Delete PR commits (pr_commits join table)
        await db.execute(sa_delete(PullRequestCommit).where(PullRequestCommit.pull_request_id.in_(pr_ids)))
        # 4. Delete reviews
        await db.execute(sa_delete(Review).where(Review.pull_request_id.in_(pr_ids)))

    # 5. Delete commits
    await db.execute(sa_delete(Commit).where(Commit.repository_id == repo_id))

    # 6. Delete PRs
    await db.execute(sa_delete(PullRequest).where(PullRequest.repository_id == repo_id))

    # 7. Mark inactive and clear sync timestamps
    repo.active = False
    repo.commits_synced_at = None
    repo.prs_synced_at = None
    repo.reviews_synced_at = None
    repo.pr_commits_synced_at = None

    await db.commit()
    return {"id": repo_id, "active": False}


# ── sync ──────────────────────────────────────────────────────────────────────

# Strips ANSI/VT control sequences produced by Rich's terminal output
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[^[\]]|\r")

# backend/ is two levels up from this file (backend/app/routers/repos.py)
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


@router.post("/{repo_id}/sync")
async def trigger_sync(
    repo_id: int,
    phases: str = Query(default="all"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    repo = (
        await db.execute(select(Repository).where(Repository.id == repo_id))
    ).scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    full_name = repo.full_name           # capture as plain string before session closes
    owner     = repo.owner

    org_row = (
        await db.execute(select(Organization).where(Organization.id == repo.organisation_id))
    ).scalar_one_or_none() if repo.organisation_id else None
    github_token = (org_row.github_token if org_row else None) or settings.github_token
    if not github_token:
        raise HTTPException(
            status_code=400,
            detail=f"No GitHub token configured for '{owner}'. Add one at /orgs.",
        )

    job = job_store.create_job()
    asyncio.create_task(_run_repo_sync(job, full_name, github_token, phases))
    return JSONResponse({"job_id": job.job_id}, status_code=202)


async def _run_repo_sync(
    job: job_store.SyncJob, full_name: str, token: str, phases: str
) -> None:
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "GITHUB_TOKEN": token}
    cmd = [sys.executable, "-m", "scripts.sync_github", full_name, "--process", phases, "--json"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=_BACKEND_DIR, env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async for line in proc.stdout:
            if line.strip():
                await job_store.publish_line(job, line)
        await proc.wait()
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    finally:
        await job_store.finish_job(job, proc.returncode or 1)


@router.get("/{repo_id}/sync/{job_id}/stream")
async def stream_sync(repo_id: int, job_id: str) -> StreamingResponse:
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")

    async def generate():
        q, replay_offset = job_store.subscribe(job)
        try:
            for line in job.lines[:replay_offset]:
                yield line
            while True:
                line = await asyncio.wait_for(q.get(), timeout=60.0)
                if line is None:  # sentinel: job finished
                    break
                yield line
        except asyncio.TimeoutError:
            pass
        finally:
            job_store.unsubscribe(job, q)

    return StreamingResponse(generate(), media_type="application/x-ndjson")
