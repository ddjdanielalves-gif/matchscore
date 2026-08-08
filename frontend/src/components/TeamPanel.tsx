import type { TeamContext } from "../types"
import Crest from "./Crest"
import FormChips from "./FormChips"

function IssueList({ title, items, tone }: { title: string; items: TeamContext["injuries"]; tone: string }) {
  if (items.length === 0) {
    return (
      <div className="issue-block">
        <h5 className="issue-title">{title}</h5>
        <span className="issue-none">Nenhum</span>
      </div>
    )
  }
  return (
    <div className="issue-block">
      <h5 className="issue-title">{title}</h5>
      <ul className={`issue-list ${tone}`}>
        {items.map((it, i) => (
          <li key={i}>
            <span className="issue-pos">{it.position || "?"}</span>
            <span className="issue-name">{it.player}</span>
            <span className="issue-reason">{it.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function TeamPanel({ ctx }: { ctx: TeamContext }) {
  return (
    <div className="team-panel">
      <div className="team-panel-head">
        <Crest team={ctx.team} size={44} />
        <div className="team-panel-title">
          <h3>{ctx.team.name}</h3>
          <div className="team-metrics">
            {ctx.position && <span className="metric">#{ctx.position} na tabela</span>}
            {ctx.points !== null && <span className="metric">{ctx.points} pts</span>}
            <span className="metric">ELO {ctx.elo.toFixed(0)}</span>
            <span className="metric">
              Gols {ctx.avg_goals_for.toFixed(2)} pf / {ctx.avg_goals_against.toFixed(2)} pc
            </span>
            <span className="metric">
              Cartões {ctx.avg_yellow_cards.toFixed(1)}A / {ctx.avg_red_cards.toFixed(2)}V
            </span>
          </div>
        </div>
      </div>
      <div className="team-form-row">
        <span className="team-form-label">Últimos jogos</span>
        <FormChips form={ctx.form_last6} />
      </div>
      <div className="issue-grid">
        <IssueList title="Lesões" items={ctx.injuries} tone="tone-inj" />
        <IssueList title="Suspensões" items={ctx.suspensions} tone="tone-sus" />
      </div>
    </div>
  )
}
