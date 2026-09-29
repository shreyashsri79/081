import type { ModelId, ScoreRow } from './contract'

export type Ref = 'best' | 'b1' | ModelId

export const refRmse = (row: ScoreRow, ref: Ref) => (ref === 'best' ? row.rmse[row.best]! : row.rmse[ref])

/** Blend − reference, and whether it clears the 95 % CI half-width. */
export function verdict(row: ScoreRow, ref: Ref) {
  const r = refRmse(row, ref)
  if (r == null) return null
  const d = row.rmse.blend! - r
  const half = (row.ci[1] - row.ci[0]) / 2
  const sig = ref === 'best' ? row.ci[1] < 0 || row.ci[0] > 0 : Math.abs(d) > half
  return { pct: (d / r) * 100, sig }
}

/** Green = blend better, red = worse, grey = CI includes zero (no claim). */
export function cellColour(pct: number, sig: boolean) {
  if (!sig) return { background: '#ece9e4', color: '#7a878c' }
  const t = Math.min(1, Math.abs(pct) / 15)
  const [r, g, b] = pct < 0 ? [47, 125, 90] : [196, 52, 42]
  const a = 0.18 + 0.72 * t
  return { background: `rgb(${r} ${g} ${b} / ${a})`, color: a > 0.55 ? '#f8f7f5' : '#0e2129' }
}
