#!/usr/bin/env python3
"""
Backfill author_id and committer_id for commits where these are NULL.

For each unresolved commit it:
  1. Fetches the full commit from GitHub (includes GitHub user + git metadata)
  2. Resolves the user via GitHub-linked account (most reliable)
  3. Falls back to email cross-reference from other commits in the same batch
  4. Falls back to GitHub user search by email (rate-limited, cached across repos)

Usage:
    docker compose run --rm api python -m scripts.backfill_authors
"""

import asyncio
import sys

import httpx
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from sqlalchemy import select, update

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Commit, Repository
from scripts.sync_github import (
    BATCH_SIZE,
    GitHubClient,
    chunks,
    enrich_user_profiles,
    resolve_unlinked_authors,
    upsert_users,
)

console = Console()
FETCH_CONCURRENCY = 10  # parallel individual commit fetches


async def fetch_full_commit(
    gh: GitHubClient,
    owner: str,
    name: str,
    sha: str,
    sem: asyncio.Semaphore,
) -> dict | None:
    """Fetch a single commit from GitHub. Returns None if 404 (force-pushed away)."""
    async with sem:
        try:
            return await gh.get(f"/repos/{owner}/{name}/commits/{sha}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise


async def backfill_repo(
    gh: GitHubClient,
    repo_id: int,
    owner: str,
    name: str,
    session,
    search_sem: asyncio.Semaphore,
    search_cache: dict[str, dict | None],
    progress: Progress,
    task_id,
) -> int:
    """Backfill null author_id / committer_id for one repo. Returns count updated."""

    # 1. Find all commits in this repo with a null author or committer
    result = await session.execute(
        select(Commit.id, Commit.sha)
        .where(Commit.repository_id == repo_id)
        .where((Commit.author_id.is_(None)) | (Commit.committer_id.is_(None)))
        .order_by(Commit.authored_at)
    )
    null_commits = result.fetchall()  # [(db_id, sha)]

    if not null_commits:
        return 0

    progress.update(task_id, total=len(null_commits))

    # 2. Fetch each commit from GitHub concurrently to get the GitHub user objects
    fetch_sem = asyncio.Semaphore(FETCH_CONCURRENCY)
    raw_map: dict[str, dict] = {}  # sha → full github commit payload

    async def _fetch(sha: str) -> None:
        data = await fetch_full_commit(gh, owner, name, sha, fetch_sem)
        if data:
            raw_map[sha] = data

    await asyncio.gather(*[_fetch(sha) for _, sha in null_commits])

    if not raw_map:
        return 0

    raw_list = list(raw_map.values())

    # 3. Upsert users that GitHub directly linked to these commits
    gh_users: dict[int, dict] = {}
    for c in raw_list:
        for key in ("author", "committer"):
            u = c.get(key)
            if u and u.get("id"):
                gh_users[u["id"]] = u

    user_id_map: dict[int, int] = {}
    for batch in chunks(list(gh_users.values()), BATCH_SIZE):
        user_id_map.update(await upsert_users(session, batch))
        await session.commit()

    # 4. Two-stage email fallback for commits still unlinked
    email_to_db_id = await resolve_unlinked_authors(
        gh, raw_list, user_id_map, session, search_sem, search_cache
    )

    # 5. Update commit rows where we now have a resolved id
    updated = 0
    for batch in chunks(null_commits, BATCH_SIZE):
        for db_id, sha in batch:
            c = raw_map.get(sha)
            if not c:
                progress.advance(task_id)
                continue

            author_gh = c.get("author")
            committer_gh = c.get("committer")
            commit_meta = c["commit"]

            author_email = commit_meta["author"].get("email", "").lower().strip()
            committer_email = commit_meta["committer"].get("email", "").lower().strip()

            new_author_id = (
                user_id_map.get(author_gh["id"]) if author_gh and author_gh.get("id")
                else email_to_db_id.get(author_email)
            )
            new_committer_id = (
                user_id_map.get(committer_gh["id"]) if committer_gh and committer_gh.get("id")
                else email_to_db_id.get(committer_email)
            )

            values: dict = {}
            if new_author_id is not None:
                values["author_id"] = new_author_id
            if new_committer_id is not None:
                values["committer_id"] = new_committer_id

            # Always backfill raw git identity fields — they may be missing
            # on commits inserted before this column was added.
            author_name = commit_meta["author"].get("name")
            committer_name = commit_meta["committer"].get("name")
            if author_name:
                values["author_name"] = author_name
            if author_email:
                values["author_email"] = author_email
            if committer_name:
                values["committer_name"] = committer_name
            if committer_email:
                values["committer_email"] = committer_email

            if values:
                await session.execute(
                    update(Commit).where(Commit.id == db_id).values(**values)
                )
                updated += 1

        await session.commit()
        progress.advance(task_id, len(batch))

    return updated


async def main() -> None:
    if not settings.github_token:
        console.print("[red]Error: GITHUB_TOKEN is not set in .env[/red]")
        sys.exit(1)

    gh = GitHubClient(settings.github_token)
    search_sem = asyncio.Semaphore(5)
    search_cache: dict[str, dict | None] = {}

    try:
        # Find repos that have at least one commit with null author/committer
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Repository.id, Repository.name, Repository.full_name)
                .where(
                    Repository.id.in_(
                        select(Commit.repository_id)
                        .where((Commit.author_id.is_(None)) | (Commit.committer_id.is_(None)))
                        .distinct()
                    )
                )
                .order_by(Repository.full_name)
            )
            repos = result.fetchall()

        if not repos:
            console.print("[green]✓ No commits with null author_id or committer_id — nothing to do.[/green]")
            return

        # Print a summary before starting
        async with AsyncSessionLocal() as session:
            count_result = await session.execute(
                select(Commit.repository_id, Commit.id)
                .where((Commit.author_id.is_(None)) | (Commit.committer_id.is_(None)))
            )
            total_null = len(count_result.fetchall())

        console.print(
            f"\nFound [bold cyan]{total_null:,}[/bold cyan] commit(s) with null author/committer "
            f"across [bold]{len(repos)}[/bold] repo(s)\n"
        )

        total_updated = 0

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description:<45}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("commits"),
            TimeElapsedColumn(),
            console=console,
        )

        with progress:
            for repo_id, name, full_name in repos:
                owner = full_name.split("/")[0]
                task_id = progress.add_task(full_name, total=None)
                async with AsyncSessionLocal() as session:
                    try:
                        updated = await backfill_repo(
                            gh, repo_id, owner, name, session,
                            search_sem, search_cache, progress, task_id,
                        )
                        total_updated += updated
                        progress.update(
                            task_id,
                            description=f"[green]✓[/green] {full_name} ({updated} updated)",
                        )
                    except Exception:
                        progress.update(task_id, description=f"[red]✗[/red] {full_name}")
                        console.print_exception()

        console.print(
            f"\n[bold]Done.[/bold] Resolved [bold cyan]{total_updated:,}[/bold cyan] commit(s). "
            f"Remaining nulls (truly unresolvable) can be checked with:\n"
            f"  [dim]SELECT COUNT(*) FROM commits WHERE author_id IS NULL OR committer_id IS NULL;[/dim]"
        )

        # Also backfill name / email for users that only have basic profile data
        console.print("\n[cyan]Enriching user profiles (name / email)…[/cyan]")
        async with AsyncSessionLocal() as session:
            enriched = await enrich_user_profiles(gh, session)
        console.print(f"[green]✓[/green] Enriched [bold cyan]{enriched:,}[/bold cyan] user profile(s).")

    finally:
        await gh.close()


if __name__ == "__main__":
    asyncio.run(main())
