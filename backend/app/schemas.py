from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TeamRef(BaseModel):
    id: int
    name: str
    short_name: str = ""
    crest: str = ""


class Score(BaseModel):
    home: int | None = None
    away: int | None = None


class Match(BaseModel):
    id: int
    competition: str = "Campeonato Brasileiro Serie A"
    round: str = ""
    date: datetime
    status: Literal["scheduled", "in_play", "finished", "postponed"] = "scheduled"
    home: TeamRef
    away: TeamRef
    score: Score = Field(default_factory=Score)
    source: Literal["api", "demo"] = "demo"


class PlayerIssue(BaseModel):
    player_id: int | None = None
    player: str
    position: str = "?"  # GK / DEF / MID / ATT / ?
    reason: str
    severity: float = 1.0


class TeamContext(BaseModel):
    team: TeamRef
    position: int | None = None
    points: int | None = None
    elo: float = 1500.0
    form_last6: list[str] = Field(default_factory=list)  # "W"/"D"/"L"
    avg_goals_for: float = 1.3
    avg_goals_against: float = 1.2
    avg_yellow_cards: float = 2.0
    avg_red_cards: float = 0.1
    injuries: list[PlayerIssue] = Field(default_factory=list)
    suspensions: list[PlayerIssue] = Field(default_factory=list)


class FactorContribution(BaseModel):
    key: str
    label: str
    detail: str
    home_shift: float  # percentage-point shift on home win prob
    away_shift: float  # percentage-point shift on away win prob


class Analysis(BaseModel):
    match: Match
    probabilities: dict[str, float]  # home_win / draw / away_win
    expected_goals: dict[str, float]  # home / away
    home: TeamContext
    away: TeamContext
    factors: list[FactorContribution] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    # Real percentages from api-football /predictions (when available), so the
    # UI can show our blended estimate next to the provider's own reading.
    provider_prediction: dict | None = None
    source: Literal["api", "demo"] = "demo"
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    disclaimer: str = (
        "Estimativa estatistica, nao uma previsao garantida. Futebol e imprevisivel "
        "e o resultado pode ser completamente aleatorio. Nao constitui recomendacao "
        "de aposta."
    )


class StandingsEntry(BaseModel):
    position: int
    team: TeamRef
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0
    form: list[str] = Field(default_factory=list)


class Standings(BaseModel):
    competition: str
    season: int
    rows: list[StandingsEntry]
    source: Literal["api", "demo"] = "demo"
