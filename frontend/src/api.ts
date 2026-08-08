import type { Analysis, MatchesResponse, Standings } from "./types"

// Absolute backend URL for the mobile (Capacitor) build; empty means the API
// is served from the same origin (web deploy / local dev).
const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? ""

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`Erro ${res.status} em ${path}`)
  return res.json() as Promise<T>
}

export function fetchMatches(round?: number): Promise<MatchesResponse> {
  const q = round ? `?round=${round}` : ""
  return get<MatchesResponse>(`/api/matches${q}`)
}

export function fetchAnalysis(matchId: number): Promise<Analysis> {
  return get<Analysis>(`/api/matches/${matchId}/analysis`)
}

export function fetchStandings(): Promise<Standings> {
  return get<Standings>("/api/standings")
}

export function fetchInfo(): Promise<{ disclaimer: string; competition: string }> {
  return get<{ disclaimer: string; competition: string }>("/api/info")
}
