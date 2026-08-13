import { useCallback, useEffect, useState } from "react"
import { fetchAnalysis, fetchMatches, fetchResults, fetchStandings } from "./api"
import type { Analysis, Match, Standings } from "./types"
import Disclaimer from "./components/Disclaimer"
import MatchCard from "./components/MatchCard"
import AnalysisView from "./components/AnalysisView"
import StandingsTable from "./components/StandingsTable"
import SourceBadge from "./components/SourceBadge"

type Tab = "jogos" | "tabela"

function roundNumber(round: string): number {
  return Number(round.split(" ").pop()) || 0
}

export default function App() {
  const [tab, setTab] = useState<Tab>("jogos")
  const [rounds, setRounds] = useState<string[]>([])
  const [round, setRound] = useState<string | null>(null)
  const [matches, setMatches] = useState<Match[]>([])
  const [results, setResults] = useState<Match[]>([])
  const [sources, setSources] = useState<string[]>([])
  const [selected, setSelected] = useState<Match | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [standings, setStandings] = useState<Standings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const loadMatches = useCallback(async (roundLabel: string | null) => {
    setLoading(true)
    setError("")
    try {
      const data = await fetchMatches(
        roundLabel ? roundNumber(roundLabel) : undefined,
      )
      setRounds(data.rounds)
      setSources((prev) => [...prev, ...data.source])
      setMatches(data.matches)
    } catch (e) {
      setError("Não foi possível carregar os jogos.")
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadResults = useCallback(async () => {
    try {
      const data = await fetchResults(3)
      setResults(data.matches)
      setSources((prev) => [...prev, ...data.source])
    } catch (e) {
      console.error("Não foi possível carregar os resultados recentes.", e)
    }
  }, [])

  useEffect(() => {
    void loadMatches(null)
    void loadResults()
  }, [loadMatches, loadResults])

  const loadStandings = useCallback(async () => {
    if (standings) return
    try {
      const data = await fetchStandings()
      setStandings(data)
    } catch (e) {
      setError("Não foi possível carregar a tabela.")
      console.error(e)
    }
  }, [standings])

  const openMatch = useCallback(async (match: Match) => {
    setSelected(match)
    setAnalysis(null)
    try {
      const data = await fetchAnalysis(match.id)
      setAnalysis(data)
      setSources(data.data_sources)
    } catch (e) {
      setError("Não foi possível gerar a análise.")
      console.error(e)
    }
    window.scrollTo({ top: 0, behavior: "smooth" })
  }, [])

  const back = useCallback(() => {
    setSelected(null)
    setAnalysis(null)
  }, [])

  const switchTab = useCallback((t: Tab) => {
    setTab(t)
    if (t === "tabela") void loadStandings()
  }, [loadStandings])

  const upcoming = matches
    .filter((m) => m.status !== "finished")
    .sort((a, b) => a.date.localeCompare(b.date))

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="brand">
            <img className="brand-ball" src="/logo.jpg" alt="MatchScore" />
            <h1>MatchScore</h1>
            <span className="brand-sub">Brasileirão Série A</span>
          </div>
          <nav className="tabs">
            <button
              type="button"
              className={`tab ${tab === "jogos" ? "tab-active" : ""}`}
              onClick={() => switchTab("jogos")}
            >
              Jogos
            </button>
            <button
              type="button"
              className={`tab ${tab === "tabela" ? "tab-active" : ""}`}
              onClick={() => switchTab("tabela")}
            >
              Tabela
            </button>
          </nav>
        </div>
      </header>

      <Disclaimer />

      <main className="main">
        {error && <div className="error-box">{error}</div>}

        {tab === "jogos" && !selected && (
          <>
            <div className="list-head">
              <h2>Próximos jogos</h2>
              <SourceBadge sources={sources} />
            </div>
            {rounds.length > 0 && (
              <div className="round-picker">
                <button
                  type="button"
                  className={`round-chip ${round === null ? "round-chip-active" : ""}`}
                  onClick={() => {
                    setRound(null)
                    void loadMatches(null)
                  }}
                >
                  Todos
                </button>
                {rounds.map((r) => (
                  <button
                    key={r}
                    type="button"
                    className={`round-chip ${round === r ? "round-chip-active" : ""}`}
                    onClick={() => {
                      setRound(r)
                      void loadMatches(r)
                    }}
                  >
                    {r.replace("Rodada", "Rod.")}
                  </button>
                ))}
              </div>
            )}
            {loading ? (
              <div className="loading">Carregando jogos…</div>
            ) : (
              <>
                {upcoming.length > 0 && (
                  <div className="list-section">
                    <h3 className="section-title">Próximos jogos</h3>
                    <div className="match-grid">
                      {upcoming.map((m) => (
                        <MatchCard
                          key={m.id}
                          match={m}
                          selected={false}
                          onSelect={() => void openMatch(m)}
                        />
                      ))}
                    </div>
                  </div>
                )}
                {results.length > 0 && (
                  <div className="list-section">
                    <h3 className="section-title">
                      Resultados recentes (últimos 3 dias)
                    </h3>
                    <div className="match-grid">
                      {results.map((m) => (
                        <MatchCard
                          key={m.id}
                          match={m}
                          selected={false}
                          onSelect={() => void openMatch(m)}
                        />
                      ))}
                    </div>
                  </div>
                )}
                {upcoming.length === 0 && results.length === 0 && (
                  <div className="loading">Nenhum jogo neste período.</div>
                )}
              </>
            )}
          </>
        )}

        {tab === "jogos" && selected && (
          <>
            <button type="button" className="back-btn" onClick={back}>
              ← Voltar para jogos
            </button>
            {analysis ? (
              <AnalysisView analysis={analysis} />
            ) : (
              <div className="loading">Calculando probabilidades…</div>
            )}
          </>
        )}

        {tab === "tabela" && (
          standings ? <StandingsTable standings={standings} /> : <div className="loading">Carregando tabela…</div>
        )}
      </main>

      <footer className="footer">
        <p>
          MatchScore é uma ferramenta educacional/experimental. Os resultados
          apresentados são estimativas e não garantias de resultado.
        </p>
      </footer>
    </div>
  )
}
