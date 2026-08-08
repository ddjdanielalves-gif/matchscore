import type { Match } from "../types"
import Crest from "./Crest"

function fmtDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export default function MatchCard({
  match,
  selected,
  onSelect,
}: {
  match: Match
  selected: boolean
  onSelect: () => void
}) {
  const finished = match.status === "finished"
  return (
    <button
      type="button"
      className={`match-card ${selected ? "match-card-selected" : ""}`}
      onClick={onSelect}
    >
      <div className="match-meta">
        <span className="match-round">{match.round}</span>
        <span className="match-date">{fmtDate(match.date)}</span>
      </div>
      <div className="match-teams">
        <div className="team-row">
          <Crest team={match.home} size={28} />
          <span className="team-name">{match.home.name}</span>
        </div>
        <div className="team-row">
          <Crest team={match.away} size={28} />
          <span className="team-name">{match.away.name}</span>
        </div>
      </div>
      {finished && match.score.home !== null && (
        <div className="match-score">
          <b>{match.score.home}</b>
          <span className="vs">x</span>
          <b>{match.score.away}</b>
        </div>
      )}
      {!finished && <span className="match-analyze">Analisar →</span>}
    </button>
  )
}
