from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Role(StrEnum):
    cfo = "cfo"
    ceo = "ceo"
    treasurer = "treasurer"
    chief_accountant = "chief_accountant"
    owner = "owner"


class Register(Input):
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: SecretStr = Field(min_length=10, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    role: Role
    organization_id: int = Field(gt=0)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return value.lower()


class Login(Input):
    email: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)


class UserUpdate(Input):
    organization_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: Role | None = None


Factor = Literal[
    "key_rate",
    "inflation",
    "consumption",
    "gdp",
    "labor_market",
    "bonds",
    "gold",
    "commodities",
    "currency",
    "sanctions",
    "logistics",
    "real_estate",
    "lending",
]


class Shock(Input):
    factor: Factor
    direction: float = Field(ge=-1, le=1)
    magnitude: float = Field(ge=0, le=1)
    horizon: Literal["immediate", "week", "month", "quarter", "year"] = "quarter"
    source: str = "operator"


class Article(Input):
    title: str = Field(min_length=3, max_length=1000)
    body: str = Field(min_length=20, max_length=100000)
    source_name: str = Field(min_length=1, max_length=255)
    source_url: HttpUrl
    published_at: datetime
    shocks: list[Shock] | None = Field(default=None, max_length=13)

    @field_validator("published_at")
    @classmethod
    def aware(cls, v):
        if v.tzinfo is None:
            raise ValueError("Нужна дата с часовым поясом, например +03:00")
        return v


class Ingest(Input):
    articles: Annotated[list[Article], Field(min_length=1, max_length=50)]


class AnalysisRequest(Input):
    material_ids: list[int] | None = Field(default=None, min_length=1, max_length=10)
    max_events: int = Field(default=5, ge=1, le=10)
    max_depth: int = Field(default=3, ge=1, le=4)
    decay: float = Field(default=0.5, gt=0, le=1)
    min_score: float = Field(default=0.05, ge=0, le=1)


class Question(Input):
    question: str = Field(min_length=3, max_length=2000)


class Feedback(Input):
    rating: Literal["useful", "not_useful", "already_known"]
    comment: str | None = Field(default=None, max_length=2000)
