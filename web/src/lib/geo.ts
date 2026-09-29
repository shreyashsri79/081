import india from '@/geo/india.json'
import type { Grid } from './contract'

type Ring = number[][]

export const OUTLINE = india.outline as Ring[]
export const STATES = india.states as { name: string; rings: Ring[] }[]

/** Domain of the blend: India box 5–40° N, 65–100° E (B4.3). */
export const BOX = { lat0: 5, lat1: 40, lon0: 65, lon1: 100 }
/** Equirectangular, scaled by cos(mid-latitude) so India is not stretched. */
export const KX = Math.cos((((BOX.lat0 + BOX.lat1) / 2) * Math.PI) / 180)
export const ASPECT = ((BOX.lon1 - BOX.lon0) * KX) / (BOX.lat1 - BOX.lat0)

export function project(lon: number, lat: number, w: number, h: number): [number, number] {
  return [((lon - BOX.lon0) / (BOX.lon1 - BOX.lon0)) * w, ((BOX.lat1 - lat) / (BOX.lat1 - BOX.lat0)) * h]
}

export function unproject(x: number, y: number, w: number, h: number): [number, number] {
  return [BOX.lon0 + (x / w) * (BOX.lon1 - BOX.lon0), BOX.lat1 - (y / h) * (BOX.lat1 - BOX.lat0)]
}

export function ringsToPath(rings: Ring[], w: number, h: number) {
  let d = ''
  for (const r of rings) {
    r.forEach(([lon, lat], k) => {
      const [x, y] = project(lon, lat, w, h)
      d += `${k ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    d += 'Z'
  }
  return d
}

function inRing(x: number, y: number, r: Ring) {
  let inside = false
  for (let a = 0, b = r.length - 1; a < r.length; b = a++) {
    const [xa, ya] = r[a], [xb, yb] = r[b]
    if (ya > y !== yb > y && x < ((xb - xa) * (y - ya)) / (yb - ya) + xa) inside = !inside
  }
  return inside
}

const bbox = (rings: Ring[]) => {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (const r of rings) for (const [x, y] of r) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y) }
  return [x0, y0, x1, y1]
}
const STATE_BOX = STATES.map((s) => bbox(s.rings))

export function stateAt(lon: number, lat: number): number {
  for (let s = 0; s < STATES.length; s++) {
    const [x0, y0, x1, y1] = STATE_BOX[s]
    if (lon < x0 || lon > x1 || lat < y0 || lat > y1) continue
    let n = 0
    for (const r of STATES[s].rings) if (inRing(lon, lat, r)) n++
    if (n % 2 === 1) return s
  }
  return -1
}

const stateCache = new Map<string, Int16Array>()
/** State index per grid cell, −1 outside India. Row-major like the fields. */
export function stateIndex(g: Grid): Int16Array {
  const key = `${g.lat0},${g.lon0},${g.step},${g.ny},${g.nx}`
  let idx = stateCache.get(key)
  if (!idx) {
    idx = new Int16Array(g.ny * g.nx)
    for (let i = 0; i < g.ny; i++)
      for (let j = 0; j < g.nx; j++) idx[i * g.nx + j] = stateAt(g.lon0 + j * g.step, g.lat0 + i * g.step)
    stateCache.set(key, idx)
  }
  return idx
}

export const fmtLat = (v: number) => `${Math.abs(v).toFixed(2)}°${v >= 0 ? 'N' : 'S'}`
export const fmtLon = (v: number) => `${Math.abs(v).toFixed(2)}°${v >= 0 ? 'E' : 'W'}`
