"""Application settings, loaded from environment variables (and a local .env file).

Using pydantic-settings gives us typed, validated config with a single source of
truth. Every deployment environment (local, Railway/Render) sets these vars.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App metadata
    app_name: str = "FitMind AI API"
    environment: str = "development"

    # Comma-separated list of origins allowed to call this API (the Next.js app).
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS origins into a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# A single importable settings instance used across the app.
settings = Settings()
