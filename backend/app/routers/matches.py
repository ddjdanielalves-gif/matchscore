from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from ..schemas import Analysis, Match
from ..services.model import ProbabilityEngine
from ..services.provider import DataService

router = APIRouter(prefix="/api")

_ds = DataService()
_engine = ProbabilityEngine(_ds)


def _round_number(round_label: str) -> int | None:
    """Extracts the round number from labels like 'Regular Season - 15'.

    Returns None for labels with no trailing number (e.g. knockout-stage
    rounds like 'Final' or 'Semi-finals') instead of raising, so those
    rounds are simply excluded from numeric sorting/filtering rather than
    crashing the endpoint.
    """
    if not round_label:
        return None
    match = re.search(r"(\d+)\s*$", round_label.strip())
    return int(match.group(1)) if match else None


@router.get("/info")
def info():
    return {
        "name": "MatchScore",
        "description": "Analise probabilistica de partidas do futebol brasileiro.",
        "competition": "Campeonato Brasileiro Serie A",
        "disclaimer": (
            "As probabilidades sao estimativas estatisticas baseadas em dados "
            "historicos e atuais (forma, forca, lesoes, suspensoes, cartoes). "
            "Futebol e imprevisivel: o resultado de uma partida pode ser "
            "completamente aleatorio e divergir de qualquer estimativa. "
            "Esta ferramenta nao constitui recomendacao de aposta."
        ),
    }


@router.get("/matches")
def matches(round: int | None = None):
    fixtures = _ds.fixtures()

    # Only rounds with a parseable trailing number are offered for numeric
    # sorting/selection; knockout-stage labels (e.g. "Final") are skipped
    # here rather than crashing the endpoint.
    numbered_rounds = {f.round for f in fixtures if f.round and _round_number(f.round) is not None}
    rounds = sorted(numbered_rounds, key=_round_number)

    if round is not None:
        # Try the requested matchday of the current season first; fall back
        # to the current window and, finally, to the completed season so a
        # requested round still returns its matches instead of an empty list.
        current = _ds.upcoming(round)
        if not current:
            current = [m for m in fixtures if _round_number(m.round) == round]
        if not current:
            current = [m for m in _ds.all_finished() if _round_number(m.round) == round]
    else:
        current = _ds.upcoming()
        if not current:
            current = fixtures[:10]

    sources = _ds.snapshot_sources()
    return {"matches": current, "rounds": rounds, "source": sources}


@router.get("/results")
def results(days: int = 3):
    """Partidas finalizadas nos ultimos `days` dias (padrao: 3), mais recentes primeiro."""
    recent = _ds.recent_results(days=days)
    sources = _ds.snapshot_sources()
    return {"matches": recent, "days": days, "source": sources}


@router.get("/matches/{match_id}", response_model=Match)
def match(match_id: int):
    m = _ds.match(match_id)
    _ds.snapshot_sources()
    if m is None:
        raise HTTPException(status_code=404, detail="Partida nao encontrada")
    return m


@router.get("/matches/{match_id}/analysis", response_model=Analysis)
def analysis(match_id: int):
    m = _ds.match(match_id)
    if m is None:
        _ds.snapshot_sources()
        raise HTTPException(status_code=404, detail="Partida nao encontrada")
    result = _engine.analyze(m)
    if result is None:
        raise HTTPException(status_code=404, detail="Partida nao encontrada")
    return result


@router.get("/standings")
def standings():
    data = _ds.standings()
    sources = _ds.snapshot_sources()
    data.source = "api" if any(s.startswith("api") for s in sources) else "demo"
    return data
    
