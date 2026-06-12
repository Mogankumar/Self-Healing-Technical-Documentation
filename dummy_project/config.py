"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """
    Holds database connection settings.

    Reads from environment variables with sensible defaults
    for local development.
    """
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    name: str = os.getenv("DB_NAME", "userdb")
    user: str = os.getenv("DB_USER", "postgres")
    password: str = os.getenv("DB_PASSWORD", "")

    @property
    def url(self) -> str:
        """Returns a full PostgreSQL connection URL."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class AppConfig:
    """
    Top-level application configuration.

    Controls server behaviour, token expiry, and rate limiting.
    """
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "8000"))
    token_expiry_seconds: int = int(os.getenv("TOKEN_EXPIRY", "3600"))
    max_requests_per_minute: int = int(os.getenv("RATE_LIMIT", "60"))
    db: DatabaseConfig = None

    def __post_init__(self):
        if self.db is None:
            self.db = DatabaseConfig()


def load_config() -> AppConfig:
    """
    Loads and returns the application configuration.

    Reads all values from environment variables.
    Call this once at startup and pass the config object around.

    Returns:
        A fully populated AppConfig instance.
    """
    return AppConfig()
