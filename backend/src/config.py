from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://taxpilot:taxpilot_dev@db:5432/taxpilot"
    log_level: str = "INFO"

    # LLM Gateway (Phase 6A)
    llm_provider: str = "openai"
    llm_model: str = "openai/gpt-4o"
    llm_api_token: str = ""
    llm_encryption_key: str = ""
    llm_monthly_budget_usd: float = 50.00

    # NTA Crawler (Phase 6B)
    nta_crawl_interval_hours: int = 24
    nta_crawl_rate_limit_seconds: float = 2.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
