#!/usr/bin/env python3
"""
Sync GitHub repositories (commits, PRs, reviews) into the database.

Usage:
    # Sync all repos in one or more orgs/users:
    python -m scripts.sync_github myorg
    python -m scripts.sync_github myorg anotherog

    # Or mix explicit repos with orgs:
    python -m scripts.sync_github myorg owner/specific-repo

    # Or configure in .env and run without args:
    #   GITHUB_ORGS=myorg,anotherorg
    #   GITHUB_REPOS=owner/extra-repo      (optional, stacked on top)
"""

import asyncio
import json
import re
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Commit, Label, PullRequest, PullRequestCommit, PullRequestLabel, Repository, Review, User, UserEmail
from app.models.organization import Organization
from app.models.pull_request import PRState
from app.models.review import ReviewState

BATCH_SIZE = 10
STATS_CONCURRENCY = 5    # max parallel requests when fetching per-commit stats
PROFILE_CONCURRENCY = 5  # GET /users/{login} hits the core rate limit (5 000/hr)
GITHUB_API = "https://api.github.com"

# GitHub noreply email formats:
#   modern: 12345678+username@users.noreply.github.com  (contains the numeric user ID)
#   legacy: username@users.noreply.github.com           (login only, needs a /users lookup)
_NOREPLY_RE = re.compile(
    r"^(?:(\d+)\+)?([^@]+)@users\.noreply\.github\.com$", re.IGNORECASE
)


def parse_noreply_email(email: str) -> tuple[int | None, str | None]:
    """
    Parse a GitHub noreply email and return (github_id, login).
    Returns (None, None) if the email is not a noreply address.
    github_id is None for the legacy format (login-only).
    """
    m = _NOREPLY_RE.match(email)
    if not m:
        return None, None
    github_id = int(m.group(1)) if m.group(1) else None
    login = m.group(2)
    return github_id, login


# ─────────────────────────── stats ───────────────────────────


@dataclass
class RepoStats:
    full_name: str
    commits: int = 0
    prs: int = 0
    reviews: int = 0
    users_enriched: int = 0
    status: str = "pending"   # pending | syncing | done | error
    phase: str = ""           # fine-grained sub-phase detail (shown below badges)
    error: str | None = None
    # Per-phase status: pending | syncing | done | error
    commits_status:    str = "pending"
    prs_status:        str = "pending"
    reviews_status:    str = "pending"
    pr_commits_status: str = "pending"

    def _badge(self, label: str, phase_status: str) -> str:
        if phase_status == "done":
            return f"[green]✓ {label}[/green]"
        if phase_status == "syncing":
            return f"[yellow]⟳ {label}[/yellow]"
        if phase_status == "error":
            return f"[red]✗ {label}[/red]"
        return f"[dim]· {label}[/dim]"

    def status_cell(self) -> str:
        if self.status == "pending":
            return "[dim]Pending[/dim]"
        if self.status == "done":
            return (
                "  ".join([
                    self._badge("commits", "done"),
                    self._badge("PRs", "done"),
                    self._badge("reviews", "done"),
                    self._badge("PR-links", "done"),
                ])
            )
        if self.error:
            badges = "  ".join([
                self._badge("commits",  self.commits_status),
                self._badge("PRs",      self.prs_status),
                self._badge("reviews",  self.reviews_status),
                self._badge("PR-links", self.pr_commits_status),
            ])
            return f"{badges}\n[red]{self.error[:60]}[/red]"
        # syncing — show per-phase badges + current detail underneath
        badges = "  ".join([
            self._badge("commits",  self.commits_status),
            self._badge("PRs",      self.prs_status),
            self._badge("reviews",  self.reviews_status),
            self._badge("PR-links", self.pr_commits_status),
        ])
        if self.phase:
            return f"{badges}\n[dim italic]{self.phase}[/dim italic]"
        return badges


# ─────────────────────────── JSON emission (--json mode) ───────────────────────────


def emit_json(stats: RepoStats) -> None:
    """Write one NDJSON line describing the current sync state of a repo."""
    sys.stdout.write(json.dumps({
        "type": "repo",
        "full_name": stats.full_name,
        "status": stats.status,
        "phase": stats.phase,
        "commits": stats.commits,
        "prs": stats.prs,
        "reviews": stats.reviews,
        "users_enriched": stats.users_enriched,
        "commits_status": stats.commits_status,
        "prs_status": stats.prs_status,
        "reviews_status": stats.reviews_status,
        "pr_commits_status": stats.pr_commits_status,
    }) + "\n")
    sys.stdout.flush()


class ThrottledEmit:
    """Wraps emit_json with a time-based throttle so we don't flood stdout."""

    def __init__(self, stats: RepoStats, interval: float = 0.5) -> None:
        self._stats = stats
        self._interval = interval
        self._last_emit: float = 0.0

    def emit(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or (now - self._last_emit) >= self._interval:
            emit_json(self._stats)
            self._last_emit = now

    def force(self) -> None:
        self.emit(force=True)


# ─────────────────────────── display ───────────────────────────


def build_display(stats_list: list[RepoStats], overall: Progress) -> Panel:
    table = Table(box=box.SIMPLE_HEAVY, header_style="bold cyan", expand=True, show_edge=False)
    table.add_column("Repository", ratio=3)
    table.add_column("Commits", justify="right", ratio=1)
    table.add_column("PRs", justify="right", ratio=1)
    table.add_column("Reviews", justify="right", ratio=1)
    table.add_column("Phase status", ratio=5)

    for s in stats_list:
        table.add_row(
            f"[bold]{s.full_name}[/bold]",
            f"{s.commits:,}" if s.commits else "–",
            f"{s.prs:,}" if s.prs else "–",
            f"{s.reviews:,}" if s.reviews else "–",
            s.status_cell(),
        )

    return Panel(Group(table, overall), title="[bold blue]GitHub Sync[/bold blue]", border_style="blue")


class _LiveDisplay:
    """Renderable that re-evaluates build_display() on every auto-refresh tick.

    Rich's Live stores a single renderable and re-renders it each tick.  If we
    pass a frozen Panel (the return value of build_display) the Table rows are
    baked in at that moment and never update.  By passing this class instead,
    __rich_console__ is called on every tick so the Table is rebuilt from the
    current stats state, making badge transitions visible in real time.
    """

    def __init__(self, stats_list: list[RepoStats], overall: Progress) -> None:
        self._stats_list = stats_list
        self._overall = overall

    def __rich_console__(self, console, options):
        yield build_display(self._stats_list, self._overall)


# ─────────────────────────── github client ───────────────────────────


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._http = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, **params: Any) -> Any:
        resp = await self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def paginate(
        self,
        path: str,
        *,
        stop_at_dt: datetime | None = None,
        dt_field: str = "updated_at",
        **params: Any,
    ) -> list[dict]:
        """
        Fetch all pages (100 items each) and return combined list.

        stop_at_dt: stop early once an item's `dt_field` is older than this
                    timestamp. Use with APIs sorted newest-first so we skip
                    anything we already have from a previous sync.
        """
        items: list[dict] = []
        page = 1
        while True:
            batch = await self.get(path, per_page=BATCH_SIZE, page=page, **params)
            if not batch:
                break
            if stop_at_dt:
                keep: list[dict] = []
                stop = False
                for item in batch:
                    item_dt = parse_dt(item.get(dt_field))
                    if item_dt is not None and item_dt < stop_at_dt:
                        stop = True
                        break
                    keep.append(item)
                items.extend(keep)
                if stop:
                    break
            else:
                items.extend(batch)
            if len(batch) < BATCH_SIZE:
                break
            page += 1
        return items

    async def fetch_org_repos(self, org: str) -> list[dict]:
        """
        Return all repos for an org or user account.
        Tries /orgs/{org}/repos first; falls back to /users/{org}/repos
        if the org endpoint returns 404 (i.e. it's a personal account).
        Skips archived and disabled repos.
        """
        try:
            repos = await self.paginate(f"/orgs/{org}/repos", type="all", sort="full_name", direction="asc")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                repos = await self.paginate(f"/users/{org}/repos", type="all", sort="full_name", direction="asc")
            else:
                raise
        return [r for r in repos if not r.get("archived") and not r.get("disabled")]


# ─────────────────────────── helpers ───────────────────────────


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


# ─────────────────────────── upserts ───────────────────────────


async def upsert_users(session, users: list[dict]) -> dict[int, int]:
    """Insert/update users. Returns {github_id: db_id}."""
    if not users:
        return {}
    rows = [
        {
            "github_id": u["id"],
            "login": u["login"],
            "avatar_url": u.get("avatar_url"),
            # name / email are only present on full profile responses;
            # list-API responses leave them absent (None here).
            "name": u.get("name"),
            "email": u.get("email"),
        }
        for u in users
    ]
    stmt = pg_insert(User).values(rows)
    tbl = User.__table__.c
    stmt = stmt.on_conflict_do_update(
        index_elements=["github_id"],
        set_={
            "login": stmt.excluded.login,
            # COALESCE: never overwrite a known value with null.
            # When a list-API object arrives (name=None) we keep whatever
            # the DB already has; when a full profile arrives we update it.
            "avatar_url": func.coalesce(stmt.excluded.avatar_url, tbl.avatar_url),
            "name": func.coalesce(stmt.excluded.name, tbl.name),
            "email": func.coalesce(stmt.excluded.email, tbl.email),
            "updated_at": func.now(),
        },
    ).returning(User.github_id, User.id)
    result = await session.execute(stmt)
    return {gh_id: db_id for gh_id, db_id in result.fetchall()}


async def upsert_repository(session, owner: str, name: str, data: dict) -> int:
    # Resolve organisation_id via owner login (None if org not yet registered)
    org_id = (await session.execute(
        select(Organization.id).where(Organization.login == owner)
    )).scalar_one_or_none()

    stmt = pg_insert(Repository).values(
        github_id=data["id"],
        organisation_id=org_id,
        name=name,
        full_name=data["full_name"],
        default_branch=data.get("default_branch", "main"),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["github_id"],
        set_={
            "organisation_id": stmt.excluded.organisation_id,
            "name": stmt.excluded.name,
            "full_name": stmt.excluded.full_name,
            "default_branch": stmt.excluded.default_branch,
            "updated_at": func.now(),
        },
    ).returning(Repository.id)
    result = await session.execute(stmt)
    return result.scalar_one()


async def upsert_commits(session, rows: list[dict]) -> None:
    stmt = pg_insert(Commit).values(rows)
    tbl = Commit.__table__.c
    stmt = stmt.on_conflict_do_update(
        index_elements=["sha"],
        set_={
            # COALESCE: keep the existing value when the incoming one is NULL.
            # This prevents a re-sync from overwriting a previously resolved
            # author_id / committer_id with NULL if GitHub temporarily unlinks it.
            "author_id": func.coalesce(stmt.excluded.author_id, tbl.author_id),
            "committer_id": func.coalesce(stmt.excluded.committer_id, tbl.committer_id),
            # Raw git identity — always overwrite since this never changes.
            "author_name": stmt.excluded.author_name,
            "author_email": stmt.excluded.author_email,
            "committer_name": stmt.excluded.committer_name,
            "committer_email": stmt.excluded.committer_email,
            "message": stmt.excluded.message,
            "additions": stmt.excluded.additions,
            "deletions": stmt.excluded.deletions,
            "net_lines": stmt.excluded.net_lines,
            "authored_at": stmt.excluded.authored_at,
            "committed_at": stmt.excluded.committed_at,
        },
    )
    await session.execute(stmt)


async def upsert_prs(session, rows: list[dict]) -> None:
    stmt = pg_insert(PullRequest).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["github_id"],
        set_={
            "title": stmt.excluded.title,
            "state": stmt.excluded.state,
            "author_id": stmt.excluded.author_id,
            "base_branch": stmt.excluded.base_branch,
            "head_branch": stmt.excluded.head_branch,
            "head_sha": stmt.excluded.head_sha,
            "merge_commit_sha": stmt.excluded.merge_commit_sha,
            "draft": stmt.excluded.draft,
            "additions": stmt.excluded.additions,
            "deletions": stmt.excluded.deletions,
            "changed_files": stmt.excluded.changed_files,
            "commits_count": stmt.excluded.commits_count,
            "opened_at": stmt.excluded.opened_at,
            "closed_at": stmt.excluded.closed_at,
            "merged_at": stmt.excluded.merged_at,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)


async def upsert_labels(session, rows: list[dict]) -> dict[tuple, int]:
    """Returns {(repository_id, name): db_id}."""
    if not rows:
        return {}
    stmt = pg_insert(Label).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_label_repo_name",
        set_={"color": stmt.excluded.color},
    ).returning(Label.repository_id, Label.name, Label.id)
    result = await session.execute(stmt)
    return {(repo_id, name): db_id for repo_id, name, db_id in result.fetchall()}


async def upsert_reviews(session, rows: list[dict]) -> None:
    stmt = pg_insert(Review).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["github_id"],
        set_={
            "pull_request_id": stmt.excluded.pull_request_id,
            "reviewer_id": stmt.excluded.reviewer_id,
            "state": stmt.excluded.state,
            "submitted_at": stmt.excluded.submitted_at,
        },
    )
    await session.execute(stmt)


async def upsert_pr_commits(session, rows: list[dict]) -> None:
    stmt = pg_insert(PullRequestCommit).values(rows)
    stmt = stmt.on_conflict_do_nothing()
    await session.execute(stmt)


async def upsert_pr_labels(session, rows: list[dict]) -> None:
    stmt = pg_insert(PullRequestLabel).values(rows)
    stmt = stmt.on_conflict_do_nothing()
    await session.execute(stmt)


# ─────────────────────────── sync phases ───────────────────────────


async def enrich_user_profiles(
    gh: GitHubClient,
    session,
    stats: RepoStats | None = None,
) -> int:
    """
    Fetch full GitHub profiles for users that only have basic data (login /
    avatar_url) and are still missing a name.

    The GitHub list APIs embedded in commits / PRs / reviews only return
    { id, login, avatar_url }.  Getting name and email requires a separate
    GET /users/{login} per user.  We do this once per user and cache the
    result in the DB — subsequent syncs find name IS NOT NULL and skip them.

    Returns the number of users successfully enriched.
    """
    result = await session.execute(
        select(User.id, User.login).where(User.name.is_(None))
    )
    to_enrich = result.fetchall()
    if not to_enrich:
        return 0

    if stats:
        stats.phase = f"enriching {len(to_enrich)} user profile(s)"
    sem = asyncio.Semaphore(PROFILE_CONCURRENCY)
    enriched = 0

    async def _fetch(db_id: int, login: str) -> None:
        nonlocal enriched
        async with sem:
            try:
                data = await gh.get(f"/users/{login}")
                # Use "" (not None) when GitHub has no name for this user.
                # The WHERE clause filters on IS NULL, so "" marks the row as
                # "profile fetched, no public name" and prevents re-fetching
                # it on every subsequent sync.
                name = data.get("name") or ""
                email = data.get("email")
                await session.execute(
                    update(User)
                    .where(User.id == db_id)
                    .values(
                        name=name,
                        email=email,
                        avatar_url=data.get("avatar_url") or None,
                    )
                )
                enriched += 1
            except Exception:
                pass  # leave null; will retry on the next sync run

    await asyncio.gather(*[_fetch(db_id, login) for db_id, login in to_enrich])
    await session.commit()
    return enriched


async def fetch_commit_stats(
    gh: GitHubClient,
    owner: str,
    name: str,
    sha: str,
    sem: asyncio.Semaphore,
) -> tuple[str, int, int]:
    """Fetch additions/deletions for a single commit. Returns (sha, additions, deletions)."""
    async with sem:
        data = await gh.get(f"/repos/{owner}/{name}/commits/{sha}")
    s = data.get("stats", {})
    return sha, s.get("additions", 0), s.get("deletions", 0)


async def resolve_unlinked_authors(
    gh: GitHubClient,
    raw: list[dict],
    user_id_map: dict[int, int],
    session,
) -> dict[str, int]:
    """
    Multi-stage fallback to resolve author_id for commits where GitHub didn't
    link the commit to a user account (c["author"] is None).

    Stage 0 — parse GitHub noreply emails (free, no API calls):
      Extracts github_id/login from *@users.noreply.github.com addresses.
      Legacy format requires a /users/{login} lookup to get the numeric ID.

    Stage 1 — free, zero API calls:
      Build an email → GitHub user map from commits that DO have a linked user.
      A developer who changed their git email will often have some linked and
      some unlinked commits — this resolves the majority of gaps instantly.

    Stage 3 — check DB (free, no API calls):
      For emails still unresolved, check the user_emails table and users.email.
      Covers git identities manually linked via the /users/missing UI.

    Returns {git_email: db_user_id}.
    """
    # Stage 0: parse GitHub noreply emails — free, no API calls.
    #   Modern format: 12345678+login@users.noreply.github.com
    #     → github_id + login available directly, no lookup needed.
    #   Legacy format: login@users.noreply.github.com
    #     → need GET /users/{login} to get the numeric ID.
    noreply_email_to_gh_user: dict[str, dict] = {}
    logins_to_fetch: dict[str, str] = {}  # login → email (for legacy format)

    for c in raw:
        for gh_key, meta_key in (("author", "author"), ("committer", "committer")):
            if c.get(gh_key) and c[gh_key].get("id"):
                continue  # already linked by GitHub
            email = c["commit"][meta_key].get("email", "").lower().strip()
            if not email or email in noreply_email_to_gh_user:
                continue
            github_id, login = parse_noreply_email(email)
            if login is None:
                continue  # not a noreply address
            if github_id is not None:
                # Modern format: we have everything we need
                noreply_email_to_gh_user[email] = {"id": github_id, "login": login, "avatar_url": None}
            else:
                # Legacy format: queue a /users/{login} lookup
                logins_to_fetch[login] = email

    # Fetch legacy noreply users by login (concurrently, capped at 5)
    _sem = asyncio.Semaphore(5)

    async def _fetch_by_login(login: str, email: str) -> None:
        async with _sem:
            try:
                user = await gh.get(f"/users/{login}")
                noreply_email_to_gh_user[email] = user
            except Exception:
                pass  # leave unresolved

    if logins_to_fetch:
        await asyncio.gather(*[_fetch_by_login(l, e) for l, e in logins_to_fetch.items()])

    # Stage 1: derive email→gh_user from commits that are already linked
    email_to_gh_user: dict[str, dict] = {**noreply_email_to_gh_user}
    for c in raw:
        gh_user = c.get("author")
        if gh_user and gh_user.get("id"):
            email = c["commit"]["author"].get("email", "").lower().strip()
            if email:
                email_to_gh_user[email] = gh_user
        gh_user = c.get("committer")
        if gh_user and gh_user.get("id"):
            email = c["commit"]["committer"].get("email", "").lower().strip()
            if email:
                email_to_gh_user[email] = gh_user


    # upsert any newly discovered users not already in user_id_map
    new_users = {
        u["id"]: u
        for u in email_to_gh_user.values()
        if u and u.get("id") and u["id"] not in user_id_map
    }
    for batch in chunks(list(new_users.values()), BATCH_SIZE):
        user_id_map.update(await upsert_users(session, batch))
        await session.commit()

    result: dict[str, int] = {
        email: user_id_map[gh_user["id"]]
        for email, gh_user in email_to_gh_user.items()
        if gh_user and gh_user.get("id") in user_id_map
    }

    # Stage 3: check user_emails table + users.email for still-unresolved emails.
    # This covers git identities manually linked via the /users/missing UI without
    # needing a GitHub API call.
    all_emails = {
        c["commit"][meta_key].get("email", "").lower().strip()
        for c in raw
        for meta_key in ("author", "committer")
    } - {""}
    unresolved_stage3 = all_emails - set(result.keys())
    if unresolved_stage3:
        alt_rows = (await session.execute(
            select(UserEmail.email, UserEmail.user_id).where(UserEmail.email.in_(unresolved_stage3))
        )).fetchall()
        for row in alt_rows:
            result[row.email] = row.user_id

        still_unresolved = unresolved_stage3 - set(result.keys())
        if still_unresolved:
            primary_rows = (await session.execute(
                select(User.email, User.id).where(User.email.in_(still_unresolved))
            )).fetchall()
            for row in primary_rows:
                if row.email:
                    result[row.email] = row.id

    return result


async def sync_commits(
    gh: GitHubClient, session, repo_id: int, owner: str, name: str, stats: RepoStats,
    synced_at: datetime | None = None,
    sync_start: datetime | None = None,
    console: Console | None = None,
    emit: "ThrottledEmit | None" = None,
) -> None:
    stats.phase = "fetching commits"
    # `since` tells GitHub to only return commits authored after this timestamp
    extra = {"since": synced_at.isoformat()} if synced_at else {}
    raw = await gh.paginate(f"/repos/{owner}/{name}/commits", **extra)
    # GitHub returns newest-first; reverse so we insert oldest→newest
    raw.reverse()

    if not raw:
        # Nothing new — advance the cutoff so the next run stays incremental
        if sync_start:
            await session.execute(
                update(Repository).where(Repository.id == repo_id)
                .values(commits_synced_at=sync_start)
            )
            await session.commit()
        return

    # Stage A: upsert users directly linked by GitHub
    gh_users: dict[int, dict] = {}
    for c in raw:
        for key in ("author", "committer"):
            u = c.get(key)
            if u and u.get("id"):
                gh_users[u["id"]] = u

    user_id_map: dict[int, int] = {}
    for batch in chunks(list(gh_users.values()), BATCH_SIZE):
        user_id_map.update(await upsert_users(session, batch))
        await session.commit()

    # Stage B: resolve unlinked authors via email fallback + GitHub search
    stats.phase = "resolving authors"
    email_to_db_id = await resolve_unlinked_authors(gh, raw, user_id_map, session)

    # Process commits in batches: fetch stats → save → advance commits_synced_at.
    # Merging stats-fetch and DB-save into one loop means each completed batch is
    # durably checkpointed.  A crash mid-stats-fetch only loses that batch's work;
    # the next run resumes from the authored_at of the last saved batch.
    stats_sem = asyncio.Semaphore(STATS_CONCURRENCY)
    done_count = 0
    total = len(raw)
    stats.phase = f"commit stats (0/{total})"

    for batch in chunks(raw, BATCH_SIZE):
        # 1. Fetch stats concurrently for just this batch
        batch_sha_stats: dict[str, tuple[int, int]] = {}

        async def _fetch_stat(c: dict, _bss: dict = batch_sha_stats) -> None:
            nonlocal done_count
            sha, adds, dels = await fetch_commit_stats(gh, owner, name, c["sha"], stats_sem)
            _bss[sha] = (adds, dels)
            done_count += 1
            stats.phase = f"commit stats ({done_count}/{total})"

        await asyncio.gather(*[_fetch_stat(c) for c in batch])

        # 2. Build and save rows
        rows = []
        for c in batch:
            author_gh = c.get("author")
            committer_gh = c.get("committer")
            commit_meta = c["commit"]
            additions, deletions = batch_sha_stats.get(c["sha"], (0, 0))

            author_email = commit_meta["author"].get("email", "").lower().strip()
            committer_email = commit_meta["committer"].get("email", "").lower().strip()

            rows.append({
                "sha": c["sha"],
                "repository_id": repo_id,
                # Primary: use GitHub-linked user; fallback: email-resolved user
                "author_id": (
                    user_id_map.get(author_gh["id"]) if author_gh and author_gh.get("id")
                    else email_to_db_id.get(author_email)
                ),
                "committer_id": (
                    user_id_map.get(committer_gh["id"]) if committer_gh and committer_gh.get("id")
                    else email_to_db_id.get(committer_email)
                ),
                # Raw git identity — stored unconditionally so there's always
                # something to display even when author_id/committer_id is null.
                "author_name": commit_meta["author"].get("name"),
                "author_email": author_email or None,
                "committer_name": commit_meta["committer"].get("name"),
                "committer_email": committer_email or None,
                "message": commit_meta["message"],
                "additions": additions,
                "deletions": deletions,
                "net_lines": additions - deletions,
                "authored_at": parse_dt(commit_meta["author"]["date"]),
                "committed_at": parse_dt(commit_meta["committer"]["date"]),
            })
        await upsert_commits(session, rows)

        # 3. Advance commits_synced_at to the authored_at of the last commit in
        # this batch (raw is oldest→newest after the earlier reverse()).  Using
        # the item's own timestamp — not wall-clock sync_start — means a crash
        # and restart will use `since=` from exactly where we left off.
        batch_cutoff = parse_dt(batch[-1]["commit"]["author"]["date"])
        await session.execute(
            update(Repository).where(Repository.id == repo_id)
            .values(commits_synced_at=batch_cutoff or sync_start)
        )
        await session.commit()
        stats.commits += len(batch)
        if emit:
            emit.emit()

        await asyncio.sleep(5)


async def sync_prs(
    gh: GitHubClient, session, repo_id: int, owner: str, name: str, stats: RepoStats,
    synced_at: datetime | None = None,
    sync_start: datetime | None = None,
    console: Console | None = None,
    emit: "ThrottledEmit | None" = None,
) -> set[int]:
    """Returns the set of PR numbers that were fetched (new or updated since last sync)."""
    stats.phase = "fetching PRs"
    # Both first-sync and incremental go oldest→newest (sort=updated, asc).
    # Incremental passes `since=` so GitHub filters server-side — no
    # client-side stop_at_dt needed.  This mirrors how sync_commits works and
    # makes per-batch cutoff timestamps semantically correct.
    extra = {"since": synced_at.isoformat()} if synced_at else {}
    raw = await gh.paginate(
        f"/repos/{owner}/{name}/pulls",
        state="all",
        sort="updated",
        direction="asc",
        **extra,
    )

    # collect users and label data from PR payloads
    gh_users: dict[int, dict] = {}
    # key by (name) to deduplicate — same label can appear across many PRs
    labels_by_name: dict[str, dict] = {}
    for pr in raw:
        if pr.get("user") and pr["user"].get("id"):
            gh_users[pr["user"]["id"]] = pr["user"]
        for lbl in pr.get("labels", []):
            labels_by_name[lbl["name"]] = {"repository_id": repo_id, "name": lbl["name"], "color": lbl.get("color")}
    label_rows = list(labels_by_name.values())

    user_id_map: dict[int, int] = {}
    for batch in chunks(list(gh_users.values()), BATCH_SIZE):
        mapping = await upsert_users(session, batch)
        user_id_map.update(mapping)
        await session.commit()

    label_id_map: dict[tuple, int] = {}
    for batch in chunks(label_rows, BATCH_SIZE):
        mapping = await upsert_labels(session, batch)
        label_id_map.update(mapping)
        await session.commit()

    stats.phase = "saving PRs"
    for i, batch in enumerate(chunks(raw, BATCH_SIZE)):
        pr_rows = []
        for pr in batch:
            author_gh = pr.get("user")
            merged = pr.get("merged_at") is not None
            state = PRState.merged if merged else (PRState.open if pr["state"] == "open" else PRState.closed)
            pr_rows.append({
                "github_id": pr["id"],
                "repository_id": repo_id,
                "number": pr["number"],
                "title": pr["title"],
                "state": state,
                "author_id": user_id_map.get(author_gh["id"]) if author_gh and author_gh.get("id") else None,
                "base_branch": pr["base"]["ref"],
                "head_branch": pr["head"]["ref"],
                "head_sha": pr["head"]["sha"],
                "merge_commit_sha": pr.get("merge_commit_sha"),
                "draft": pr.get("draft", False),
                "additions": 0,
                "deletions": 0,
                "changed_files": 0,
                "commits_count": 0,
                "opened_at": parse_dt(pr["created_at"]),
                "closed_at": parse_dt(pr.get("closed_at")),
                "merged_at": parse_dt(pr.get("merged_at")),
            })

        batch_cutoff = parse_dt(batch[-1].get("updated_at"))

        # Skip, if data already processed
        if synced_at and batch_cutoff < synced_at:
            if console:
                console.print(f"[yellow]DEBUG:[/yellow] SKIPPING BATCH # {i}")
            continue
        
        await upsert_prs(session, pr_rows)

        # The list API does not return additions/deletions/changed_files/commits;
        # fetch each PR individually to get those stats.
        done = min((i + 1) * BATCH_SIZE, len(raw))
        stats.phase = f"fetching PR stats ({done}/{len(raw)} PRs)"
        for pr in batch:
            detail = await gh.get(f"/repos/{owner}/{name}/pulls/{pr['number']}")
            await session.execute(
                update(PullRequest)
                .where(PullRequest.github_id == pr["id"])
                .values(
                    additions=detail.get("additions", 0),
                    deletions=detail.get("deletions", 0),
                    changed_files=detail.get("changed_files", 0),
                    commits_count=detail.get("commits", 0),
                )
            )
            await asyncio.sleep(1)

        await session.execute(
            update(Repository).where(Repository.id == repo_id)
            .values(prs_synced_at=batch_cutoff)
        )
        await session.commit()

        # resolve PR db ids then link labels
        gh_ids = [r["github_id"] for r in pr_rows]
        result = await session.execute(
            select(PullRequest.github_id, PullRequest.id).where(PullRequest.github_id.in_(gh_ids))
        )
        pr_id_map = {gh_id: db_id for gh_id, db_id in result.fetchall()}

        # deduplicate pr_label pairs — a PR can't have the same label twice
        # but defensive dedup prevents ON CONFLICT batch errors
        pl_seen: set[tuple] = set()
        pl_rows = []
        for pr in batch:
            db_pr_id = pr_id_map.get(pr["id"])
            if not db_pr_id:
                continue
            for lbl in pr.get("labels", []):
                label_db_id = label_id_map.get((repo_id, lbl["name"]))
                if label_db_id and (db_pr_id, label_db_id) not in pl_seen:
                    pl_seen.add((db_pr_id, label_db_id))
                    pl_rows.append({"pull_request_id": db_pr_id, "label_id": label_db_id})

        if pl_rows:
            await upsert_pr_labels(session, pl_rows)
            await session.commit()

        stats.prs += len(batch)
        if emit:
            emit.emit()

        await asyncio.sleep(10)


    return {pr["number"] for pr in raw}


async def sync_reviews(
    gh: GitHubClient, session, repo_id: int, owner: str, name: str, stats: RepoStats,
    sync_start: datetime | None = None,
    synced_at: datetime | None = None,
    console: Console | None = None,
    emit: "ThrottledEmit | None" = None,
) -> None:
    """Fetch reviews for PRs in this repo."""
    query = select(PullRequest.id, PullRequest.number, PullRequest.opened_at).where(PullRequest.repository_id == repo_id)
    if synced_at:
        # PRs closed/merged before the last review sync cannot have new reviews.
        # Exclude them entirely to avoid unnecessary GitHub API calls.
        # merged PRs always have closed_at set too, so one check covers both.
        query = query.where(
            or_(
                PullRequest.closed_at.is_(None),     # still open
                PullRequest.closed_at >= synced_at,  # closed/merged after last review sync
            )
        )
    query = query.order_by(PullRequest.opened_at.asc())
    result = await session.execute(query)
    all_prs = result.fetchall()  # [(db_id, number)]

    if console:
        console.print(f"[yellow]DEBUG:[/yellow] BATCH SIZE # {len(all_prs)}")

    for i, batch_prs in enumerate(chunks(all_prs, BATCH_SIZE)):
        stats.phase = f"reviews ({min((i + 1) * BATCH_SIZE, len(all_prs))}/{len(all_prs)} PRs)"

        gh_users: dict[int, dict] = {}
        review_items: list[tuple[dict, int]] = []  # (raw_review, pr_db_id)

        for db_pr_id, pr_number, pr_opened_at in batch_prs:
            raw = await gh.paginate(f"/repos/{owner}/{name}/pulls/{pr_number}/reviews")
            for r in raw:
                
                # Skip reviews already captured in a previous sync
                if synced_at:
                    submitted = parse_dt(r.get("submitted_at"))
                    if submitted and submitted < synced_at:
                        continue
                if r.get("user") and r["user"].get("id"):
                    gh_users[r["user"]["id"]] = r["user"]
                review_items.append((r, db_pr_id))

            await asyncio.sleep(1)

        user_id_map: dict[int, int] = {}
        for batch in chunks(list(gh_users.values()), BATCH_SIZE):
            mapping = await upsert_users(session, batch)
            user_id_map.update(mapping)
            await session.commit()

        # build review rows and track earliest review per PR for first_review_at
        first_review_at: dict[int, datetime] = {}
        review_rows = []
        for r, pr_db_id in review_items:
            if not r.get("submitted_at"):
                continue
            try:
                state = ReviewState(r["state"].lower())
            except ValueError:
                continue
            submitted = parse_dt(r["submitted_at"])
            reviewer_gh = r.get("user")
            review_rows.append({
                "github_id": r["id"],
                "pull_request_id": pr_db_id,
                "reviewer_id": user_id_map.get(reviewer_gh["id"]) if reviewer_gh and reviewer_gh.get("id") else None,
                "state": state,
                "submitted_at": submitted,
            })
            if pr_db_id not in first_review_at or submitted < first_review_at[pr_db_id]:
                first_review_at[pr_db_id] = submitted

        for batch in chunks(review_rows, BATCH_SIZE):
            await upsert_reviews(session, batch)
            await session.commit()
            stats.reviews += len(batch)
            if emit:
                emit.emit()

        # update first_review_at on each PR
        for pr_db_id, first_at in first_review_at.items():
            await session.execute(
                update(PullRequest)
                .where(PullRequest.id == pr_db_id)
                .values(first_review_at=first_at)
            )
        await session.commit()

        # Advance reviews_synced_at for every batch.
        await session.execute(
            update(Repository).where(Repository.id == repo_id)
            .values(reviews_synced_at=pr_opened_at)
        )
        await session.commit()

        await asyncio.sleep(10)


async def sync_pr_commits(
    gh: GitHubClient, session, repo_id: int, owner: str, name: str, stats: RepoStats,
    sync_start: datetime | None = None,
    synced_at: datetime | None = None,
    console: Console | None = None,
    emit: "ThrottledEmit | None" = None,
) -> None:
    """Link PRs to their commits."""
    query = select(PullRequest.id, PullRequest.number, PullRequest.opened_at).where(PullRequest.repository_id == repo_id)
    if synced_at:
        # Closed/merged PRs have a final commit list — skip if already synced.
        query = query.where(
            or_(
                PullRequest.closed_at.is_(None),      # still open
                PullRequest.closed_at >= synced_at,   # closed/merged after last sync
            )
        )
    query = query.order_by(PullRequest.opened_at.asc())
    result = await session.execute(query)
    all_prs = result.fetchall()

    for i, batch_prs in enumerate(chunks(all_prs, BATCH_SIZE)):
        stats.phase = f"PR→commit links ({min((i + 1) * BATCH_SIZE, len(all_prs))}/{len(all_prs)} PRs)"
        link_rows = []

        for db_pr_id, pr_number, pr_opened_at in batch_prs:
            raw = await gh.paginate(f"/repos/{owner}/{name}/pulls/{pr_number}/commits")
            shas = [c["sha"] for c in raw]
            if not shas:
                continue
            sha_result = await session.execute(
                select(Commit.sha, Commit.id).where(Commit.sha.in_(shas))
            )
            sha_to_id = dict(sha_result.fetchall())
            for sha in shas:
                if sha in sha_to_id:
                    link_rows.append({"pull_request_id": db_pr_id, "commit_id": sha_to_id[sha]})

            await asyncio.sleep(1)

        if link_rows:
            await upsert_pr_commits(session, link_rows)
        await session.commit()

        # Advance pr_commits_synced_at at every batch.
        await session.execute(
            update(Repository).where(Repository.id == repo_id)
            .values(pr_commits_synced_at=pr_opened_at)
        )
        await session.commit()
        if emit:
            emit.emit()

        await asyncio.sleep(10)


# ─────────────────────────── per-repo orchestration ───────────────────────────


async def sync_repo(
    gh: GitHubClient,
    full_name: str,
    stats: RepoStats,
    process_phases: set[str] | None = None,
    console: Console | None = None,
    emit: "ThrottledEmit | None" = None,
) -> None:
    if process_phases is None:
        process_phases = {"commits", "prs", "reviews", "pr_commits"}
    owner, name = full_name.split("/", 1)
    # Capture start time BEFORE any work so the next incremental sync's cutoff
    # overlaps slightly rather than leaving a gap for items created mid-run.
    sync_start = datetime.now(timezone.utc)
    stats.status = "syncing"
    try:
        gh_repo = await gh.get(f"/repos/{owner}/{name}")
        async with AsyncSessionLocal() as session:
            # Look up the last successful per-phase sync timestamps
            # Skip repositories that have been archived (active=False)
            existing = await session.execute(
                select(
                    Repository.id,
                    Repository.commits_synced_at,
                    Repository.prs_synced_at,
                    Repository.reviews_synced_at,
                    Repository.pr_commits_synced_at,
                ).where(Repository.full_name == full_name, Repository.active == True)  # noqa: E712
            )
            row = existing.first()

            # If no row found (repo is inactive or not in DB yet for an inactive repo), skip sync
            # The query already filters active=True, so a missing row means archived — skip it.
            # (New repos not yet in DB will be upserted below; inactive repos are intentionally absent.)
            # To distinguish: check if the repo exists at all (inactive) vs. truly new.
            if row is None:
                # Check if the repo exists but is inactive
                inactive_check = await session.execute(
                    select(Repository.id).where(
                        Repository.full_name == full_name,
                        Repository.active == False,  # noqa: E712
                    )
                )
                if inactive_check.first() is not None:
                    stats.status = "done"
                    stats.phase = "skipped (archived)"
                    return

            commits_synced_at:    datetime | None = row.commits_synced_at    if row else None
            prs_synced_at:        datetime | None = row.prs_synced_at        if row else None
            reviews_synced_at:    datetime | None = row.reviews_synced_at    if row else None
            pr_commits_synced_at: datetime | None = row.pr_commits_synced_at if row else None

            # Display the earliest completed timestamp as the incremental baseline
            earliest = min(filter(None, [commits_synced_at, prs_synced_at]), default=None)
            if earliest:
                stats.phase = f"incremental (since {earliest.strftime('%Y-%m-%d')})"
            else:
                stats.phase = "full sync"

            repo_id = await upsert_repository(session, owner, name, gh_repo)
            await session.commit()

            # ── commits ───────────────────────────────────────────────────────
            if "commits" in process_phases:
                stats.commits_status = "syncing"
                if emit: emit.force()
                await sync_commits(gh, session, repo_id, owner, name, stats, commits_synced_at,
                                   sync_start=sync_start, console=console, emit=emit)
                stats.commits_status = "done"
                if emit: emit.force()
            else:
                stats.commits_status = "skipped"
                if emit: emit.force()

            # ── pull requests ─────────────────────────────────────────────────
            if "prs" in process_phases:
                stats.prs_status = "syncing"
                if emit: emit.force()
                synced_pr_numbers = await sync_prs(gh, session, repo_id, owner, name, stats,
                                                   prs_synced_at, sync_start=sync_start,
                                                   console=console, emit=emit)
                stats.prs_status = "done"
                if emit: emit.force()
            else:
                stats.prs_status = "skipped"
                if emit: emit.force()
                synced_pr_numbers = set()

            # ── reviews ───────────────────────────────────────────────────────
            if "reviews" in process_phases:
                stats.reviews_status = "syncing"
                if emit: emit.force()
                await sync_reviews(gh, session, repo_id, owner, name, stats,
                                   sync_start=sync_start,
                                   synced_at=reviews_synced_at, console=console, emit=emit)
                stats.reviews_status = "done"
                if emit: emit.force()
            else:
                stats.reviews_status = "skipped"
                if emit: emit.force()

            # ── PR → commit links ─────────────────────────────────────────────
            if "pr_commits" in process_phases:
                stats.pr_commits_status = "syncing"
                if emit: emit.force()
                await sync_pr_commits(gh, session, repo_id, owner, name, stats,
                                      sync_start=sync_start,
                                      synced_at=pr_commits_synced_at, console=console, emit=emit)
                stats.pr_commits_status = "done"
                if emit: emit.force()
            else:
                stats.pr_commits_status = "skipped"
                if emit: emit.force()

            # Enrich user profiles: fetch name / email for any user that was
            # inserted with only the basic list-API fields (id, login, avatar).
            stats.phase = "enriching user profiles"
            if emit: emit.emit()
            stats.users_enriched = await enrich_user_profiles(gh, session, stats)

        stats.status = "done"
        stats.phase = ""
        if emit: emit.force()
    except Exception as exc:
        # Mark the currently-active phase as failed so the badge turns red
        for field in ("commits_status", "prs_status", "reviews_status", "pr_commits_status"):
            if getattr(stats, field) == "syncing":
                setattr(stats, field, "error")
                break
        stats.status = "error"
        stats.error = str(exc)
        if emit: emit.force()
        raise


# ─────────────────────────── main ───────────────────────────


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


async def resolve_repos(gh: GitHubClient, args: list[str]) -> list[str]:
    """
    Expand CLI args into a deduplicated list of 'owner/repo' strings.
    - Args containing '/'  → treated as explicit repos (owner/repo).
    - Args without '/'     → treated as an org/user; all its repos are fetched.
    Also merges repos from GITHUB_REPOS env var.
    """
    console = Console(stderr=True)
    repo_set: list[str] = []
    seen: set[str] = set()

    def add(full_name: str) -> None:
        if full_name not in seen:
            seen.add(full_name)
            repo_set.append(full_name)

    # explicit repos from env
    for r in _split_csv(settings.github_repos):
        add(r)

    orgs: list[str] = []
    for arg in args:
        if "/" in arg:
            add(arg)
        else:
            orgs.append(arg)

    # also fold in GITHUB_ORGS from env (only when no CLI args given)
    if not args:
        orgs = _split_csv(settings.github_orgs)

    for org in orgs:
        with console.status(f"[cyan]Discovering repos for [bold]{org}[/bold]…"):
            try:
                repos = await gh.fetch_org_repos(org)
            except httpx.HTTPStatusError as exc:
                console.print(f"[red]✗ Could not fetch repos for '{org}': HTTP {exc.response.status_code}[/red]")
                continue

        console.print(
            f"[green]✓[/green] [bold]{org}[/bold] — found [bold]{len(repos)}[/bold] active repos"
        )
        for r in repos:
            add(r["full_name"])

    return repo_set


async def main(args: list[str], process_phases: set[str] | None = None) -> None:
    if process_phases is None:
        process_phases = {"commits", "prs", "reviews", "pr_commits"}
    if not settings.github_token:
        print("Error: GITHUB_TOKEN is not set in .env")
        sys.exit(1)

    console = Console()
    gh = GitHubClient(settings.github_token)

    try:
        repos = await resolve_repos(gh, args)
    except Exception as exc:
        console.print(f"[red]Failed during repo discovery: {exc}[/red]")
        await gh.close()
        sys.exit(1)

    if not repos:
        console.print("[red]No repositories found. Check your org names and GITHUB_TOKEN permissions.[/red]")
        await gh.close()
        sys.exit(1)

    console.print(f"\n[bold]Syncing {len(repos)} repositor{'y' if len(repos) == 1 else 'ies'}…[/bold]\n")

    stats_list = [RepoStats(full_name=r) for r in repos]

    overall = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        transient=False,
    )
    overall_task = overall.add_task("[cyan]Repos", total=len(repos))

    try:
        with Live(_LiveDisplay(stats_list, overall), refresh_per_second=4) as live:
            for stats in stats_list:
                try:
                    await sync_repo(gh, stats.full_name, stats, process_phases=process_phases, console=live.console)
                except Exception:
                    # print full traceback below the live display so nothing is lost
                    live.console.print_exception()
                finally:
                    overall.advance(overall_task)
    finally:
        await gh.close()

    # final summary
    done = sum(1 for s in stats_list if s.status == "done")
    failed = sum(1 for s in stats_list if s.status == "error")
    total_commits = sum(s.commits for s in stats_list)
    total_prs = sum(s.prs for s in stats_list)
    total_reviews = sum(s.reviews for s in stats_list)

    console.print()
    console.print(f"[bold]Sync complete:[/bold] {done} succeeded, {failed} failed")
    console.print(f"Total synced: {total_commits:,} commits · {total_prs:,} PRs · {total_reviews:,} reviews")


async def main_json(args: list[str], process_phases: set[str], github_token: str) -> None:
    """JSON-mode entry point: emits NDJSON lines to stdout, one per phase transition."""
    gh = GitHubClient(github_token)
    try:
        try:
            repos = await resolve_repos(gh, args)
        except Exception as exc:
            sys.stdout.write(json.dumps({"type": "error", "message": str(exc)}) + "\n")
            sys.stdout.flush()
            return

        if not repos:
            sys.stdout.write(json.dumps({"type": "error", "message": "No repositories found"}) + "\n")
            sys.stdout.flush()
            return

        total_commits = total_prs = total_reviews = done = failed = 0
        for full_name in repos:
            stats = RepoStats(full_name=full_name, status="syncing")
            te = ThrottledEmit(stats)
            te.force()  # initial "syncing" line so the UI shows the repo immediately
            try:
                await sync_repo(gh, full_name, stats, process_phases=process_phases, emit=te)
            except Exception:
                pass  # status/error already set inside sync_repo
            te.force()  # final state line
            if stats.status == "done":
                done += 1
            else:
                failed += 1
            total_commits += stats.commits
            total_prs += stats.prs
            total_reviews += stats.reviews

        sys.stdout.write(json.dumps({
            "type": "summary",
            "done": done,
            "failed": failed,
            "total_commits": total_commits,
            "total_prs": total_prs,
            "total_reviews": total_reviews,
        }) + "\n")
        sys.stdout.flush()
    finally:
        await gh.close()


if __name__ == "__main__":
    _VALID_PHASES = {"commits", "prs", "reviews", "pr_commits"}

    # Strip --json flag before parsing the rest of the args
    _json_mode = "--json" in sys.argv[1:]
    _all_args = [a for a in sys.argv[1:] if a != "--json"]

    _process_phases: set[str] = set(_VALID_PHASES)  # default = all
    cli_args: list[str] = []
    _i = 0
    while _i < len(_all_args):
        if _all_args[_i] == "--process" and _i + 1 < len(_all_args):
            _raw = {p.strip() for p in _all_args[_i + 1].split(",")}
            if "all" in _raw:
                _process_phases = set(_VALID_PHASES)
            else:
                _invalid = _raw - _VALID_PHASES
                if _invalid:
                    print(f"Error: unknown phase(s): {', '.join(sorted(_invalid))}")
                    print(f"Valid values: all, {', '.join(sorted(_VALID_PHASES))}")
                    sys.exit(1)
                _process_phases = _raw
            _i += 2
        else:
            cli_args.append(_all_args[_i])
            _i += 1

    # If no repo/org args, fall back entirely to env vars (orgs + repos)
    if not cli_args and not settings.github_orgs and not settings.github_repos:
        print("Usage:  python -m scripts.sync_github myorg")
        print("        python -m scripts.sync_github myorg owner/specific-repo")
        print("        python -m scripts.sync_github myorg --process commits")
        print("        python -m scripts.sync_github myorg --process commits,prs")
        print("        python -m scripts.sync_github myorg --json   (NDJSON output for UI)")
        print("        # or set GITHUB_ORGS=myorg,anotherorg in .env")
        sys.exit(1)

    if _json_mode:
        _token = settings.github_token or ""
        asyncio.run(main_json(cli_args, _process_phases, _token))
    else:
        asyncio.run(main(cli_args, _process_phases))
