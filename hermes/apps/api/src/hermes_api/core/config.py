from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Hermes Cryptocurrency AI Trader API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    postgres_user: str = "hermes"
    postgres_password: str = "hermes"
    postgres_db: str = "hermes"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str = "postgresql+psycopg://hermes:hermes@localhost:5432/hermes"

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    lm_studio_base_url: str = "http://localhost:1234"

    telegram_bot_token: str = ""
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    webhook_base_url: str = "http://localhost:8000"

    # Operator auth defaults to fail-closed. Protected routes require either a
    # Bearer token via HERMES_API_KEY or an explicit local-only bypass.
    hermes_api_key: str = ""
    hermes_api_dev_bypass_auth: bool = False

    # Trading mode: "paper" (default) blocks live execution at the API layer.
    # Set to "live" only when exchange credentials and risk controls are verified.
    hermes_trading_mode: str = "paper"
    hermes_enable_live_trading: bool = False
    hermes_live_trading_ack: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
