export default function SourceBadge({ sources }: { sources: string[] }) {
  const real = sources.some((s) => s.includes("api"))
  const labels = real ? "Dados reais (api-football)" : "Modo demo (dados simulados)"
  const notes = sources.filter((s) => s !== "api" && s !== "demo")
  return (
    <span className={`badge ${real ? "badge-real" : "badge-demo"}`} title={sources.join(", ")}>
      {labels}
      {notes.length > 0 && <span className="badge-note"> · {notes.join(" · ")}</span>}
    </span>
  )
}
