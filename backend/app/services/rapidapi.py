from __future__ import annotations

import logging
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

_RATE_INTERVAL = 1.2  # seconds between calls (free tier throttles per minute)
_rate_lock = Lock()
_last_call = 0.0


def _throttle() -> None:
    """Sleep so api-football free tier does not return 429."""
    global _last_call
    with _rate_lock:
        wait = _last_call + _RATE_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


class RapidApiProvider:
    """Provider for api-football (free tier).

    Free-plan restrictions we work around:
      * /fixtures?league&season (current season) -> blocked, only 2022-2024
        allowed. We pull finished strength data from `base_season` (2024) and
        current fixtures from the 3-day ?date= window.
      * /predictions?fixture -> works and returns real current percentages.
      * /players/injuries, /lineups, /teams/statistics -> blocked, so those
        degrade to honest estimates (None) and the UI flags them.
    """

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
            self._headers = {"x-apisports-key": self._key}

    # ------------------------------------------------------------------ http
    def _get(self, path: str, params: dict) -> dict | None:
        url = f"{self._base}{path}"
        for attempt in range(2):
            _throttle()
            try:
                with httpx.Client(timeout=15, headers=self._headers) as client:
                    resp = client.get(url, params=params)
                    if resp.status_code == 429:
                        logger.warning("api-football quota exceeded for %s (attempt %d)", path, attempt + 1)
                        time.sleep(5.0)
                        continue
                    resp.raise_for_status()
                    return resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning("api-football request failed for %s: %s", path, exc)
                return None
        return None

    # ----------------------------------------------------------- mappers
    @staticmethod
    def _short_name(name: str) -> str:
        norm = unicodedata.normalize("NFD", name)
        plain = "".join(c for c in norm if not unicodedata.combining(c))
        first = plain.split("-")[0].split()[0]
        return first[:3].upper() if first else "???"

    @staticmethod
    def _team(t: dict) -> TeamRef:
        name = t.get("name", "?")
        return TeamRef(id=int(t.get("id", 0)), name=name, short_name=t.get("code") or RapidApiProvider._short_name(name), crest=t.get("logo", ""))

    @staticmethod
    def _status(short: str) -> str:
        if short in {"NS", "TBD", "SUS"}:
            return "scheduled"
        if short in {"1H", "2H", "HT", "ET", "BT", "P", "INT"}:
            return "in_play"
        if short in {"FT", "AET", "PEN"}:
            return "finished"
        if short in {"PST", "CANC"}:
            return "postponed"
        return "scheduled"

    def _fixture_to_match(self, f: dict) -> Match:
        fx = f.get("fixture", {})
        teams = f.get("teams", {})
        goals = f.get("goals") or {}
        home_g, away_g = goals.get("home"), goals.get("away")
        return Match(
            id=int(fx.get("id", 0)),
            round=f.get("league", {}).get("round", ""),
            date=datetime_iso(fx.get("date")),
            status=self._status(fx.get("status", {}).get("short", "")),
            home=self._team(teams.get("home", {})),
            away=self._team(teams.get("away", {})),
            score=Score(home=int(home_g) if home_g is not None else None,
                        away=int(away_g) if away_g is not None else None),
            source="api",
        )

    # ----------------------------------------------------------- data
    def _window_dates(self) -> list[str]:
        today = date.today()
        return [(today + timedelta(days=d)).isoformat() for d in (-1, 0, 1)]

    def _fetch_window(self) -> list[dict]:
        seen: dict[int, dict] = {}
        for day in self._window_dates():
            data = cached(15 * 60)(lambda _k, d=day: self._get("/fixtures", {"date": d}))(f"window:{day}")
            if not data or "response" not in data:
                continue
            for f in data["response"]:
                league = f.get("league", {})
                if int(league.get("id", 0)) != settings.league_id:
                    continue
                seen[int(f.get("fixture", {}).get("id", 0))] = f
        return list(seen.values())

    def _fetch_base_season(self) -> list[dict]:
        data = cached(12 * 3600)(
            lambda k: self._get("/fixtures", {"league": settings.league_id, "season": settings.base_season})
        )(f"fixtures:{settings.league_id}:{settings.base_season}")
        if not data or "response" not in data:
            return []
        return data["response"]

    def fixtures(self) -> list[Match]:
        return [self._fixture_to_match(f) for f in self._fetch_window()]

    def all_finished(self) -> list[Match]:
        return [self._fixture_to_match(f) for f in self._fetch_base_season()
                if f.get("fixture", {}).get("status", {}).get("short") in {"FT", "AET", "PEN"}]

    def upcoming(self, round_no: int | None = None) -> list[Match]:
        matches = [self._fixture_to_match(f) for f in self._fetch_window()
                   if self._status(f.get("fixture", {}).get("status", {}).get("short", "")) != "finished"]
        if round_no:
            matches = [m for m in matches if m.round and f"Rodada {round_no}" in m.round]
        return matches

    def match(self, match_id: int) -> Match | None:
        data = cached(15 * 60)(lambda _k, fid=match_id: self._get("/fixtures", {"id": fid}))(f"match:{match_id}")
        if not data or "response" not in data or not data["response"]:
            return None
        return self._fixture_to_match(data["response"][0])

    def standings(self) -> Standings | None:
        data = cached(12 * 3600)(
            lambda k: self._get("/standings", {"league": settings.league_id, "season": settings.base_season})
        )(f"standings:{settings.league_id}:{settings.base_season}")
        if not data or "response" not in data or not data["response"]:
            return None
        table = data["response"][0].get("league", {}).get("standings", [[]])[0]
        rows: list[StandingsEntry] = []
        for r in table:
            all_g = r.get("all", {})
            rows.append(
                StandingsEntry(
                    position=int(r.get("rank", 0)),
                    team=self._team(r.get("team", {})),
                    games=int(all_g.get("played", 0)),
                    wins=int(all_g.get("win", 0)),
                    draws=int(all_g.get("draw", 0)),
                    losses=int(all_g.get("lose", 0)),
                    goals_for=int(all_g.get("goals", {}).get("for", 0)),
                    goals_against=int(all_g.get("goals", {}).get("against", 0)),
                    points=int(r.get("points", 0)),
                    form=list(r.get("form", "")) if r.get("form") else [],
                )
            )
        return Standings(competition="Campeonato Brasileiro Serie A",
                         season=settings.base_season, rows=rows, source="api")

    def predictions(self, match_id: int) -> dict | None:
        data = cached(3600)(lambda _k, fid=match_id: self._get("/predictions", {"fixture": fid}))(f"predictions:{match_id}")
        if not data or "response" not in data or not data["response"]:
            return None
        top = data["response"][0]
        pred = top.get("predictions") or {}

        def pct(v: str | None) -> float:
            if not v:
                return 0.0
            try:
                return float(str(v).replace("%", "").strip())
            except ValueError:
                return 0.0

        percent = pred.get("percent") or {}
        ph, pd_, pa = pct(percent.get("home")), pct(percent.get("draw")), pct(percent.get("away"))
        if not (ph or pd_ or pa):
            # The free tier occasionally returns an empty/zero percent block;
            # treat it as "no provider reading" rather than a real prediction.
            return None
        h2h: list[dict] = []
        for m in top.get("h2h") or []:
            goals = m.get("goals") or {}
            teams = m.get("teams") or {}
            h2h.append({
                "date": (m.get("fixture") or {}).get("date"),
                "home": (teams.get("home") or {}).get("name", "?"),
                "away": (teams.get("away") or {}).get("name", "?"),
                "home_goals": goals.get("home"),
                "away_goals": goals.get("away"),
            })
        return {
            "percent": {
                "home_win": ph,
                "draw": pd_,
                "away_win": pa,
            },
            "comparison": top.get("comparison") or {},
            "h2h": h2h,
        }

    def team_issues(self, team_id: int) -> tuple[list[PlayerIssue] | None, list[PlayerIssue] | None]:
        # /players/injuries is unavailable on the free plan; returning None lets
        # the caller flag the gap honestly instead of fabricating names.
        return None, None

    def team_cards(self, team_id: int) -> tuple[float, float] | None:
        # /teams/statistics is behind the paid plan; returning None (without
        # spending a request on a blocked endpoint) lets the caller fall back
        # to an estimate (league average).
        return None


def datetime_iso(value: str | None) -> object:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
