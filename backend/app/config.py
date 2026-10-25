from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: SecretStr = SecretStr(
        "postgresql://alfahack:local-development-only@localhost:5432/alfahack"
    )
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    ingest_api_key: SecretStr = SecretStr("")
    data_mode: Literal["demo", "organizers"] = "demo"
    organizer_data_dir: str = str(ROOT / "ml/data")
    llm_mode: str = "offline"
    llm_allow_external: bool = False
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_allowed_models: list[str] = []
    llm_reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    llm_max_tokens: int = Field(default=3000, ge=128, le=16000)
    llm_timeout_seconds: float = Field(default=180, ge=5, le=180)
    session_hours: int = Field(default=24, ge=1, le=168)
    worker_poll_seconds: float = 1
    job_lease_seconds: int = 180


@lru_cache
def get_settings():
    return Settings()
