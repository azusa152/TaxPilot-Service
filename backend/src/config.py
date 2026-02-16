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

    # MOF Tax Reform Monitor (Layer 2)
    mof_crawl_interval_hours: int = 168  # Weekly (reform docs are annual)
    mof_reform_url: str = "https://www.mof.go.jp/tax_policy/tax_reform/outline/index.html"

    # e-Gov Law API (Layer 3)
    egov_api_base_url: str = "https://laws.e-gov.go.jp/api/2"
    egov_crawl_interval_hours: int = 720  # Monthly (laws change infrequently)
    egov_income_tax_law_id: str = "340AC0000000033"  # 所得税法
    egov_local_tax_law_id: str = "325AC0000000226"  # 地方税法

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
