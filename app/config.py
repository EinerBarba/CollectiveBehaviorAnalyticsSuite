"""Application settings, read from environment variables or the `.env` file.

Every setting is required. The application fails at import time if one is
missing, because `settings` is created when this module loads. Variable names
are case-insensitive, so `DATABASE_URL` sets `database_url`.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration values the backend uses."""

    database_url: str
    """PostgreSQL connection string. Must use the `postgresql+asyncpg` driver."""

    jwt_secret: str
    """Secret key used to sign access tokens. Keep it private."""

    storage_root: str
    """Folder where uploaded videos and all results are written."""

    jwt_algorithm: str
    """Signing algorithm for access tokens, for example `HS256`."""

    access_token_expire_minutes: int
    """Lifetime of an access token, in minutes."""

    refresh_token_expire_days: int
    """Lifetime of a refresh token, in days. Also the refresh cookie's lifetime."""

    cookie_secure: bool
    """Whether the refresh cookie is sent only over HTTPS. Use False for local development."""

    cookie_domain: str
    """Domain the refresh cookie is set for."""

    cors_origins: str
    """Comma-separated list of frontend addresses allowed to call the API."""

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def cors_origin_list(self) -> list[str]:
        """The CORS origins as a list, with surrounding spaces removed."""
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()
"""The single settings instance used throughout the application."""
