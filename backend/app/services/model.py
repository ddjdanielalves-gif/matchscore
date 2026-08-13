from __future__ import annotations

import math
from datetime import datetime

from ..schemas import Analysis, FactorContribution, Match, Standings, TeamContext
from .provider import DataService

_GOALS_MAX = 12
_HOME_ADV_ELO = 100.0
_ELO_K = 32.0


# ---------------------------------------------------------------- helpers
def poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def probabilities(lh: float, la: float) -> dict[str, float]:
    home = draw = away = 0.0
    for x in range(_GOALS_MAX + 1):
        for y in range(_GOALS_MAX + 1):
            p = poisson_pmf(x, lh) * poisson_pmf(y, la)
            if x > y:
                home += p
            elif x == y:
                draw += p
            else:
                away += p
    total = home + draw + away or 1.0
    return {
        "home_win": round(home / total * 100, 1),
        "draw": round(draw / total * 100, 1),
        "away_win": round(away / total * 100, 1),
    }


def goals_stats(lh: float, la: float) -> dict[str, float]:
    """Over/under totals and BTTS, derived from the same Poisson model."""
    total_grid: dict[float, float] = {}

    def prob_total(total: float) -> float:
        if total not in total_grid:
            p = sum(
                poisson_pmf(x, lh) * poisson_pmf(y, la)
                for x in range(_GOALS_MAX + 1)
                for y in range(_GOALS_MAX + 1)
                if x + y > total
            )
            total_grid[total] = min(100.0, p * 100)
        return total_grid[total]

    both_teams = (1 - poisson_pmf(0, lh)) * (1 - poisson_pmf(0, la))
    return {
        "over_0_5": round(prob_total(0.5), 1),
        "under_0_5": round(100.0 - prob_total(0.5), 1),
        "over_1_5": round(prob_total(1.5), 1),
        "under_1_5": round(100.0 - prob_total(1.5), 1),
        "over_2_5": round(prob_total(2.5), 1),
        "under_2_5": round(100.0 - prob_total(2.5), 1),
        "over_3_5": round(prob_total(3.5), 1),
        "under_3_5": round(100.0 - prob_total(3.5), 1),
        "btts_yes": round(min(100.0, both_teams * 100), 1),
        "btts_no": round(min(100.0, (1 - both_teams) * 100), 1),
    }


def likely_score(lh: float, la: float) -> dict[str, str | float]:
    best, bp = (0, 0), -1.0
    for x in range(_GOALS_MAX + 1):
        for y in range(_GOALS_MAX + 1):
            p = poisson_pmf(x, lh) * poisson_pmf(y, la)
            if p > bp:
                best, bp = (x, y), p
    return {"score": f"{best[0]}-{best[1]}", "prob": round(bp * 100, 1)}


def compute_elos(finished: list[Match]) -> dict[int, float]:
    elo: dict[int, float] = {}
    for m in sorted(finished, key=lambda x: x.date):
        if m.score is None or m.score.home is None or m.score.away is None:
            continue
        r_home = elo.get(m.home.id, 1500.0)
        r_away = elo.get(m.away.id, 1500.0)
        exp_home = 1 / (1 + 10 ** ((r_away - (r_home + _HOME_ADV_ELO)) / 400))
        s_home = 1.0 if m.score.home > m.score.away else (0.5 if m.score.home == m.score.away else 0.0)
        elo[m.home.id] = r_home + _ELO_K * (s_home - exp_home)
        elo[m.away.id] = r_away + _ELO_K * ((1 - s_home) - (1 - exp_home))
    return elo


def form_score(form: list[str]) -> float:
    if not form:
        return 0.0
    weights = [1.0, 0.8, 0.6, 0.4, 0.2, 0.1][: len(form)]
    score = sum(w * (1.0 if r == "W" else (-1.0 if r == "L" else 0.0)) for w, r in zip(weights, form))
    return score / sum(weights)


def fmt_form(form: list[str]) -> str:
    return "-".join(form[-5:]) if form else "-"


def league_averages(finished: list[Match]) -> dict[str, float]:
    n = len(finished)
    if n == 0:
        return {"home": 1.35, "away": 1.15, "team": 1.25, "yellow": 2.0}
    total_h = sum(m.score.home for m in finished if m.score and m.score.home is not None)
    total_a = sum(m.score.away for m in finished if m.score and m.score.away is not None)
    home = total_h / n
    away = total_a / n
    return {"home": home, "away": away, "team": (total_h + total_a) / (2 * n), "yellow": 2.0}


def team_stats(finished: list[Match], team_id: int) -> tuple[list[str], float, float]:
    gf = ga = 0
    games = 0
    form: list[tuple[datetime, str]] = []
    for m in finished:
        if m.score is None or m.score.home is None or m.score.away is None:
            continue
        if m.home.id == team_id:
            games += 1
            gf += m.score.home
            ga += m.score.away
            form.append((m.date, "W" if m.score.home > m.score.away else ("D" if m.score.home == m.score.away else "L")))
        elif m.away.id == team_id:
            games += 1
            gf += m.score.away
            ga += m.score.home
            form.append((m.date, "W" if m.score.away > m.score.home else ("D" if m.score.away == m.score.home else "L")))
    form.sort(key=lambda x: x[0], reverse=True)
    seq = [r for _, r in form][:6]
    games = games or 1
    return seq, gf / games, ga / games


# ---------------------------------------------------------------- engine
class ProbabilityEngine:
    def __init__(self, ds: DataService) -> None:
        self.ds = ds

    def build_context(
        self,
        team: Match,
        finished: list[Match],
        standings: Standings,
        elos: dict[int, float],
        avg: dict[str, float],
        is_home: bool,
    ) -> TeamContext:
        tid = team.home.id if is_home else team.away.id
        seq, avg_gf, avg_ga = team_stats(finished, tid)
        row = next((r for r in standings.rows if r.team.id == tid), None)
        injuries, suspensions = self.ds.team_issues(tid)
        yellow, red = self.ds.team_cards(tid)
        ref = team.home if is_home else team.away
        return TeamContext(
            team=ref,
            position=row.position if row else None,
            points=row.points if row else None,
            elo=elos.get(tid, 1500.0),
            form_last6=seq,
            avg_goals_for=avg_gf,
            avg_goals_against=avg_ga,
            avg_yellow_cards=yellow,
            avg_red_cards=red,
            injuries=injuries,
            suspensions=suspensions,
        )

    @staticmethod
    def _own_mult(issues: list, weight: float) -> float:
        impact = sum(i.severity for i in issues)
        return 1 / (1 + weight * impact)

    def lambdas(self, home: TeamContext, away: TeamContext, avg: dict[str, float],
                neutral: set[str] | None = None) -> tuple[float, float]:
        neutral = neutral or set()

        attack_h = home.avg_goals_for / avg["team"]
        defense_a = away.avg_goals_against / avg["team"]
        attack_a = away.avg_goals_for / avg["team"]
        defense_h = home.avg_goals_against / avg["team"]

        lh_stats = avg["home"] * attack_h * defense_a
        la_stats = avg["away"] * attack_a * defense_h

        if "elo" not in neutral:
            lh_elo = avg["home"] * math.exp((home.elo + _HOME_ADV_ELO - away.elo) / 600)
            la_elo = avg["away"] * math.exp((away.elo - home.elo - _HOME_ADV_ELO) / 600)
            lh = 0.6 * lh_stats + 0.4 * lh_elo
            la = 0.6 * la_stats + 0.4 * la_elo
        else:
            lh, la = lh_stats, la_stats

        ha = 1.08 if "home_advantage" not in neutral else 1.0
        lh *= ha

        fm_h = 1 + 0.12 * form_score(home.form_last6) if "form" not in neutral else 1.0
        fm_a = 1 + 0.12 * form_score(away.form_last6) if "form" not in neutral else 1.0
        ih = self._own_mult(home.injuries, 0.22) if "injuries" not in neutral else 1.0
        ia = self._own_mult(away.injuries, 0.22) if "injuries" not in neutral else 1.0
        sh = self._own_mult(home.suspensions, 0.18) if "suspensions" not in neutral else 1.0
        sa = self._own_mult(away.suspensions, 0.18) if "suspensions" not in neutral else 1.0

        ch = 1 - 0.04 * (home.avg_yellow_cards - avg["yellow"])
        ca = 1 - 0.04 * (away.avg_yellow_cards - avg["yellow"])
        ch = min(1.12, max(0.85, ch)) if "cards" not in neutral else 1.0
        ca = min(1.12, max(0.85, ca)) if "cards" not in neutral else 1.0

        ph = 1 + 0.004 * (10.5 - (home.position or 10.5)) if "standings" not in neutral else 1.0
        pa = 1 + 0.004 * (10.5 - (away.position or 10.5)) if "standings" not in neutral else 1.0
        ph = min(1.1, max(0.9, ph))
        pa = min(1.1, max(0.9, pa))

        return max(0.05, lh * fm_h * ih * sh * ch * ph), max(0.05, la * fm_a * ia * sa * ca * pa)

    def analyze(self, match: Match) -> Analysis | None:
        finished = self.ds.all_finished()
        standings = self.ds.standings()
        elos = compute_elos(finished)
        avg = league_averages(finished)

        home = self.build_context(match, finished, standings, elos, avg, is_home=True)
        away = self.build_context(match, finished, standings, elos, avg, is_home=False)

        lh, la = self.lambdas(home, away, avg)
        probs_all = probabilities(lh, la)
        goals = goals_stats(lh, la)
        score = likely_score(lh, la)

        provider_pred = self.ds.predictions(match.id)
        blended = probs_all
        if provider_pred and provider_pred.get("percent"):
            pred = provider_pred["percent"]
            ph, pd_, pa = pred.get("home_win", 0.0), pred.get("draw", 0.0), pred.get("away_win", 0.0)
            if ph or pd_ or pa:
                # Our model leans on the previous full season; the provider's
                # reading is current, so it carries more weight.
                blended = self._blend(probs_all, {"home_win": ph, "draw": pd_, "away_win": pa})

        factors = self._factor_breakdown(home, away, avg, probs_all)
        sources = self.ds.snapshot_sources()
        if provider_pred:
            sources.append("previsao real combinada com o modelo")
        source = "api" if any(s.startswith("api") for s in sources) else "demo"
        if not sources:
            sources = ["demo"]

        match.source = source
        return Analysis(
            match=match,
            probabilities=blended,
            expected_goals={"home": round(lh, 2), "away": round(la, 2)},
            goals=goals,
            likely_score=score,
            home=home,
            away=away,
            factors=factors,
            data_sources=sources,
            provider_prediction=provider_pred,
            source=source,
        )

    @staticmethod
    def _blend(model: dict[str, float], provider: dict[str, float], weight: float = 0.55) -> dict[str, float]:
        out = {
            "home_win": (1 - weight) * model["home_win"] + weight * provider["home_win"],
            "draw": (1 - weight) * model["draw"] + weight * provider["draw"],
            "away_win": (1 - weight) * model["away_win"] + weight * provider["away_win"],
        }
        total = sum(out.values()) or 1.0
        return {k: round(v / total * 100, 1) for k, v in out.items()}

    def _factor_breakdown(self, home: TeamContext, away: TeamContext, avg: dict[str, float],
                          probs_all: dict[str, float]) -> list[FactorContribution]:
        def delta_for(key: str, label: str, detail: str) -> FactorContribution:
            lh, la = self.lambdas(home, away, avg, neutral={key})
            probs_n = probabilities(lh, la)
            return FactorContribution(
                key=key,
                label=label,
                detail=detail,
                home_shift=round(probs_all["home_win"] - probs_n["home_win"], 1),
                away_shift=round(probs_all["away_win"] - probs_n["away_win"], 1),
            )

        return [
            delta_for(
                "home_advantage",
                "Mando de campo",
                "Vantagem tradicional do mandante no Brasileirao.",
            ),
            delta_for(
                "elo",
                "Forca ELO",
                f"{home.team.short_name} {home.elo:.0f} vs {away.team.short_name} {away.elo:.0f}. "
                "Atualizado com os resultados reais disponiveis.",
            ),
            delta_for(
                "form",
                "Forma recente",
                f"{home.team.short_name} {fmt_form(home.form_last6)} vs "
                f"{away.team.short_name} {fmt_form(away.form_last6)} (ultimos jogos).",
            ),
            delta_for(
                "injuries",
                "Lesoes",
                f"{home.team.short_name}: {len(home.injuries)} desfalque(s) | "
                f"{away.team.short_name}: {len(away.injuries)} desfalque(s).",
            ),
            delta_for(
                "suspensions",
                "Suspensoes",
                f"{home.team.short_name}: {len(home.suspensions)} suspenso(s) | "
                f"{away.team.short_name}: {len(away.suspensions)} suspenso(s).",
            ),
            delta_for(
                "cards",
                "Cartoes",
                f"Media de cartoes: {home.team.short_name} {home.avg_yellow_cards:.1f}/jogo, "
                f"{away.team.short_name} {away.avg_yellow_cards:.1f}/jogo.",
            ),
            delta_for(
                "standings",
                "Posicao na tabela",
                f"{home.team.short_name} #{home.position or '-'} vs "
                f"{away.team.short_name} #{away.position or '-'}.",
            ),
        ]
