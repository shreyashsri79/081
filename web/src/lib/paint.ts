import type { WeightSet } from './contract'
import { hexToRgb } from './colour'
import { MODELS } from './models'

type RGB = [number, number, number]
export const PAPER: RGB = [243, 241, 236]
export const mix = (c: RGB, t: number): RGB =>
  [PAPER[0] + (c[0] - PAPER[0]) * t, PAPER[1] + (c[1] - PAPER[1]) * t, PAPER[2] + (c[2] - PAPER[2]) * t]

/**
 * Dominant-model paint: each cell takes the hue of its largest weight, faded
 * by how decisive that weight is. 1/n (no preference) is pale; 1 is full hue.
 */
export function dominantPaint(ws: WeightSet) {
  const cols = ws.models.map((m) => hexToRgb(MODELS[m].colour))
  const n = ws.models.length
  return (k: number): RGB | null => {
    const a = ws.dominant[k]
    if (!Number.isFinite(ws.weights[a][k])) return null // masked cell
    const t = Math.min(1, ((ws.weights[a][k] - 1 / n) / (1 - 1 / n)) * 1.6 + 0.18)
    return mix(cols[a], t)
  }
}

/** Share of cells (optionally only where `mask` ≥ 0) led by each model. */
export function dominantShare(ws: WeightSet, mask?: Int16Array) {
  const count = ws.models.map(() => 0)
  let n = 0
  for (let k = 0; k < ws.dominant.length; k++) {
    if (mask && mask[k] < 0) continue
    count[ws.dominant[k]]++
    n++
  }
  return ws.models.map((m, a) => ({ model: m, share: n ? count[a] / n : 0 }))
}
