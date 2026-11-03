from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BOT_TOKEN: SecretStr
    GEMINI_API_KEY: SecretStr
    ADMIN_ID: int
    DB_PATH: str = "data/bot.db"
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_FALLBACK_MODELS: list[str] = ["gemini-3.6-flash", "gemini-flash-lite-latest"]
    GEMINI_TIMEOUT_SECONDS: float = 180.0
    GEMINI_RPM: int = 15
    GEMINI_CONCURRENCY: int = 3


settings = Settings()
