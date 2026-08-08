export default function ProbabilityBar({
  home,
  draw,
  away,
}: {
  home: number
  draw: number
  away: number
}) {
  return (
    <div className="prob-wrap">
      <div className="prob-bar" role="img" aria-label={`Vitória do mandante ${home}%, empate ${draw}%, visitante ${away}%`}>
        <div className="prob-seg prob-home" style={{ width: `${home}%` }} />
        <div className="prob-seg prob-draw" style={{ width: `${draw}%` }} />
        <div className="prob-seg prob-away" style={{ width: `${away}%` }} />
      </div>
      <div className="prob-legend">
        <span className="lg-home">
          <b>{home.toFixed(1)}%</b> Mandante
        </span>
        <span className="lg-draw">
          <b>{draw.toFixed(1)}%</b> Empate
        </span>
        <span className="lg-away">
          <b>{away.toFixed(1)}%</b> Visitante
        </span>
      </div>
    </div>
  )
}
