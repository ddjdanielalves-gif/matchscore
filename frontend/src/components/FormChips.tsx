const LABEL: Record<string, string> = { W: "V", D: "E", L: "D" }

export default function FormChips({ form }: { form: string[] }) {
  if (form.length === 0) return <span className="form-empty">sem jogos</span>
  return (
    <span className="form-chips">
      {form.slice(0, 5).map((r, i) => (
        <span key={`${i}-${r}`} className={`chip chip-${r.toLowerCase()}`}>
          {LABEL[r] ?? r}
        </span>
      ))}
    </span>
  )
}
