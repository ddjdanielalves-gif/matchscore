from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from threading import Lock

import httpx

from ..config import settings
from ..schemas import (
    Match,
    PlayerIssue,
    Score,
    Standings,
    StandingsEntry,
    TeamRef,
)
from .cache import cached

logger = logging.getLogger("matchscore.api")

# football-data.org free plan:
# 10 requests/minute.
_RATE_INTERVAL = 6.2

_rate_lock = Lock()
_last_call = 0.0

_WINDOW_DAYS_BACK = 3
_WINDOW_DAYS_FORWARD = 10


def _throttle() -> None:
    """Keep requests safely below the free-plan rate limit."""
    global _last_call

    with _rate_lock:
        wait = _last_call + _RATE_INTERVAL - time.monotonic()

        if wait > 0:
            time.sleep(wait)

        _last_call = time.monotonic()


def datetime_iso(value: str | None) -> datetime:
    """Convert an ISO-8601 API date to an aware UTC datetime."""

    if not value:
        return datetime.now(timezone.utc)

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (TypeError, ValueError):
        logger.warning("Invalid API datetime: %r", value)
        return datetime.now(timezone.utc)


class RapidApiProvider:
    """
    Compatibility provider for the MatchScore.

    The old class name is intentionally preserved so provider.py
    does not need to change.

    Data source:
        football-data.org API v4
    """

    source = "api"

    def __init__(self) -> None:
        self._key = settings.api_key.strip()
        self._base = (
            settings.api_base_url.rstrip("/")
        )

        self._headers = {
            "X-Auth-Token": self._key,
            "Accept": "application/json",
            "User-Agent": "MatchScore/1.0",
        }

        self._competition = getattr(
            settings,
            "competition_code",
            "BSA",
        )

        logger.info(
            "football-data provider initialized: "
            "competition=%s season=%s base_season=%s",
            self._competition,
            settings.season,
            settings.base_season,
        )

    # ============================================================
    # HTTP
    # ============================================================

    def _get(
        self,
        path: str,
        params: dict | None = None,
    ) -> dict | None:

        url = f"{self._base}{path}"

        try:
            _throttle()

            logger.info(
                "football-data request: %s params=%s",
                path,
                params or {},
            )

            with httpx.Client(
                timeout=20,
                headers=self._headers,
            ) as client:

                response = client.get(
                    url,
                    params=params or {},
                )

            logger.info(
                "football-data response: "
                "%s status=%s",
                path,
                response.status_code,
            )

            if response.status_code == 401:
                logger.error(
                    "football-data authentication failed. "
                    "Check MATCH_API_KEY."
                )
                return None

            if response.status_code == 403:
                logger.error(
                    "football-data access denied. "
                    "The competition/season may not be "
                    "available on the current plan."
                )
                return None

            if response.status_code == 404:
                logger.warning(
                    "football-data resource not found: %s",
                    path,
                )
                return None

            if response.status_code == 429:
                logger.warning(
                    "football-data rate limit reached."
                )

                # Do not make several immediate retries.
                # The service will fall back to cache/mock.
                return None

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, dict):
                logger.warning(
                    "Unexpected API response type: %s",
                    type(data),
                )
                return None

            return data

        except httpx.TimeoutException as exc:
            logger.warning(
                "football-data timeout: %s",
                exc,
            )
            return None

        except httpx.HTTPError as exc:
            logger.warning(
                "football-data HTTP error: %s",
                exc,
            )
            return None

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Unexpected football-data error: %s",
                exc,
            )
            return None

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _short_name(name: str) -> str:
        if not name:
            return "???"

        norm = unicodedata.normalize(
            "NFD",
            name,
        )

        plain = "".join(
            char
            for char in norm
            if not unicodedata.combining(char)
        )

        words = plain.replace("-", " ").split()

        if not words:
            return "???"

        return words[0][:3].upper()

    @staticmethod
    def _team(team: dict) -> TeamRef:
        team_id = team.get("id", 0)

        try:
            team_id = int(team_id)
        except (TypeError, ValueError):
            team_id = 0

        name = (
            team.get("name")
            or team.get("shortName")
            or "?"
        )

        short_name = (
            team.get("tla")
            or team.get("shortName")
            or RapidApiProvider._short_name(name)
        )

        return TeamRef(
            id=team_id,
            name=name,
            short_name=short_name,
            crest=team.get("crest") or "",
        )

    @staticmethod
    def _status(status: str | None) -> str:
        value = (status or "").upper()

        if value in {
            "IN_PLAY",
            "PAUSED",
            "LIVE",
            "POSTPONED",
        }:
            if value == "POSTPONED":
                return "postponed"

            return "in_play"

        if value in {
            "FINISHED",
        }:
            return "finished"

        if value in {
            "CANCELLED",
            "SUSPENDED",
        }:
            return "postponed"

        if value in {
            "TIMED",
            "SCHEDULED",
            "AWAITING_PENALTIES",
            "AWAITING_EXTRA_TIME",
        }:
            return "scheduled"

        return "scheduled"

    @staticmethod
    def _round_label(match: dict) -> str:
        matchday = match.get("matchday")

        if matchday is not None:
            try:
                return f"Rodada {int(matchday)}"
            except (TypeError, ValueError):
                pass

        return (
            match.get("stage")
            or ""
        )

    @staticmethod
    def _is_finished(match: dict) -> bool:
        return (
            str(match.get("status", "")).upper()
            == "FINISHED"
        )

    @staticmethod
    def _extract_score(match: dict) -> tuple[int | None, int | None]:
        score = match.get("score") or {}

        # football-data provides:
        # score.fullTime.home
        # score.fullTime.away
        full_time = score.get("fullTime") or {}

        home = full_time.get("home")
        away = full_time.get("away")

        if home is None:
            home = score.get("home")

        if away is None:
            away = score.get("away")

        try:
            home = int(home) if home is not None else None
        except (TypeError, ValueError):
            home = None

        try:
            away = int(away) if away is not None else None
        except (TypeError, ValueError):
            away = None

        return home, away

    def _match_to_model(self, match: dict) -> Match:
        home_goals, away_goals = self._extract_score(
            match
        )

        return Match(
            id=int(match.get("id", 0)),
            round=self._round_label(match),
            date=datetime_iso(
                match.get("utcDate")
            ),
            status=self._status(
                match.get("status")
            ),
            home=self._team(
                match.get("homeTeam") or {}
            ),
            away=self._team(
                match.get("awayTeam") or {}
            ),
            score=Score(
                home=home_goals,
                away=away_goals,
            ),
            source="api",
        )

    # ============================================================
    # COMPETITION
    # ============================================================

    def _competition_info(
        self,
        season: int | None = None,
    ) -> dict | None:

        params = {}

        if season is not None:
            params["season"] = season

        key = (
            f"competition:"
            f"{self._competition}:"
            f"{season or 'current'}"
        )

        return cached(6 * 3600)(
            lambda _key: self._get(
                f"/competitions/{self._competition}",
                params,
            )
        )(key)

    def _current_matchday(self) -> int | None:
        data = self._competition_info(
            settings.season
        )

        if not data:
            return None

        season = data.get("currentSeason") or {}

        value = season.get("currentMatchday")

        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    # ============================================================
    # MATCHES
    # ============================================================

    def _fetch_matches(
        self,
        *,
        season: int | None = None,
        matchday: int | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:

        params: dict[str, str | int] = {}

        if season is not None:
            params["season"] = season

        if matchday is not None:
            params["matchday"] = matchday

        if status:
            params["status"] = status

        if date_from:
            params["dateFrom"] = date_from

        if date_to:
            params["dateTo"] = date_to

        cache_key = (
            f"matches:"
            f"{self._competition}:"
            f"{season or 'current'}:"
            f"{matchday or ''}:"
            f"{status or ''}:"
            f"{date_from or ''}:"
            f"{date_to or ''}"
        )

        data = cached(15 * 60)(
            lambda _key: self._get(
                f"/competitions/"
                f"{self._competition}/matches",
                params,
            )
        )(cache_key)

        if not data:
            return []

        matches = data.get("matches") or []

        if not isinstance(matches, list):
            return []

        return matches

    # ============================================================
    # FIXTURES
    # ============================================================

    def fixtures(self) -> list[Match]:
        """
        Returns matches from the current matchday.

        If current matchday cannot be determined, uses a
        small date window as fallback.
        """

        current = self._current_matchday()

        if current is not None:
            matches = self._fetch_matches(
                season=settings.season,
                matchday=current,
            )

            if matches:
                result = [
                    self._match_to_model(m)
                    for m in matches
                ]

                result.sort(
                    key=lambda item: item.date
                )

                logger.info(
                    "fixtures(): %d matches "
                    "from matchday %s",
                    len(result),
                    current,
                )

                return result

        logger.warning(
            "Could not determine current "
            "matchday. Using date fallback."
        )

        raw = self._fetch_window()

        result = [
            self._match_to_model(m)
            for m in raw
        ]

        result.sort(
            key=lambda item: item.date
        )

        return result

    # ============================================================
    # DATE WINDOW
    # ============================================================

    def _window_dates(self) -> tuple[str, str]:
        today = date.today()

        first = (
            today
            - timedelta(days=_WINDOW_DAYS_BACK)
        ).isoformat()

        last = (
            today
            + timedelta(days=_WINDOW_DAYS_FORWARD)
        ).isoformat()

        return first, last

    def _fetch_window(self) -> list[dict]:
        date_from, date_to = self._window_dates()

        return self._fetch_matches(
            season=settings.season,
            date_from=date_from,
            date_to=date_to,
        )

    # ============================================================
    # ALL FINISHED
    # ============================================================

    def all_finished(self) -> list[Match]:
        raw = self._fetch_matches(
            season=settings.base_season,
            status="FINISHED",
        )

        result = [
            self._match_to_model(m)
            for m in raw
            if self._is_finished(m)
        ]

        result.sort(
            key=lambda item: item.date,
            reverse=True,
        )

        return result

    # ============================================================
    # UPCOMING
    # ============================================================

    def upcoming(
        self,
        round_no: int | None = None,
    ) -> list[Match]:

        if round_no is not None:
            raw = self._fetch_matches(
                season=settings.season,
                matchday=round_no,
            )
        else:
            current = self._current_matchday()

            if current is not None:
                raw = self._fetch_matches(
                    season=settings.season,
                    matchday=current,
                )
            else:
                raw = self._fetch_window()

        result = [
            self._match_to_model(m)
            for m in raw
            if not self._is_finished(m)
        ]

        if round_no is not None:
            result = [
                m
                for m in result
                if self._round_number(m.round)
                == round_no
            ]

        result.sort(
            key=lambda item: item.date
        )

        return result

    # ============================================================
    # RECENT RESULTS
    # ============================================================

    def recent_results(
        self,
        days: int = 3,
    ) -> list[Match]:

        today = date.today()

        date_from = (
            today
            - timedelta(days=days)
        ).isoformat()

        date_to = today.isoformat()

        raw = self._fetch_matches(
            season=settings.season,
            status="FINISHED",
            date_from=date_from,
            date_to=date_to,
        )

        result = [
            self._match_to_model(m)
            for m in raw
            if self._is_finished(m)
        ]

        result.sort(
            key=lambda item: item.date,
            reverse=True,
        )

        return result

    # ============================================================
    # SINGLE MATCH
    # ============================================================

    def match(
        self,
        match_id: int,
    ) -> Match | None:

        data = cached(5 * 60)(
            lambda _key: self._get(
                f"/matches/{match_id}",
            )
        )(
            f"match:{match_id}"
        )

        if not data:
            return None

        try:
            return self._match_to_model(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not map match %s: %s",
                match_id,
                exc,
            )
            return None

    # ============================================================
    # STANDINGS
    # ============================================================

    def standings(self) -> Standings | None:
        """
        Returns the official TOTAL standings.

        football-data.org returns TOTAL, HOME and AWAY
        standings. MatchScore uses TOTAL.
        """

        data = cached(30 * 60)(
            lambda _key: self._get(
                f"/competitions/"
                f"{self._competition}/standings",
                {
                    "season": settings.season,
                },
            )
        )(
            f"standings:"
            f"{self._competition}:"
            f"{settings.season}"
        )

        if not data:
            return None

        standings = data.get("standings") or []

        total = next(
            (
                item
                for item in standings
                if item.get("type") == "TOTAL"
            ),
            None,
        )

        if not total:
            logger.warning(
                "TOTAL standings not found."
            )
            return None

        table = total.get("table") or []

        rows: list[StandingsEntry] = []

        for row in table:
            team_data = row.get("team") or {}

            try:
                position = int(
                    row.get("position", 0)
                )
            except (TypeError, ValueError):
                position = 0

            try:
                games = int(
                    row.get("playedGames", 0)
                )
            except (TypeError, ValueError):
                games = 0

            try:
                wins = int(
                    row.get("won", 0)
                )
            except (TypeError, ValueError):
                wins = 0

            try:
                draws = int(
                    row.get("draw", 0)
                )
            except (TypeError, ValueError):
                draws = 0

            try:
                losses = int(
                    row.get("lost", 0)
                )
            except (TypeError, ValueError):
                losses = 0

            try:
                goals_for = int(
                    row.get("goalsFor", 0)
                )
            except (TypeError, ValueError):
                goals_for = 0

            try:
                goals_against = int(
                    row.get("goalsAgainst", 0)
                )
            except (TypeError, ValueError):
                goals_against = 0

            try:
                goal_difference = int(
                    row.get("goalDifference", 0)
                )
            except (TypeError, ValueError):
                goal_difference = 0

            try:
                points = int(
                    row.get("points", 0)
                )
            except (TypeError, ValueError):
                points = 0

            rows.append(
                StandingsEntry(
                    position=position,
                    team=self._team(team_data),
                    games=games,
                    wins=wins,
                    draws=draws,
                    losses=losses,
                    goals_for=goals_for,
                    goals_against=goals_against,
                    goal_difference=goal_difference,
                    points=points,
                )
            )

        return Standings(
            entries=rows
        )

    # ============================================================
    # PREDICTIONS
    # ============================================================

    def predictions(
        self,
        match_id: int,
    ) -> dict | None:
        """
        football-data.org does not provide an equivalent
        prediction endpoint.

        MatchScore's own prediction/model layer can continue
        to calculate predictions from available match data.
        """

        return None

    # ============================================================
    # INJURIES / SUSPENSIONS
    # ============================================================

    def team_issues(
        self,
        team_id: int,
    ) -> tuple[
        list[PlayerIssue],
        list[PlayerIssue],
    ]:

        # football-data.org does not expose the API-Football
        # injuries/suspensions endpoint used previously.

        return [], []

    # ============================================================
    # CARDS
    # ============================================================

    def team_cards(
        self,
        team_id: int,
    ) -> tuple[float, float]:

        # No equivalent reliable team-card endpoint is used
        # here. Return neutral values rather than inventing data.

        return 2.0, 0.1

    # ============================================================
    # ROUND NUMBER
    # ============================================================

    @staticmethod
    def _round_number(
        round_label: str,
    ) -> int | None:

        if not round_label:
            return None

        found = re.search(
            r"(\d+)\s*$",
            round_label.strip(),
        )

        return (
            int(found.group(1))
            if found
            else None
        )
