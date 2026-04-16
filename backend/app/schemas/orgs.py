from datetime import datetime

from pydantic import BaseModel


def _mask_token(token: str) -> str:
    """Return a partially-masked token preview — raw token is never sent to the client."""
    if len(token) <= 12:
        return "•" * len(token)
    return token[:8] + "…" + token[-4:]


class OrgCreateRequest(BaseModel):
    login: str
    github_token: str


class OrgUpdateRequest(BaseModel):
    display_name: str | None = None
    github_token: str | None = None  # None = leave unchanged


class OrgSummary(BaseModel):
    id: int
    login: str
    display_name: str | None
    avatar_url: str | None
    token_preview: str
    repo_count: int
    created_at: datetime


class OrgsListResponse(BaseModel):
    orgs: list[OrgSummary]
