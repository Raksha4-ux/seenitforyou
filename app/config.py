"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for Gmail, WhatsApp Web (Selenium), and polling."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gmail_credentials_path: Path = Field(
        default=Path("credentials.json"),
        description="Path to Google OAuth client credentials JSON",
    )
    gmail_token_path: Path = Field(
        default=Path("token.json"),
        description="Path where Gmail OAuth token is stored",
    )
    gmail_scopes: str = Field(
        default="https://www.googleapis.com/auth/gmail.readonly",
        description="Comma-separated Gmail API scopes",
    )

    whatsapp_chat_name: str = Field(
        ...,
        description="Exact WhatsApp contact or chat name to send alerts to",
    )
    chrome_user_data_dir: Path = Field(
        default=Path("data/chrome_whatsapp_profile"),
        description="Persistent Chrome profile for WhatsApp Web login session",
    )
    whatsapp_web_url: str = Field(default="https://web.whatsapp.com")
    whatsapp_login_timeout_seconds: int = Field(default=180, ge=30, le=600)
    selenium_implicit_wait_seconds: int = Field(default=10, ge=1, le=60)
    chrome_headless: bool = Field(
        default=False,
        description="Headless mode is not recommended; WhatsApp may block it",
    )

    poll_interval_seconds: int = Field(default=30, ge=5, le=3600)
    state_file_path: Path = Field(default=Path("data/processed_ids.json"))
    whatsapp_max_chunk_chars: int = Field(
        default=4000,
        ge=500,
        le=65000,
        description="Max characters per WhatsApp message before splitting",
    )

    @property
    def gmail_scope_list(self) -> list[str]:
        return [s.strip() for s in self.gmail_scopes.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
