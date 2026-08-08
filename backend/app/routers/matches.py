from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import Analysis, Match
from ..services.model import ProbabilityEngine
from ..services.provider import DataService

router = APIRouter(prefix="/api")

_ds = DataService()
_engine = ProbabilityEngine(_ds)


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
    rounds = sorted({f.round for f in fixtures if f.round}, key=lambda r: int(r.split()[-1]))
    current = _ds.upcoming()
    if not current:
        current = fixtures[:10]
    if round is not None:
        current = [m for m in current if m.round and m.round.split()[-1] == str(round)]
    sources = _ds.snapshot_sources()
    return {"matches": current, "rounds": rounds, "source": sources}


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
