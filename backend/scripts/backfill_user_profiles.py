#!/usr/bin/env python3
"""
Backfill name and email for users that were inserted with only basic GitHub
data (id, login, avatar_url) from list-API responses.

Calls GET /users/{login} for each user whose `name` is NULL — which means
their full profile has never been fetched.  Users with a genuinely blank
GitHub name are stored with name="" so they are skipped on future runs.

Usage:
    docker compose run --rm api python -m scripts.backfill_user_profiles
"""

import asyncio
import sys

from rich.console import Console
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import User
from scripts.sync_github import GitHubClient, enrich_user_profiles

console = Console()


async def main() -> None:
    if not settings.github_token:
        console.print("[red]Error: GITHUB_TOKEN is not set in .env[/red]")
        sys.exit(1)

    gh = GitHubClient(settings.github_token)
    try:
        async with AsyncSessionLocal() as session:
            total_null = (
                await session.execute(
                    select(func.count()).select_from(User).where(User.name.is_(None))
                )
            ).scalar_one()

        if total_null == 0:
            console.print("[green]✓ All user profiles are already enriched — nothing to do.[/green]")
            return

        console.print(
            f"\nFound [bold cyan]{total_null:,}[/bold cyan] user(s) with null name.\n"
            f"Fetching full profiles from GitHub (up to 20 concurrent)…\n"
        )

        async with AsyncSessionLocal() as session:
            enriched = await enrich_user_profiles(gh, session)

        console.print(
            f"\n[bold]Done.[/bold] Enriched [bold cyan]{enriched:,}[/bold cyan] user profile(s).\n"
            f"Remaining nulls (users whose profiles genuinely have no name) can be checked with:\n"
            f"  [dim]SELECT login, email FROM users WHERE name IS NULL;[/dim]"
        )
    finally:
        await gh.close()


if __name__ == "__main__":
    asyncio.run(main())
