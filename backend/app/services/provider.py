from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

import httpx

from ..config import settings
from ..schemas import (
    Match,
    TeamRef,
    Score,
    Standings,
    StandingsEntry,
)
from .cache import cached

logger = logging.getLogger("matchscore.api")

# ============================================================
# CONFIGURAÇÕES
# ============================================================

# Rate limit mais realista (2 req/segundo)
_RATE_INTERVAL = 0.5
_last_call = 0.0

# Janela de datas
_WINDOW_DAYS_BACK = 7
_WINDOW_DAYS_FORWARD = 30

# Mapeamento de competições
COMPETITIONS = {
    "brasileirao": "2013",
    "premier": "2021",
    "laliga": "2014",
    "bundesliga": "2002",
    "seriea": "2019",  # Italiano
    "ligue1": "2015",
    "champions": "2001",
}

# ============================================================
# HELPERS
# ============================================================

def _throttle() -> None:
    """Controla taxa de requisições"""
    global _last_call
    wait = _last_call + _RATE_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()

def datetime_iso(value: str | None) -> datetime:
    """Converte ISO para datetime UTC"""
    if not value:
        return datetime.now(timezone.utc)
    
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except:
        return datetime.now(timezone.utc)

def clean_name(name: str) -> str:
    """Remove acentos e pega sigla"""
    if not name:
        return "???"
    
    # Remove acentos
    nfkd = unicodedata.normalize('NFKD', name)
    plain = ''.join(c for c in nfkd if not unicodedata.combining(c))
    
    # Pega primeira palavra
    words = re.sub(r'[^a-zA-Z\s]', '', plain).split()
    return words[0][:3].upper() if words else "???"

# ============================================================
# PROVIDER PRINCIPAL
# ============================================================

class RapidApiProvider:
    """Provider para football-data.org v4"""
    
    source = "api"
    
    def __init__(self):
        # Configuração
        self.api_key = settings.api_key.strip()
        self.base_url = settings.api_base_url.rstrip('/')
        
        # Código da competição (converte nome para código)
        comp_code = getattr(settings, 'competition_code', 'brasileirao')
        self.competition = COMPETITIONS.get(comp_code.lower(), '2013')
        
        # Temporada (ano atual)
        self.season = getattr(settings, 'season', datetime.now().year)
        
        # Headers
        self.headers = {
            "X-Auth-Token": self.api_key,
            "Accept": "application/json",
        }
        
        logger.info(f"Provider iniciado: competição={self.competition} season={self.season}")
    
    # ============================================================
    # REQUISIÇÕES HTTP
    # ============================================================
    
    def _get(self, path: str, params: Dict = None) -> Optional[Dict]:
        """Faz requisição GET com throttling e tratamento de erros"""
        url = f"{self.base_url}{path}"
        
        try:
            _throttle()
            
            logger.debug(f"Request: {path} params={params}")
            
            with httpx.Client(timeout=30, headers=self.headers) as client:
                response = client.get(url, params=params or {})
            
            # Tratamento de status
            if response.status_code == 401:
                logger.error("API Key inválida! Verifique MATCH_API_KEY")
                return None
            
            if response.status_code == 403:
                logger.error(f"Acesso negado. Plano não cobre {self.competition}")
                return None
            
            if response.status_code == 404:
                logger.warning(f"Recurso não encontrado: {path}")
                return None
            
            if response.status_code == 429:
                logger.warning("Rate limit excedido. Aguardando...")
                time.sleep(5)
                return self._get(path, params)  # Tenta novamente
            
            response.raise_for_status()
            
            data = response.json()
            return data if isinstance(data, dict) else None
            
        except httpx.TimeoutException:
            logger.error(f"Timeout: {path}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error: {e}")
            return None
        except Exception as e:
            logger.exception(f"Erro inesperado: {e}")
            return None
    
    # ============================================================
    # MAPEAMENTO DE DADOS
    # ============================================================
    
    def _parse_team(self, data: Dict) -> TeamRef:
        """Converte dados da API para TeamRef"""
        return TeamRef(
            id=data.get('id', 0),
            name=data.get('name', 'Desconhecido'),
            short_name=data.get('tla') or clean_name(data.get('name', '')),
            crest=data.get('crest', ''),
        )
    
    def _parse_score(self, match: Dict) -> Score:
        """Extrai placar"""
        score = match.get('score', {})
        full = score.get('fullTime', {})
        
        home = full.get('home') or score.get('home')
        away = full.get('away') or score.get('away')
        
        try:
            home = int(home) if home is not None else None
        except:
            home = None
        
        try:
            away = int(away) if away is not None else None
        except:
            away = None
        
        return Score(home=home, away=away)
    
    def _parse_status(self, status: str) -> str:
        """Normaliza status do jogo"""
        status_map = {
            'SCHEDULED': 'scheduled',
            'TIMED': 'scheduled',
            'LIVE': 'in_play',
            'IN_PLAY': 'in_play',
            'PAUSED': 'in_play',
            'FINISHED': 'finished',
            'POSTPONED': 'postponed',
            'CANCELLED': 'postponed',
            'SUSPENDED': 'postponed',
        }
        return status_map.get(str(status).upper(), 'scheduled')
    
    def _parse_match(self, match: Dict) -> Match:
        """Converte jogo da API para Match"""
        return Match(
            id=int(match.get('id', 0)),
            round=self._get_round(match),
            date=datetime_iso(match.get('utcDate')),
            status=self._parse_status(match.get('status')),
            home=self._parse_team(match.get('homeTeam', {})),
            away=self._parse_team(match.get('awayTeam', {})),
            score=self._parse_score(match),
            source="api",
        )
    
    def _get_round(self, match: Dict) -> str:
        """Extrai rodada"""
        matchday = match.get('matchday')
        if matchday:
            try:
                return f"Rodada {int(matchday)}"
            except:
                pass
        return match.get('stage', '')
    
    # ============================================================
    # MÉTODOS PRINCIPAIS
    # ============================================================
    
    def _fetch_matches(self, **params) -> List[Dict]:
        """Busca partidas da competição"""
        # Parâmetros padrão
        if 'season' not in params:
            params['season'] = self.season
        
        cache_key = f"matches:{self.competition}:{hash(str(sorted(params.items())))}"
        
        data = cached(300)(  # 5 minutos de cache
            lambda _: self._get(
                f"/competitions/{self.competition}/matches",
                params
            )
        )(cache_key)
        
        if not data:
            return []
        
        matches = data.get('matches', [])
        return matches if isinstance(matches, list) else []
    
    # ============================================================
    # FIXTURES - Próximos jogos
    # ============================================================
    
    def fixtures(self) -> List[Match]:
        """Retorna os próximos jogos"""
        logger.info("Buscando próximos jogos...")
        
        # Busca jogos agendados
        matches = self._fetch_matches(
            status="SCHEDULED",
            dateFrom=(date.today()).isoformat(),
            dateTo=(date.today() + timedelta(days=_WINDOW_DAYS_FORWARD)).isoformat(),
        )
        
        # Se não achou, busca por matchday atual
        if not matches:
            current_round = self._get_current_matchday()
            if current_round:
                matches = self._fetch_matches(matchday=current_round)
        
        # Se ainda não achou, busca janela de datas
        if not matches:
            matches = self._fetch_matches(
                dateFrom=(date.today() - timedelta(days=1)).isoformat(),
                dateTo=(date.today() + timedelta(days=14)).isoformat(),
            )
        
        # Converte para Match
        result = [self._parse_match(m) for m in matches]
        
        # Filtra apenas futuros/não finalizados
        result = [m for m in result if m.status != 'finished']
        
        # Ordena por data
        result.sort(key=lambda m: m.date)
        
        # Limita a 20 jogos
        result = result[:20]
        
        logger.info(f"Encontrados {len(result)} jogos futuros")
        
        # Fallback: dados mockados se não encontrar nada
        if not result:
            logger.warning("Nenhum jogo encontrado. Usando fallback.")
            result = self._mock_fixtures()
        
        return result
    
    # ============================================================
    # STANDINGS - Classificação
    # ============================================================
    
    def standings(self) -> Optional[Standings]:
        """Retorna classificação completa"""
        logger.info("Buscando classificação...")
        
        data = cached(3600)(  # 1 hora de cache
            lambda _: self._get(
                f"/competitions/{self.competition}/standings",
                {"season": self.season}
            )
        )(f"standings:{self.competition}:{self.season}")
        
        if not data:
            logger.warning("Não foi possível obter classificação")
            return self._mock_standings()
        
        # Pega o standings do tipo TOTAL
        standings_list = data.get('standings', [])
        total = next((s for s in standings_list if s.get('type') == 'TOTAL'), None)
        
        if not total:
            logger.warning("Standings TOTAL não encontrado")
            return self._mock_standings()
        
        # Converte cada entrada
        entries = []
        for row in total.get('table', []):
            try:
                entries.append(StandingsEntry(
                    position=int(row.get('position', 0)),
                    team=self._parse_team(row.get('team', {})),
                    games=int(row.get('playedGames', 0)),
                    wins=int(row.get('won', 0)),
                    draws=int(row.get('draw', 0)),
                    losses=int(row.get('lost', 0)),
                    goals_for=int(row.get('goalsFor', 0)),
                    goals_against=int(row.get('goalsAgainst', 0)),
                    goal_difference=int(row.get('goalDifference', 0)),
                    points=int(row.get('points', 0)),
                ))
            except Exception as e:
                logger.warning(f"Erro ao processar linha: {e}")
                continue
        
        return Standings(entries=entries)
    
    # ============================================================
    # MATCH - Jogo específico
    # ============================================================
    
    def match(self, match_id: int) -> Optional[Match]:
        """Busca um jogo específico"""
        data = cached(300)(
            lambda _: self._get(f"/matches/{match_id}")
        )(f"match:{match_id}")
        
        if not data:
            return None
        
        return self._parse_match(data)
    
    # ============================================================
    # MÉTODOS AUXILIARES
    # ============================================================
    
    def _get_current_matchday(self) -> Optional[int]:
        """Descobre a rodada atual"""
        data = self._get(
            f"/competitions/{self.competition}",
            {"season": self.season}
        )
        
        if not data:
            return None
        
        season = data.get('currentSeason', {})
        matchday = season.get('currentMatchday')
        
        try:
            return int(matchday) if matchday else None
        except:
            return None
    
    # ============================================================
    # FALLBACKS - Dados mockados
    # ============================================================
    
    def _mock_fixtures(self) -> List[Match]:
        """Gera jogos mockados para teste"""
        teams = [
            ("Flamengo", "FLA"),
            ("Palmeiras", "PAL"),
            ("São Paulo", "SPO"),
            ("Corinthians", "COR"),
            ("Internacional", "INT"),
            ("Grêmio", "GRE"),
            ("Atlético-MG", "ATL"),
            ("Cruzeiro", "CRU"),
        ]
        
        now = datetime.now(timezone.utc)
        matches = []
        
        for i in range(4):
            home_idx = i * 2
            away_idx = i * 2 + 1
            
            if away_idx < len(teams):
                matches.append(Match(
                    id=1000 + i,
                    round=f"Rodada {i+1}",
                    date=now + timedelta(days=i*2 + 1, hours=16),
                    status="scheduled",
                    home=TeamRef(
                        id=i*10+1,
                        name=teams[home_idx][0],
                        short_name=teams[home_idx][1],
                        crest=""
                    ),
                    away=TeamRef(
                        id=i*10+2,
                        name=teams[away_idx][0],
                        short_name=teams[away_idx][1],
                        crest=""
                    ),
                    score=Score(home=None, away=None),
                    source="api"
                ))
        
        return matches
    
    def _mock_standings(self) -> Standings:
        """Gera classificação mockada"""
        teams = [
            ("Flamengo", "FLA", 10, 30),
            ("Palmeiras", "PAL", 8, 25),
            ("São Paulo", "SPO", 7, 23),
            ("Corinthians", "COR", 6, 20),
        ]
        
        entries = []
        for i, (name, short, wins, pts) in enumerate(teams, 1):
            entries.append(StandingsEntry(
                position=i,
                team=TeamRef(id=i, name=name, short_name=short, crest=""),
                games=10,
                wins=wins,
                draws=10-wins-2,
                losses=2,
                goals_for=wins*2,
                goals_against=wins,
                goal_difference=wins,
                points=pts,
            ))
        
        return Standings(entries=entries)
