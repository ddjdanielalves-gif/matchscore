export type Source = "api" | "demo"

export interface TeamRef {
  id: number
  name: string
  short_name: string
  crest: string
}

export interface Score {
  home: number | null
  away: number | null
}

export type MatchStatus = "scheduled" | "in_play" | "finished" | "postponed"

export interface Match {
  id: number
  competition: string
  round: string
  date: string
  status: MatchStatus
  home: TeamRef
  away: TeamRef
  score: Score
  source: Source
}

export interface MatchesResponse {
  matches: Match[]
  rounds: string[]
  source: string[]
}

export interface ResultsResponse {
  matches: Match[]
  days: number
  source: string[]
}

export interface PlayerIssue {
  player_id: number | null
  player: string
  position: string
  reason: string
  severity: number
}

export interface TeamContext {
  team: TeamRef
  position: number | null
  points: number | null
  elo: number
  form_last6: string[]
  avg_goals_for: number
  avg_goals_against: number
  avg_yellow_cards: number
  avg_red_cards: number
  injuries: PlayerIssue[]
  suspensions: PlayerIssue[]
}

export interface FactorContribution {
  key: string
  label: string
  detail: string
  home_shift: number
  away_shift: number
}

export interface Analysis {
  match: Match
  probabilities: { home_win: number; draw: number; away_win: number }
  expected_goals: { home: number; away: number }
  goals: {
    over_0_5: number
    under_0_5: number
    over_1_5: number
    under_1_5: number
    over_2_5: number
    under_2_5: number
    over_3_5: number
    under_3_5: number
    btts_yes: number
    btts_no: number
  }
  likely_score: { score: string; prob: number }
  home: TeamContext
  away: TeamContext
  factors: FactorContribution[]
  data_sources: string[]
  provider_prediction: ProviderPrediction | null
  source: Source
  generated_at: string
  disclaimer: string
}

export interface ProviderPrediction {
  percent: { home_win: number; draw: number; away_win: number }
  comparison: Record<string, { home: string; away: string }>
  h2h: {
    date: string
    home: string
    away: string
    home_goals: number | null
    away_goals: number | null
  }[]
}

export interface StandingsEntry {
  position: number
  team: TeamRef
  games: number
  wins: number
  draws: number
  losses: number
  goals_for: number
  goals_against: number
  points: number
  form: string[]
}

export interface Standings {
  competition: string
  season: number
  rows: StandingsEntry[]
  source: Source
}
