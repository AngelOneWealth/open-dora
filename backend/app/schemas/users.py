from datetime import date, datetime

from pydantic import BaseModel, field_validator


class UserSummary(BaseModel):
    id: int
    github_id: int
    login: str
    name: str | None
    full_name: str | None = None
    email: str | None
    avatar_url: str | None
    active: bool
    team_id: int | None = None
    team_name: str | None = None
    # 6-month activity stats (only populated on the active-users list)
    commits: int = 0
    net_lines: int = 0
    prs_opened: int = 0
    reviews: int = 0

    model_config = {"from_attributes": True}

    @field_validator("name", mode="before")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        """Convert the sentinel empty-string (stored when GitHub profile has no name) back to None."""
        return v or None


class UsersListResponse(BaseModel):
    users: list[UserSummary]
    total: int


class UpdateUserRequest(BaseModel):
    active: bool | None = None
    team_id: int | None = None   # send -1 to unassign from current team
    full_name: str | None = None  # send "" to clear the display name


class MergeUsersRequest(BaseModel):
    source_id: int  # the duplicate to absorb and deactivate


# ── user detail / weekly activity ────────────────────────────────────────────


class WeekActivity(BaseModel):
    """Activity counts for a single ISO week (Monday → Sunday)."""

    week_start: date  # always a Monday
    commits: int
    additions: int
    deletions: int
    prs_opened: int
    prs_merged: int
    reviews: int


class ActivityTotals(BaseModel):
    """Aggregate of all weeks in the requested range."""

    commits: int
    additions: int
    deletions: int
    prs_opened: int
    prs_merged: int
    reviews: int


class LinkMissingAuthorRequest(BaseModel):
    author_name:  str | None
    author_email: str | None
    user_id: int


class LinkMissingAuthorResponse(BaseModel):
    updated_count: int


class MissingAuthor(BaseModel):
    author_name: str | None
    author_email: str | None
    commit_count: int


class MissingAuthorsResponse(BaseModel):
    authors: list[MissingAuthor]
    total: int


class RepoStatRow(BaseModel):
    """Per-repo aggregated stats for a user."""
    repo_id: int
    repo_name: str
    commits: int
    additions: int
    deletions: int
    prs_opened: int
    prs_merged: int
    reviews: int


class WeeklyRepoStat(BaseModel):
    """Weekly commit stats for a single repo, for the line chart."""
    week_start: date
    repo_id: int
    commits: int
    net_lines: int


class UserDetailResponse(BaseModel):
    id: int
    github_id: int
    login: str
    name: str | None
    full_name: str | None = None
    email: str | None
    avatar_url: str | None
    start_date: date
    end_date: date
    weeks: list[WeekActivity]
    totals: ActivityTotals
    repos: list[RepoStatRow]
    weekly_by_repo: list[WeeklyRepoStat]

    @field_validator("name", mode="before")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return v or None


# ── per-user PR / review list ─────────────────────────────────────────────────


class ReviewerInfo(BaseModel):
    id: int
    login: str
    name: str | None
    full_name: str | None = None
    avatar_url: str | None
    state: str   # "approved" | "changes_requested" | "commented" | "dismissed"


class UserPRItem(BaseModel):
    id: int
    number: int
    title: str
    state: str                        # "open" | "closed" | "merged"
    repo_full_name: str               # "owner/repo"
    github_url: str                   # full GitHub URL
    opened_at: datetime
    merged_at: datetime | None
    closed_at: datetime | None
    additions: int
    deletions: int
    changed_files: int
    commits_count: int
    reviewers: list[ReviewerInfo] = []


class UserPRsResponse(BaseModel):
    prs: list[UserPRItem]
    total: int


class UserReviewItem(BaseModel):
    id: int
    state: str                        # "approved" | "changes_requested" | etc.
    submitted_at: datetime
    pr_number: int
    pr_title: str
    pr_state: str
    repo_full_name: str
    github_url: str                   # link to the PR on GitHub
    pr_author_login: str | None = None
    pr_author_name: str | None = None
    pr_author_avatar_url: str | None = None


class UserReviewsResponse(BaseModel):
    reviews: list[UserReviewItem]
    total: int
