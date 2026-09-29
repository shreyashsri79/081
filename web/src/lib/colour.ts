import type { VarId } from './contract'

type RGB = [number, number, number]
export interface Scale {
  stops: [number, string][]
  /** Tick values printed on the legend. */
  ticks: number[]
  /** Discrete bins: no interpolation between stops (used for rain categories). */
  stepped?: boolean
}

const hex = (h: string): RGB => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)]
const cache = new WeakMap<Scale, [number, RGB][]>()

export function sample(s: Scale, v: number): RGB {
  let st = cache.get(s)
  if (!st) { st = s.stops.map(([x, c]) => [x, hex(c)]); cache.set(s, st) }
  if (v <= st[0][0]) return st[0][1]
  for (let a = 1; a < st.length; a++) {
    if (v < st[a][0]) {
      if (s.stepped) return st[a - 1][1]
      const [x0, c0] = st[a - 1], [x1, c1] = st[a]
      const t = (v - x0) / (x1 - x0)
      return [c0[0] + (c1[0] - c0[0]) * t, c0[1] + (c1[1] - c0[1]) * t, c0[2] + (c1[2] - c0[2]) * t]
    }
  }
  return st[st.length - 1][1]
}

export const css = (c: RGB, a = 1) => `rgb(${c[0] | 0} ${c[1] | 0} ${c[2] | 0} / ${a})`

/**
 * Rain bins follow IMD's categories, so 64.5, 115.6 and 204.5 mm read as
 * heavy / very heavy / extremely heavy without a lookup.
 */
export const SCALES: Record<VarId, Scale> = {
  rain: {
    stepped: true,
    stops: [[0, '#f3f1ec'], [1, '#d6e6e4'], [2.5, '#a9d3d0'], [7.5, '#6bb6c2'], [15.6, '#3b8fb8'], [35.5, '#2a5fa3'], [64.5, '#3d3591'], [115.6, '#7b2388'], [204.5, '#c0266a']],
    ticks: [1, 7.5, 15.6, 35.5, 64.5, 115.6, 204.5],
  },
  t2m: {
    stops: [[-5, '#3a4f8c'], [10, '#7aa6c9'], [20, '#d8e3d9'], [27, '#f2e6b8'], [33, '#e9a15c'], [38, '#c8502e'], [44, '#7d1b25']],
    ticks: [0, 10, 20, 27, 33, 38, 44],
  },
  wind: {
    stops: [[0, '#eef2ef'], [3, '#c4e4dc'], [6, '#86cbc9'], [9, '#4f9fcc'], [12, '#5b66bf'], [15, '#8a3f9e'], [20, '#b3265e']],
    ticks: [0, 3, 6, 9, 12, 15, 20],
  },
  mslp: {
    stops: [[996, '#7d2b4f'], [1000, '#c4715f'], [1004, '#efd9bf'], [1008, '#eef0eb'], [1012, '#b7cfe0'], [1016, '#4f7fb0']],
    ticks: [996, 1000, 1004, 1008, 1012, 1016],
  },
}

export const PROB: Scale = {
  stepped: true,
  stops: [[0, '#f3f1ec'], [0.05, '#f1dfc9'], [0.15, '#eab98c'], [0.3, '#dd8a55'], [0.5, '#c9582f'], [0.7, '#a02b22'], [0.9, '#5e1116']],
  ticks: [0.05, 0.15, 0.3, 0.5, 0.7, 0.9],
}

export const hexToRgb = hex
