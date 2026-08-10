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

    # ============================================================
    # FOOTBALL-DATA.ORG
    # ============================================================

    # No Render:
    # MATCH_API_KEY = seu token do football-data.org
    api_key: str = ""

    # API v4
    api_host: str = "api.football-data.org"
    api_base_url: str = "https://api.football-data.org/v4"

    # Código da competição.
    # Série A do Brasil = BSA
    competition_code: str = "BSA"

    # Mantido para compatibilidade com o restante do projeto.
    # Não é mais usado como league ID da API-Football.
    league_id: int = 2013

    # Temporada atual.
    season: int = 2026

    # Temporada-base usada pelo modelo quando necessário.
    base_season: int = 2025

    # Force demo mode mesmo com API key.
    mock_mode: bool = False

    # Cache TTL.
    cache_ttl_seconds: int = 1800

    # CORS.
    cors_origins: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:5174,"
        "http://127.0.0.1:5174,"
        "https://localhost,"
        "http://localhost,"
        "capacitor://localhost"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            o.strip()
            for o in self.cors_origins.split(",")
            if o.strip()
        ]


settings = Settings()

settings.mock_mode = (
    settings.mock_mode
    or os.environ.get("MATCH_MOCK", "") == "1"
)
