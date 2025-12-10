from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Configuration.
    Reads from environment variables or .env file.
    """

    # --- API KEYS ---
    # Optional because the app can run in "Mock Mode"
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # --- APPLICATION ---
    APP_TITLE: str = "Aegis Feedback Engine"
    DATABASE_URL: str = "sqlite:///feedback.db"

    # The "Race Condition" Timeout.
    # If AI takes longer than this, we switch to Fallback.
    AI_TIMEOUT_SECONDS: float = 0.4

    DISCORD_WEBHOOK_URL: Optional[str] = None

    # --- AI MODELS ---
    AI_MODEL_GROQ: str = "llama-3.1-8b-instant"
    AI_MODEL_OPENAI: str = "gpt-4o-mini"

    # --- FEATURE FLAGS ---
    ENABLE_MOCK_MODE: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    @model_validator(mode="after")
    def check_api_keys(self):
        """Warn or Fail if keys are missing in production mode."""
        if not self.ENABLE_MOCK_MODE:
            if not self.GROQ_API_KEY and not self.OPENAI_API_KEY:
                print("WARNING: No API Keys found. App will default to VADER/Mock.")
        return self


settings = Settings()
