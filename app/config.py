from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration via Environment Variables.
    """

    # API Keys
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # App Config
    APP_TITLE: str = "Aegis Feedback Engine"
    DATABASE_URL: str = "sqlite:///feedback.db"
    AI_TIMEOUT_SECONDS: float = 0.5  # 500ms constraint

    # Flags
    ENABLE_MOCK_MODE: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )


settings = Settings()
