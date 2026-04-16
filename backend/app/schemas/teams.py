from datetime import date, datetime

from pydantic import BaseModel


class TeamSummary(BaseModel):
    id: int
    name: str
    created_at: datetime
    # 6-month activity stats (populated by list_teams)
    member_count: int = 0
    commits: int = 0
    net_lines: int = 0
    prs_opened: int = 0
    reviews: int = 0

    model_config = {"from_attributes": True}


class TeamsListResponse(BaseModel):
    teams: list[TeamSummary]
    total: int


class CreateTeamRequest(BaseModel):
    name: str


class UserStatRow(BaseModel):
    id: int
    login: str
    name: str | None
    full_name: str | None = None
    avatar_url: str | None
    commits: int
    additions: int
    deletions: int
    prs_opened: int
    prs_merged: int
    reviews: int


class WeeklyUserStat(BaseModel):
    week_start: date
    user_id: int
    commits: int
    net_lines: int


class TeamDetailResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    start_date: date
    end_date: date
    members: list[UserStatRow]
    totals: UserStatRow
    weekly: list[WeeklyUserStat]
