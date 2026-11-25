from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DIVEPOINT_", env_file=".env", extra="ignore")
    database_url: str = "postgresql://divepoint:divepoint@localhost:5432/divepoint"
    user_agent: str = "Divepoint/0.1 (local development; biodiversity exploration)"
    upstream_timeout_seconds: float = 5
    upstream_interval_seconds: float = 1
    cache_ttl_seconds: int = 30 * 24 * 60 * 60
    earliest_record_year: int = 1970
    guide_api_key: SecretStr | None = None
    guide_model: str = "claude-haiku-5-5"
