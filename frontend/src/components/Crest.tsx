import { useState } from "react"
import type { TeamRef } from "../types"

const PALETTE = ["#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]

function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

export default function Crest({ team, size = 40 }: { team: TeamRef; size?: number }) {
  const [broken, setBroken] = useState(false)
  const color = PALETTE[hashString(team.short_name || team.name) % PALETTE.length]
  if (broken || !team.crest) {
    return (
      <span
        className="crest-fallback"
        style={{
          width: size,
          height: size,
          fontSize: size * 0.36,
          background: color,
        }}
      >
        {(team.short_name || team.name).slice(0, 3)}
      </span>
    )
  }
  return (
    <img
      className="crest"
      src={team.crest}
      alt={team.name}
      width={size}
      height={size}
      loading="lazy"
      onError={() => setBroken(true)}
    />
  )
}
