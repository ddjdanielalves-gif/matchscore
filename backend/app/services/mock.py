from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from urllib.parse import quote

from ..schemas import Match, PlayerIssue, Score, Standings, StandingsEntry, TeamRef

# Realistic-looking (but simulated) data for the Campeonato Brasileiro Serie A.
# Deterministic on a fixed seed so results are stable across restarts.

_TEAMS = [
    ("Flamengo", "FLA", "#C8102E", 88),
    ("Palmeiras", "PAL", "#046434", 87),
    ("Botafogo", "BOT", "#111111", 86),
    ("Internacional", "INT", "#C8102E", 84),
    ("Corinthians", "COR", "#1E1E1E", 84),
    ("Atletico-MG", "CAM", "#333333", 83),
    ("Sao Paulo", "SAO", "#C8102E", 83),
    ("Fortaleza", "FOR", "#0A3C8C", 82),
    ("Fluminense", "FLU", "#8F0D0D", 82),
    ("Gremio", "GRE", "#0E5FA8", 82),
    ("Cruzeiro", "CRU", "#003DA5", 81),
    ("Bahia", "BAH", "#0A62AC", 80),
    ("Vasco da Gama", "VAS", "#000000", 78),
    ("Athletico-PR", "CAP", "#C11F2F", 77),
    ("Red Bull Bragantino", "RBB", "#C2185B", 76),
    ("Santos", "SAN", "#7A7A7A", 76),
    ("Ceara", "CEA", "#1B1B1B", 74),
    ("Vitoria", "VIT", "#C1272D", 73),
    ("Juventude", "JUV", "#008641", 72),
    ("Sport Recife", "SPT", "#C70000", 72),
]

_FIRST = [
    "Gabriel", "Lucas", "Pedro", "Matheus", "Joao", "Rafael", "Bruno", "Diego",
    "Felipe", "Thiago", "Vinicius", "Gustavo", "Caio", "Igor", "Renan", "Douglas",
    "Alan", "Wesley", "Anderson", "Carlos", "Marcos", "Paulo", "Rodrigo", "Andre",
]
_LAST = [
    "Silva", "Santos", "Oliveira", "Souza", "Pereira", "Costa", "Almeida",
    "Ferreira", "Rodrigues", "Barbosa", "Rocha", "Carvalho", "Mendes", "Nunes",
    "Cardoso", "Lima", "Martins", "Ribeiro", "Gomes", "Araujo",
]
_POSITIONS = ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "ATT", "ATT"]
_INJURY_REASONS = [
    "Lesao muscular", "Torcao no tornozelo", "Estiramento na coxa",
    "Lesao no joelho", "Entorse", "Dores musculares", "Lesao no tornozelo",
    "Distensao posterior",
]
_SEVERITY = {"GK": 1.0, "DEF": 0.7, "MID": 0.5, "ATT": 0.9}


def _crest(short: str, color: str) -> str:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
        f'<rect width="64" height="64" rx="14" fill="{color}"/>'
        f'<text x="32" y="40" font-family="Arial" font-size="18" font-weight="bold" '
        f'fill="#fff" text-anchor="middle">{short}</text></svg>'
    )
    return "data:image/svg+xml," + quote(svg)


def _player_name(rng: random.Random) -> str:
    return f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"


class MockProvider:
    source = "demo"

    def __init__(self, current_round: int = 14) -> None:
        self._rng = random.Random(2026)
        self._team_map: dict[int, dict] = {}
        self._players: dict[int, list[str]] = {}
        for i, (name, short, color, strength) in enumerate(_TEAMS, start=1):
            self._team_map[i] = {
                "id": i, "name": name, "short": short, "color": color,
                "strength": strength, "crest": _crest(short, color),
            }
            self._players[i] = [_player_name(self._rng) for _ in range(18)]
        self.current_round = current_round
        self._matches = self._build_schedule()
        self._injuries, self._suspensions = self._build_issues()

    # ------------------------------------------------------------------ utils
    def team(self, team_id: int) -> TeamRef:
        t = self._team_map[team_id]
        return TeamRef(id=t["id"], name=t["name"], short_name=t["short"], crest=t["crest"])

    def _round_date(self, r: int) -> datetime:
        base = datetime(2026, 4, 5, 16, 0)
        days = (r - 1) * 7
        if r >= 12:
            days += 35  # pausa da Copa do Mundo
        return base + timedelta(days=days)

    def _build_schedule(self) -> list[Match]:
        rng = self._rng
        ids = list(self._team_map)
        n = len(ids)
        pairs_by_round: list[list[tuple[int, int]]] = []

        order = ids[:]
        rng.shuffle(order)
        for r in range(n - 1):
            pairs: list[tuple[int, int]] = []
            for i in range(n // 2):
                a, b = order[i], order[n - 1 - i]
                pairs.append((a, b) if r % 2 == 0 else (b, a))
            pairs_by_round.append(pairs)
            order = [order[0]] + [order[-1]] + order[1:-1]

        fixtures: list[Match] = []
        for half in range(2):
            for idx in range(n - 1):
                pairs = pairs_by_round[idx]
                if half == 1:  # return leg: invert home/away
                    pairs = [(b, a) for a, b in pairs]
                round_no = idx + 1 + half * (n - 1)
                date = self._round_date(round_no)
                for j, (home_id, away_id) in enumerate(pairs):
                    mid = round_no * 100 + j
                    finished = round_no < self.current_round
                    home, away = self._team_map[home_id], self._team_map[away_id]
                    score = None
                    if finished:
                        lambda_h = 1.35 * math.exp((home["strength"] - away["strength"]) / 15.0) * 1.18
                        lambda_a = 1.35 * math.exp((away["strength"] - home["strength"]) / 15.0) * 0.90
                        gh = ga = 0
                        for _ in range(10):
                            gh = self._poisson(lambda_h)
                            ga = self._poisson(lambda_a)
                            if gh + ga < 6:
                                break
                        score = Score(home=gh, away=ga)
                    fixtures.append(
                        Match(
                            id=mid,
                            round=f"Rodada {round_no}",
                            date=date,
                            status="finished" if finished else "scheduled",
                            home=self.team(home_id),
                            away=self.team(away_id),
                            score=score or Score(),
                        )
                    )
        return fixtures

    @staticmethod
    def _poisson(lambda_: float) -> int:
        limit = math.exp(-lambda_)
        k, p = 0, 1.0
        while True:
            p *= random.random()
            if p <= limit:
                return k
            k += 1

    def _build_issues(self) -> tuple[dict[int, list[PlayerIssue]], dict[int, list[PlayerIssue]]]:
        rng = random.Random(777)
        injuries: dict[int, list[PlayerIssue]] = {}
        suspensions: dict[int, list[PlayerIssue]] = {}
        for tid in self._team_map:
            inj = []
            for _ in range(rng.randint(1, 3)):
                name = rng.choice(self._players[tid])
                pos = rng.choice(_POSITIONS)
                inj.append(
                    PlayerIssue(
                        player_id=None,
                        player=name,
                        position=pos,
                        reason=rng.choice(_INJURY_REASONS),
                        severity=_SEVERITY[pos],
                    )
                )
            injuries[tid] = inj
            sus = []
            if rng.random() < 0.65:
                name = rng.choice(self._players[tid])
                pos = rng.choice(_POSITIONS)
                sus.append(
                    PlayerIssue(
                        player_id=None,
                        player=name,
                        position=pos,
                        reason=rng.choice(["Acumulo de cartoes amarelos", "Cartao vermelho"]),
                        severity=_SEVERITY[pos],
                    )
                )
            suspensions[tid] = sus
        return injuries, suspensions

    # ------------------------------------------------------------ provider api
    def all_finished(self) -> list[Match]:
        return [m for m in self._matches if m.status == "finished"]

    def fixtures(self) -> list[Match]:
        return self._matches

    def upcoming(self, round_no: int | None = None) -> list[Match]:
        matches = [m for m in self._matches if m.status != "finished"]
        if round_no:
            matches = [m for m in matches if f"Rodada {round_no}" == m.round]
        return matches

    def match(self, match_id: int) -> Match | None:
        return next((m for m in self._matches if m.id == match_id), None)

    def standings(self) -> Standings:
        results: dict[int, list[tuple[int, int, bool]]] = {t: [] for t in self._team_map}
        for m in self.all_finished():
            if m.score is None or m.score.home is None or m.score.away is None:
                continue
            results[m.home.id].append((m.score.home, m.score.away, True))
            results[m.away.id].append((m.score.away, m.score.home, False))
        rows: list[StandingsEntry] = []
        for tid, team in self._team_map.items():
            gf = sum(r[0] for r in results[tid])
            ga = sum(r[1] for r in results[tid])
            wins = sum(1 for r in results[tid] if r[0] > r[1])
            draws = sum(1 for r in results[tid] if r[0] == r[1])
            losses = sum(1 for r in results[tid] if r[0] < r[1])
            form = ["W" if r[0] > r[1] else ("D" if r[0] == r[1] else "L") for r in results[tid][-6:]][::-1]
            rows.append(
                StandingsEntry(
                    position=0,
                    team=self.team(tid),
                    games=len(results[tid]),
                    wins=wins, draws=draws, losses=losses,
                    goals_for=gf, goals_against=ga,
                    points=wins * 3 + draws,
                    form=form,
                )
            )
        rows.sort(key=lambda r: (r.points, r.goals_for - r.goals_against, r.goals_for), reverse=True)
        for i, r in enumerate(rows, start=1):
            r.position = i
        return Standings(competition="Campeonato Brasileiro Serie A", season=2026, rows=rows, source="demo")

    def team_issues(self, team_id: int) -> tuple[list[PlayerIssue], list[PlayerIssue]]:
        return self._injuries.get(team_id, []), self._suspensions.get(team_id, [])

    def predictions(self, match_id: int) -> dict | None:
        # Demo provider has no real prediction; the model runs pure on demo data.
        return None

    def team_cards(self, team_id: int) -> tuple[float, float]:
        rng = random.Random(team_id * 31)
        return round(rng.uniform(1.6, 2.6), 2), round(rng.uniform(0.0, 0.25), 2)
