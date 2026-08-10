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

_RATE_INTERVAL = 1.2
_rate_lock = Lock()
_last_call = 0.0

_WINDOW_DAYS_BACK = 3
_WINDOW_DAYS_FORWARD = 10


def _throttle() -> None:
    global _last_call

    with _rate_lock:
        wait = _last_call + _RATE_INTERVAL - time.monotonic()

        if wait > 0:
            time.sleep(wait)

        _last_call = time.monotonic()


class RapidApiProvider:
    """Provider principal usando API-Football."""

    source = "api"

    def __init__(self) -> None:
        self._key = settings.api_key
        self._base = settings.api_base_url

        if "rapidapi" in settings.api_host.lower():
            self._headers = {
                "X-RapidAPI-Key": self._key,
                "X-RapidAPI-Host": settings.api_host,
            }
        else:
            self._headers = {
                "x-apisports-key": self._key,
            }

    # ============================================================
    # HTTP
    # ============================================================

    def _get(self, path: str, params: dict) -> dict | None:
        url = f"{self._base}{path}"

        for attempt in range(2):
            _throttle()

            try:
                with httpx.Client(
                    timeout=15,
                    headers=self._headers,
                ) as client:
                    logger.info(
                        "API request: %s params=%s",
                        path,
                        params,
                    )

                    response = client.get(
                        url,
                        params=params,
                    )

                    logger.info(
                        "API response: %s status=%s",
                        path,
                        response.status_code,
                    )

                    if response.status_code == 429:
                        logger.warning(
                            "API quota exceeded for %s",
                            path,
                        )

                        if attempt == 0:
                            time.sleep(5)
                            continue

                        return None

                    response.raise_for_status()

                    data = response.json()

                    errors = data.get("errors")

                    if errors:
                        logger.warning(
                            "API errors for %s: %s",
                            path,
                            errors,
                        )

                    logger.info(
                        "API results=%s response_items=%s",
                        data.get("results"),
                        len(data.get("response") or []),
                    )

                    return data

            except Exception as exc:
                logger.warning(
                    "API request failed: %s params=%s error=%s",
                    path,
                    params,
                    exc,
                )
                return None

        return None

    # ============================================================
    # MAPPERS
    # ============================================================

    @staticmethod
    def _short_name(name: str) -> str:
        norm = unicodedata.normalize("NFD", name)

        plain = "".join(
            c for c in norm
            if not unicodedata.combining(c)
        )

        first = plain.split("-")[0].split()[0]

        return first[:3].upper() if first else "???"

    @staticmethod
    def _team(t: dict) -> TeamRef:
        name = t.get("name", "?")

        return TeamRef(
            id=int(t.get("id", 0)),
            name=name,
            short_name=(
                t.get("code")
                or RapidApiProvider._short_name(name)
            ),
            crest=t.get("logo", ""),
        )

    @staticmethod
    def _status(short: str) -> str:
        if short in {"NS", "TBD", "SUS"}:
            return "scheduled"

        if short in {
            "1H",
            "2H",
            "HT",
            "ET",
            "BT",
            "P",
            "INT",
        }:
            return "in_play"

        if short in {"FT", "AET", "PEN"}:
            return "finished"

        if short in {"PST", "CANC"}:
            return "postponed"

        return "scheduled"

    def _fixture_to_match(self, f: dict) -> Match:
        fixture = f.get("fixture") or {}
        teams = f.get("teams") or {}
        goals = f.get("goals") or {}

        home_goals = goals.get("home")
        away_goals = goals.get("away")

        return Match(
            id=int(fixture.get("id", 0)),
            round=(f.get("league") or {}).get("round", ""),
            date=datetime_iso(fixture.get("date")),
            status=self._status(
                (fixture.get("status") or {}).get(
                    "short",
                    "",
                )
            ),
            home=self._team(
                teams.get("home") or {}
            ),
            away=self._team(
                teams.get("away") or {}
            ),
            score=Score(
                home=(
                    int(home_goals)
                    if home_goals is not None
                    else None
                ),
                away=(
                    int(away_goals)
                    if away_goals is not None
                    else None
                ),
            ),
            source="api",
        )

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _is_target_league(f: dict) -> bool:
        league = f.get("league") or {}

        try:
            league_id = int(league.get("id", 0))
        except (TypeError, ValueError):
            return False

        return league_id == settings.league_id

    @staticmethod
    def _round_number(round_label: str) -> int | None:
        if not round_label:
            return None

        match = re.search(
            r"(\d+)\s*$",
            round_label.strip(),
        )

        return int(match.group(1)) if match else None

    # ============================================================
    # RODADAS
    # ============================================================

    def _fetch_rounds(self) -> list[str]:
        """
        Obtém todas as rodadas disponíveis da temporada atual.
        """

        params = {
            "league": settings.league_id,
            "season": settings.season,
        }

        data = cached(12 * 3600)(
            lambda _k: self._get(
                "/fixtures/rounds",
                params,
            )
        )(
            f"rounds:{settings.league_id}:{settings.season}"
        )

        if not data:
            return []

        rounds = data.get("response") or []

        rounds = [
            str(r)
            for r in rounds
            if r
        ]

        logger.info(
            "Available rounds for league=%s season=%s: %s",
            settings.league_id,
            settings.season,
            rounds,
        )

        return rounds

    def _fetch_current_round(self) -> str | None:
        """
        Obtém diretamente a rodada atual.
        """

        params = {
            "league": settings.league_id,
            "season": settings.season,
            "current": "true",
        }

        data = cached(60 * 60)(
            lambda _k: self._get(
                "/fixtures/rounds",
                params,
            )
        )(
            f"current-round:{settings.league_id}:{settings.season}"
        )

        if not data:
            return None

        rounds = data.get("response") or []

        if not rounds:
            return None

        current = str(rounds[0])

        logger.info(
            "Current round detected: %s",
            current,
        )

        return current

    def _fetch_round_fixtures(
        self,
        round_label: str,
    ) -> list[dict]:
        """
        Busca somente os jogos da rodada especificada.
        """

        params = {
            "league": settings.league_id,
            "season": settings.season,
            "round": round_label,
        }

        data = cached(15 * 60)(
            lambda _k: self._get(
                "/fixtures",
                params,
            )
        )(
            f"round-fixtures:"
            f"{settings.league_id}:"
            f"{settings.season}:"
            f"{round_label}"
        )

        if not data:
            return []

        response = data.get("response") or []

        fixtures = [
            f
            for f in response
            if self._is_target_league(f)
        ]

        logger.info(
            "Round %s: %d fixtures returned, %d valid",
            round_label,
            len(response),
            len(fixtures),
        )

        return fixtures

    # ============================================================
    # FALLBACK POR PERÍODO
    # ============================================================

    def _window_dates(self) -> list[str]:
        today = date.today()

        return [
            (
                today + timedelta(days=d)
            ).isoformat()
            for d in range(
                -_WINDOW_DAYS_BACK,
                _WINDOW_DAYS_FORWARD + 1,
            )
        ]

    def _fetch_window(self) -> list[dict]:
        """
        Fallback caso a consulta por rodada não retorne dados.
        Cada chamada já é restrita à Série A e temporada.
        """

        seen: dict[int, dict] = {}

        for day in self._window_dates():

            params = {
                "league": settings.league_id,
                "season": settings.season,
                "date": day,
            }

            data = cached(15 * 60)(
                lambda _k, p=params: self._get(
                    "/fixtures",
                    p,
                )
            )(
                f"window:"
                f"{settings.league_id}:"
                f"{settings.season}:"
                f"{day}"
            )

            if not data:
                continue

            response = data.get("response") or []

            logger.info(
                "Date %s: %d fixtures",
                day,
                len(response),
            )

            for fixture in response:
                if not self._is_target_league(fixture):
                    continue

                fixture_id = int(
                    (fixture.get("fixture") or {}).get(
                        "id",
                        0,
                    )
                )

                if fixture_id > 0:
                    seen[fixture_id] = fixture

        result = list(seen.values())

        logger.info(
            "Window total: %d valid fixtures",
            len(result),
        )

        return result

    # ============================================================
    # FIXTURES PRINCIPAIS
    # ============================================================

    def fixtures(self) -> list[Match]:
        """
        Retorna os jogos da rodada atual.

        Primeiro:
            /fixtures/rounds?current=true

        Depois:
            /fixtures?league=71&season=2026&round=...

        Se isso falhar:
            busca por datas como fallback.
        """

        current_round = self._fetch_current_round()

        if current_round:
            fixtures = self._fetch_round_fixtures(
                current_round
            )

            if fixtures:
                matches = [
                    self._fixture_to_match(f)
                    for f in fixtures
                ]

                matches.sort(
                    key=lambda m: m.date
                )

                logger.info(
                    "fixtures(): %d matches from round %s",
                    len(matches),
                    current_round,
                )

                return matches

        logger.warning(
            "Current-round lookup failed. "
            "Using date-window fallback."
        )

        fixtures = self._fetch_window()

        matches = [
            self._fixture_to_match(f)
            for f in fixtures
        ]

        matches.sort(
            key=lambda m: m.date
        )

        return matches

    # ============================================================
    # TODOS OS FINALIZADOS DA TEMPORADA BASE
    # ============================================================

    def _fetch_base_season(self) -> list[dict]:
        params = {
            "league": settings.league_id,
            "season": settings.base_season,
        }

        data = cached(12 * 3600)(
            lambda _k: self._get(
                "/fixtures",
                params,
            )
        )(
            f"fixtures:"
            f"{settings.league_id}:"
            f"{settings.base_season}"
        )

        if not data:
            return []

        return data.get("response") or []

    def all_finished(self) -> list[Match]:
        fixtures = self._fetch_base_season()

        matches = [
            self._fixture_to_match(f)
            for f in fixtures
            if (
                (f.get("fixture") or {})
                .get("status", {})
                .get("short")
                in {"FT", "AET", "PEN"}
            )
        ]

        matches.sort(
            key=lambda m: m.date,
            reverse=True,
        )

        return matches

    # ============================================================
    # UPCOMING
    # ============================================================

    def upcoming(
        self,
        round_no: int | None = None,
    ) -> list[Match]:

        if round_no is not None:

            # Descobre o nome oficial da rodada.
            rounds = self._fetch_rounds()

            target_round = next(
                (
                    r
                    for r in rounds
                    if self._round_number(r) == round_no
                ),
                None,
            )

            if target_round:
                fixtures = self._fetch_round_fixtures(
                    target_round
                )

                matches = [
                    self._fixture_to_match(f)
                    for f in fixtures
                    if self._status(
                        (
                            f.get("fixture") or {}
                        )
                        .get("status", {})
                        .get("short", "")
                    )
                    != "finished"
                ]

                matches.sort(
                    key=lambda m: m.date
                )

                if matches:
                    return matches

        # Sem rodada específica:
        current_round = self._fetch_current_round()

        if current_round:
            fixtures = self._fetch_round_fixtures(
                current_round
            )

            if fixtures:
                matches = [
                    self._fixture_to_match(f)
                    for f in fixtures
                    if self._status(
                        (
                            f.get("fixture") or {}
                        )
                        .get("status", {})
                        .get("short", "")
                    )
                    != "finished"
                ]

                matches.sort(
                    key=lambda m: m.date
                )

                if matches:
                    return matches

        # Fallback.
        fixtures = self._fetch_window()

        matches = [
            self._fixture_to_match(f)
            for f in fixtures
            if self._status(
                (
                    f.get("fixture") or {}
                )
                .get("status", {})
                .get("short", "")
            )
            != "finished"
        ]

        if round_no is not None:
            matches = [
                m
                for m in matches
                if self._round_number(m.round)
                == round_no
            ]

        matches.sort(
            key=lambda m: m.date
        )

        return matches

    # ============================================================
    # RESULTADOS RECENTES
    # ============================================================

    def recent_results(
        self,
        days: int = 3,
    ) -> list[Match]:

        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(days=days)
        )

        fixtures = self._fetch_window()

        matches = [
            self._fixture_to_match(f)
            for f in fixtures
            if self._status(
                (
                    f.get("fixture") or {}
                )
                .get("status", {})
                .get("short", "")
            )
            == "finished"
        ]

        matches = [
            m
            for m in matches
            if m.date >= cutoff
        ]

        return sorted(
            matches,
            key=lambda m: m.date,
            reverse=True,
        )

    # ============================================================
    # PARTIDA
    # ============================================================

    def match(
        self,
        match_id: int,
    ) -> Match | None:

        data = cached(15 * 60)(
            lambda _k: self._get(
                "/fixtures",
                {"id": match_id},
            )
        )(
            f"match:{match_id}"
        )

        if (
            not data
            or not data.get("response")
        ):
            return None

        fixture = data["response"][0]

        if not self._is_target_league(
            fixture
        ):
            return None

        return self._fixture_to_match(
            fixture
        )

    # ============================================================
    # STANDINGS
    # ============================================================

    def standings(self) -> Standings | None:

        data = cached(12 * 3600)(
            lambda _k: self._get(
                "/standings",
                {
                    "league": settings.league_id,
                    "season": settings.base_season,
                },
            )
        )(
            f"standings:"
            f"{settings.league_id}:"
            f"{settings.base_season}"
        )

        if (
            not data
            or not data.get("response")
        ):
            return None

        table = (
            data["response"][0]
            .get("league", {})
            .get("standings", [[]])[0]
        )

        rows: list[StandingsEntry] = []

        for row in table:

            all_games = row.get("all") or {}

            rows.append(
                StandingsEntry(
                    position=int(
                        row.get("rank", 0)
                    ),
                    team=self._team(
                        row.get("team") or {}
                    ),
                    games=int(
                        all_games.get(
                            "played",
                            0,
                        )
                    ),
                    wins=int(
                        all_games.get(
                            "win",
                            0,
                        )
                    ),
                    
