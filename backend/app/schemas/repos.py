from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.teams import UserStatRow, WeeklyUserStat  # noqa: F401 — reused, not redefined


class RepoSummary(BaseModel):
    id: int
    owner: str
    name: str
    full_name: str
    default_branch: str
    # 6-month activity stats (populated by list_repos)
    commits: int = 0
    net_lines: int = 0
    prs_opened: int = 0
    reviews: int = 0
    contributors: int = 0
    commits_synced_at: datetime | None = None
    prs_synced_at: datetime | None = None
    reviews_synced_at: datetime | None = None
    pr_commits_synced_at: datetime | None = None
    model_config = {"from_attributes": True}


class RepoListResponse(BaseModel):
    repos: list[RepoSummary]
    total: int


class RepoDetailResponse(BaseModel):
    id: int
    owner: str
    name: str
    full_name: str
    default_branch: str
    start_date: date
    end_date: date
    contributors: list[UserStatRow]
    totals: UserStatRow
    weekly: list[WeeklyUserStat]
