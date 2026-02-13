"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """TaxPilot application settings.

    Attributes:
        postgres_user: PostgreSQL username.
        postgres_password: PostgreSQL password.
        postgres_db: PostgreSQL database name.
        postgres_host: PostgreSQL host address.
        postgres_port: PostgreSQL port number.
        database_url: Full async database connection URL.
    """

    postgres_user: str = "taxpilot"
    postgres_password: str = "taxpilot_dev"
    postgres_db: str = "taxpilot"
    postgres_host: str = "db"
    postgres_port: int = 5432
    database_url: str = "postgresql+asyncpg://taxpilot:taxpilot_dev@db:5432/taxpilot"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
