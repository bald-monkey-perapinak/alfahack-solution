"""Public response contracts, exported into OpenAPI for frontend integration."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .models import Role


class UserView(BaseModel):
    id: int
    name: str
    email: str
    role: Role
    org_id: int


class SessionView(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_at: datetime
    user: UserView | None = None


class OrganizationView(BaseModel):
    id: int
    name: str
    synthetic_u: str | None
    industry: str | None
    region: str | None


class OrganizationPage(BaseModel):
    items: list[OrganizationView]
    total: int
    limit: int
    offset: int


class MaterialOutcome(BaseModel):
    material_id: int
    status: Literal["pending", "running", "completed", "skipped", "failed"]
    error_code: str | None = None
    retries: int = 0


class JobSummary(BaseModel):
    total: int | None = None
    processed: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0
    retrying: bool = False
    materials: list[MaterialOutcome] = Field(default_factory=list)


class JobView(BaseModel):
    id: UUID
    status: Literal["pending", "running", "completed", "failed"]
    parameters: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None
    error_code: str | None
    summary: JobSummary
    insight_ids: list[int] = Field(default_factory=list)


class FeedItem(BaseModel):
    id: int
    title: str
    relevance_score: float
    confidence: float
    created_at: datetime
    primary_material_id: int
    generation_mode: Literal["offline", "live"]
    is_demo: bool
    warnings: list[str]


class FeedPage(BaseModel):
    items: list[FeedItem]
    total: int
    limit: int
    offset: int


class EvidenceView(BaseModel):
    id: int
    insight_id: int
    material_id: int
    section: str
    claim: str
    quote: str
    locator: str | None
    source_title: str
    source_ref: str
    published_at: datetime | None


class InsightView(BaseModel):
    id: int
    run_id: int
    primary_material_id: int
    title: str
    facts: str
    bank_view: str | None
    interpretation: str
    relevance_reason: str
    risks: list[str]
    opportunities: list[str]
    suggested_actions: list[dict[str, Any]]
    relevance_score: float
    confidence: float
    payload: dict[str, Any]
    created_at: datetime
    steps: list[dict[str, Any]]
    company_context: dict[str, Any]
    target_role: Role
    model_name: str
    evidence: list[EvidenceView]


class MaterialView(BaseModel):
    id: int
    title: str
    summary: str | None
    published_at: datetime | None
    material_type: Literal["news", "bank_analytics"]
    source_ref: str
    is_demo: bool


class MaterialPage(BaseModel):
    items: list[MaterialView]
    total: int
    limit: int
    offset: int
