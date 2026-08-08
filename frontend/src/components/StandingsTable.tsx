import type { Standings } from "../types"
import Crest from "./Crest"
import FormChips from "./FormChips"

export default function StandingsTable({ standings }: { standings: Standings }) {
  return (
    <section className="card">
      <div className="standings-head">
        <h3>{standings.competition}</h3>
        <span className="standings-season">
          Temporada {standings.season}
          {standings.source === "api" && (
            <span className="api-note"> · ultima completa no plano gratuito</span>
          )}
        </span>
      </div>
      <div className="table-wrap">
        <table className="standings">
          <thead>
            <tr>
              <th>#</th>
              <th>Time</th>
              <th>P</th>
              <th>J</th>
              <th>V</th>
              <th>E</th>
              <th>D</th>
              <th>GP</th>
              <th>GC</th>
              <th>Forma</th>
            </tr>
          </thead>
          <tbody>
            {standings.rows.map((r) => (
              <tr key={r.team.id}>
                <td className={`pos pos-${r.position}`}>{r.position}</td>
                <td className="team-cell">
                  <Crest team={r.team} size={22} />
                  {r.team.name}
                </td>
                <td className="num strong">{r.points}</td>
                <td className="num">{r.games}</td>
                <td className="num">{r.wins}</td>
                <td className="num">{r.draws}</td>
                <td className="num">{r.losses}</td>
                <td className="num">{r.goals_for}</td>
                <td className="num">{r.goals_against}</td>
                <td>
                  <FormChips form={r.form} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
