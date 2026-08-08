import type { Analysis } from "../types"
import ProbabilityBar from "./ProbabilityBar"
import SourceBadge from "./SourceBadge"
import TeamPanel from "./TeamPanel"

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function Shift({ value, side }: { value: number; side: "home" | "away" }) {
  const pos = value > 0
  const neg = value < 0
  return (
    <span className={`shift ${pos ? "shift-up" : neg ? "shift-down" : "shift-zero"}`}>
      {value > 0 ? "+" : ""}
      {value.toFixed(1)}pp {side === "home" ? "casa" : "fora"}
    </span>
  )
}

function shiftPct(v: string | undefined): number | null {
  if (v == null) return null
  const n = parseFloat(String(v).replace("%", "").trim())
  return Number.isFinite(n) ? n : null
}

export default function AnalysisView({ analysis }: { analysis: Analysis }) {
  const { match, home, away } = analysis
  const provider = analysis.provider_prediction
  const compLabels: Record<string, string> = {
    form: "Forma recente",
    att: "Ataque",
    def: "Defesa",
    h2h: "Historico H2H",
    goals: "Gols",
    total: "Total",
  }
  return (
    <div className="analysis">
      <div className="analysis-head">
        <h2>
          {match.home.name} <span className="vs-x">vs</span> {match.away.name}
        </h2>
        <div className="analysis-sub">
          <span>{match.round}</span>
          <span>·</span>
          <span>{fmtDate(match.date)}</span>
        </div>
        <SourceBadge sources={analysis.data_sources} />
      </div>

      <section className="card">
        <h4>Probabilidade de resultado</h4>
        <ProbabilityBar
          home={analysis.probabilities.home_win}
          draw={analysis.probabilities.draw}
          away={analysis.probabilities.away_win}
        />
        <div className="xg-row">
          <span className="xg">
            Gols esperados: <b>{analysis.expected_goals.home.toFixed(2)}</b> x{" "}
            <b>{analysis.expected_goals.away.toFixed(2)}</b>
          </span>
          <span className="fav">
            Favorito:{" "}
            <b>
              {analysis.probabilities.home_win >= analysis.probabilities.away_win
                ? home.team.name
                : away.team.name}
            </b>
          </span>
        </div>
      </section>

      {provider && (
        <section className="card">
          <h4>
            Leitura da api-football{" "}
            <span className="api-note">(real, atual)</span>
          </h4>
          <ProbabilityBar
            home={provider.percent.home_win}
            draw={provider.percent.draw}
            away={provider.percent.away_win}
          />
          <div className="comp-grid">
            {Object.entries(provider.comparison).map(([key, val]) => {
              const h = shiftPct(val?.home)
              const a = shiftPct(val?.away)
              if (h == null || a == null) return null
              return (
                <div className="comp-row" key={key}>
                  <span className="comp-label">{compLabels[key] ?? key}</span>
                  <div className="comp-bar">
                    <span
                      className="comp-bar-home"
                      style={{ width: `${h}%` }}
                      title={`${home.team.short_name}: ${h}%`}
                    />
                  </div>
                  <span className="comp-pct comp-home">
                    {home.team.short_name} {h}%
                  </span>
                  <span className="comp-pct comp-away">
                    {away.team.short_name} {a}%
                  </span>
                </div>
              )
            })}
          </div>
          {provider.h2h.length > 0 && (
            <div className="h2h-list">
              <span className="h2h-title">Ultimos confrontos diretos</span>
              {provider.h2h.map((h, i) => (
                <span className="h2h-item" key={i}>
                  {h.home} {h.home_goals ?? "-"} x {h.away_goals ?? "-"} {h.away}
                </span>
              ))}
            </div>
          )}
        </section>
      )}

      <section className="card">
        <h4>Fatores que movem a estimativa</h4>
        <div className="factor-table">
          {analysis.factors.map((f) => (
            <div className="factor-row" key={f.key}>
              <div className="factor-main">
                <span className="factor-label">{f.label}</span>
                <span className="factor-detail">{f.detail}</span>
              </div>
              <div className="factor-shifts">
                <Shift value={f.home_shift} side="home" />
                <Shift value={f.away_shift} side="away" />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h4>Contexto dos times</h4>
        <div className="team-grid">
          <TeamPanel ctx={home} />
          <TeamPanel ctx={away} />
        </div>
      </section>

      <p className="disclaimer-footer">{analysis.disclaimer}</p>
    </div>
  )
}
