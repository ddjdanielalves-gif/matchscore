from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="MATCH_",
    )

    app_name: str = "MatchScore API"
    version: str = "0.1.0"

    # api-football. Supports both the direct API (v3.football.api-sports.io,
    # header x-apisports-key) and the legacy RapidAPI host (api-football-v1.
    # p.rapidapi.com, header X-RapidAPI-Key). The host auto-selects the auth.
    # Empty key -> the app runs fully in demo mode (responses flagged as demo).
    api_key: str = ""
    api_host: str = "v3.football.api-sports.io"
    api_base_url: str = "https://v3.football.api-sports.io"
    league_id: int = 71  # Campeonato Brasileiro Serie A
    season: int = 2026
    # On the free plan, current-season league queries are blocked (only
    # seasons 2022-2024 are accessible). base_season feeds the strength
    # model (ELO/form/attack/defense) with the most recent real season.
    base_season: int = 2024

    # Force demo mode even when an API key is present.
    mock_mode: bool = False

    # Cache TTL (seconds) for raw provider data.
    cache_ttl_seconds: int = 1800

    # CORS origins for the web frontend and the Capacitor (Android) app.
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "https://localhost,http://localhost,capacitor://localhost"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
settings.mock_mode = settings.mock_mode or os.environ.get("MATCH_MOCK", "") == "1"
