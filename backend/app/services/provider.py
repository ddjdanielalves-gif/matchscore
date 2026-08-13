from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..config import settings
from ..schemas import Match, PlayerIssue, Standings
from .mock import MockProvider
from .rapidapi import RapidApiProvider

logger = logging.getLogger("matchscore.service")


class DataService:
    """Tries the real provider (api-football) and falls back to the demo
    provider on any failure. The `sources_used` set records what actually
    fed each response so the UI can flag demo vs real data honestly."""

    def __init__(self) -> None:
        use_api = bool(settings.api_key) and not settings.mock_mode
        self.primary = RapidApiProvider() if use_api else MockProvider()
        self.fallback = MockProvider()
        self.sources_used: set[str] = set()
        self.estimates: set[str] = set()
        logger.info("Primary data provider: %s", self.primary.source)

    def _pick(self, method: str, *args):
        try:
            value = getattr(self.primary, method)(*args)
            if value is None:
                raise RuntimeError(f"{method} returned None")
            self.sources_used.add(self.primary.source)
            return value
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falling back to demo for %s: %s", method, exc)
            value = getattr(self.fallback, method)(*args)
            self.sources_used.add(self.fallback.source)
            return value

    def fixtures(self) -> list[Match]:
        return self._pick("fixtures")

    def all_finished(self) -> list[Match]:
        value = self._pick("all_finished")
        if self.primary.source == "api":
            self.estimates.add("forca e forma: ultima temporada completa no plano gratuito")
        return value

    def upcoming(self, round_no: int | None = None) -> list[Match]:
        return self._pick("upcoming", round_no)

    def recent_results(self, days: int = 3) -> list[Match]:
        """Matches finished within the last `days` days, most recent first.

        Prefers the provider's own date-window implementation when available;
        otherwise falls back to filtering the fixtures window (which already
        goes through the normal primary/fallback path).
        """
        provider_method = getattr(self.primary, "recent_results", None)
        if callable(provider_method):
            try:
                value = provider_method(days)
                if value:
                    self.sources_used.add(self.primary.source)
                    return value
            except Exception as exc:  # noqa: BLE001
                logger.warning("recent_results unavailable: %s", exc)

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        matches = self.fixtures()

        def _as_utc(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        results = [
            m for m in matches
            if m.status == "finished" and _as_utc(m.date) >= cutoff
        ]
        return sorted(results, key=lambda m: m.date, reverse=True)

    def match(self, match_id: int) -> Match | None:
        return self._pick("match", match_id)

    def standings(self) -> Standings:
        value = self._pick("standings")
        if self.primary.source == "api":
            self.estimates.add("tabela: temporada atual")
        return value

    def predictions(self, match_id: int) -> dict | None:
        try:
            value = self.primary.predictions(match_id)
            if not value:
                return None
            self.sources_used.add(self.primary.source)
            return value
        except Exception as exc:  # noqa: BLE001
            logger.warning("predictions unavailable for %s: %s", match_id, exc)
            return None

    def team_issues(self, team_id: int) -> tuple[list[PlayerIssue], list[PlayerIssue]]:
        try:
            injuries, suspensions = self.primary.team_issues(team_id)
            if injuries is None or suspensions is None:
                raise RuntimeError("issues unavailable")
            self.sources_used.add(self.primary.source)
            return injuries, suspensions
        except Exception:  # noqa: BLE001
            if self.primary.source == "api":
                self.estimates.add("lesoes e suspensoes nao disponiveis no plano gratuito")
                return [], []
            injuries, suspensions = self.fallback.team_issues(team_id)
            self.sources_used.add(self.fallback.source)
            return injuries, suspensions

    def team_cards(self, team_id: int) -> tuple[float, float]:
        try:
            cards = self.primary.team_cards(team_id)
            if cards is None:
                raise RuntimeError("cards unavailable")
            self.sources_used.add(self.primary.source)
            return cards
        except Exception:  # noqa: BLE001
            if self.primary.source == "api":
                self.estimates.add("cartoes: media da liga (estimado)")
                return 2.0, 0.1
            cards = self.fallback.team_cards(team_id)
            self.sources_used.add(self.fallback.source)
            return cards

    def snapshot_sources(self) -> list[str]:
        sources = list(self.sources_used) + list(self.estimates)
        self.sources_used.clear()
        self.estimates.clear()
        return sources
                
