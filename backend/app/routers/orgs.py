import asyncio
import json
import os
import re
import sys

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import job_store
from app.config import settings
from app.database import get_db
from app.models.organization import Organization
from app.models.repository import Repository
from app.schemas.orgs import (
    OrgCreateRequest,
    OrgSummary,
    OrgUpdateRequest,
    OrgsListResponse,
    _mask_token,
)

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[^[\]]|\r")
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

router = APIRouter(prefix="/orgs", tags=["orgs"])

_GITHUB_API = "https://api.github.com"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


async def _fetch_github_profile(login: str, token: str) -> dict:
    """Try /orgs/{login}, fall back to /users/{login}. Returns partial dict on error."""
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=_GITHUB_API, headers=headers, timeout=10.0) as gh:
        for path in (f"/orgs/{login}", f"/users/{login}"):
            try:
                r = await gh.get(path)
                if r.status_code == 200:
                    data = r.json()
                    return {
                        "display_name": data.get("name") or data.get("login"),
                        "avatar_url":   data.get("avatar_url"),
                    }
            except Exception:
                pass
    return {}


async def _fetch_org_repos(login: str, token: str) -> list[dict]:
    """
    Fetch all non-archived, non-disabled repos for a GitHub org or user.
    Tries /orgs/{login}/repos first; falls back to /users/{login}/repos on 404.
    """
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=_GITHUB_API, headers=headers, timeout=30.0) as gh:
        for path in (f"/orgs/{login}/repos", f"/users/{login}/repos"):
            collected: list[dict] = []
            page = 1
            try:
                while True:
                    r = await gh.get(path, params={"per_page": 100, "page": page, "type": "all"})
                    if r.status_code == 404:
                        break           # try the next path
                    r.raise_for_status()
                    batch = r.json()
                    if not batch:
                        break
                    collected.extend(batch)
                    if len(batch) < 100:
                        break
                    page += 1
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    continue
                raise

            if collected:
                # Filter out archived / disabled repos
                return [r for r in collected if not r.get("archived") and not r.get("disabled")]

    return []


def _to_summary(org: Organization, repo_count: int) -> OrgSummary:
    return OrgSummary(
        id=org.id,
        login=org.login,
        display_name=org.display_name,
        avatar_url=org.avatar_url,
        token_preview=_mask_token(org.github_token),
        repo_count=repo_count,
        created_at=org.created_at,
    )


# ── GET /orgs ────────────────────────────────────────────────────────────────

@router.get("", response_model=OrgsListResponse)
async def list_orgs(db: AsyncSession = Depends(get_db)):
    orgs = (await db.execute(select(Organization).order_by(Organization.login))).scalars().all()

    # Count repos per org in one query (using FK, not string match)
    counts_rows = (await db.execute(
        select(Repository.organisation_id, func.count().label("n"))
        .where(Repository.organisation_id.in_([o.id for o in orgs]))
        .group_by(Repository.organisation_id)
    )).all()
    counts = {row.organisation_id: row.n for row in counts_rows}

    return OrgsListResponse(
        orgs=[_to_summary(o, counts.get(o.id, 0)) for o in orgs]
    )


# ── POST /orgs ───────────────────────────────────────────────────────────────

@router.post("", response_model=OrgSummary, status_code=201)
async def create_org(body: OrgCreateRequest, db: AsyncSession = Depends(get_db)):
    # Enrich with GitHub profile (avatar, display name)
    profile = await _fetch_github_profile(body.login, body.github_token)

    org = Organization(
        login=body.login,
        display_name=profile.get("display_name") or body.login,
        avatar_url=profile.get("avatar_url"),
        github_token=body.github_token,
    )
    db.add(org)
    try:
        await db.commit()
        await db.refresh(org)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Organisation '{body.login}' already exists")

    repo_count = (await db.execute(
        select(func.count()).select_from(Repository).where(Repository.organisation_id == org.id)
    )).scalar_one()

    return _to_summary(org, repo_count)


# ── PATCH /orgs/{org_id} ─────────────────────────────────────────────────────

@router.patch("/{org_id}", response_model=OrgSummary)
async def update_org(
    org_id: int,
    body: OrgUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    if body.display_name is not None:
        org.display_name = body.display_name
    if body.github_token is not None:
        org.github_token = body.github_token

    await db.commit()
    await db.refresh(org)

    repo_count = (await db.execute(
        select(func.count()).select_from(Repository).where(Repository.organisation_id == org.id)
    )).scalar_one()

    return _to_summary(org, repo_count)


# ── DELETE /orgs/{org_id} ────────────────────────────────────────────────────

@router.delete("/{org_id}", status_code=204)
async def delete_org(org_id: int, db: AsyncSession = Depends(get_db)):
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    await db.delete(org)
    await db.commit()


# ── POST /orgs/{org_id}/discover-repos ───────────────────────────────────────

@router.post("/{org_id}/discover-repos")
async def discover_org_repos(org_id: int, db: AsyncSession = Depends(get_db)):
    """
    Fetch every repo for this org from GitHub and upsert it into the DB
    (metadata only — no commits, PRs, or reviews are synced).
    Returns {"added": N, "total": N}.
    """
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    token = org.github_token or settings.github_token
    if not token:
        raise HTTPException(
            status_code=400,
            detail=f"No GitHub token configured for '{org.login}'. Update the token at /orgs.",
        )

    gh_repos = await _fetch_org_repos(org.login, token)
    if not gh_repos:
        return {"added": 0, "total": 0}

    # Find which github_ids are already tracked so we can report what's new
    existing_ids: set[int] = set(
        (await db.execute(
            select(Repository.github_id).where(
                Repository.github_id.in_([r["id"] for r in gh_repos])
            )
        )).scalars().all()
    )

    rows = [
        {
            "github_id": r["id"],
            "organisation_id": org.id,
            "name": r["name"],
            "full_name": r["full_name"],
            "default_branch": r.get("default_branch") or "main",
        }
        for r in gh_repos
    ]

    stmt = pg_insert(Repository).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["github_id"],
        set_={
            "organisation_id": stmt.excluded.organisation_id,
            "name": stmt.excluded.name,
            "full_name": stmt.excluded.full_name,
            "default_branch": stmt.excluded.default_branch,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    await db.commit()

    added = sum(1 for r in rows if r["github_id"] not in existing_ids)
    return {"added": added, "total": len(rows)}


# ── POST /orgs/{org_id}/sync ──────────────────────────────────────────────────

@router.post("/{org_id}/sync")
async def trigger_org_sync(
    org_id: int,
    phases: str = Query(default="all"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    login        = org.login                              # capture as plain string
    github_token = org.github_token or settings.github_token
    if not github_token:
        raise HTTPException(
            status_code=400,
            detail=f"No GitHub token configured for '{login}'. Update the token at /orgs.",
        )

    job = job_store.create_job()
    asyncio.create_task(_run_org_sync(job, login, github_token, phases))
    return JSONResponse({"job_id": job.job_id}, status_code=202)


async def _run_org_sync(
    job: job_store.SyncJob, login: str, token: str, phases: str
) -> None:
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "GITHUB_TOKEN": token}
    cmd = [sys.executable, "-m", "scripts.sync_github", login, "--process", phases, "--json"]
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


@router.get("/{org_id}/sync/{job_id}/stream")
async def stream_org_sync(org_id: int, job_id: str) -> StreamingResponse:
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
