/**
 * SYNTHETIC SOURCE. Every number produced here is invented so the interface
 * can be built before the engine exists. It is shaped like the real thing
 * (monsoon rain on the Western Ghats and the north-east, a heat low over the
 * Thar, inverse-MSE weights that sum to one) but it is not a forecast and not
 * a result. The UI stamps it as synthetic on every screen; never screenshot it
 * for the deck (PPT guide §5.2, §7.5).
 *
 * Weights use the real B3 formula, w_m = (1/MSE_m) / Σ_k (1/MSE_k), applied to
 * made-up MSE surfaces, so the mechanics on screen are the mechanics we ship.
 */
import type {
  CellReport, ExtremeId, Meteogram, ExtremeMap, Field, Grid, ModelId, Run, RunSummary, Scorecard, ScoreRow, VarId, WeightSet,
} from './contract'
import { STATES, stateIndex } from './geo'
import { VARS } from './models'

const GRID: Grid = { lat0: 5, lon0: 65, step: 0.5, ny: 71, nx: 71 }
const LEADS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
const VAR_IDS: VarId[] = ['rain', 't2m', 'wind', 'mslp']

// ---------------------------------------------------------------- noise

function hash(ix: number, iy: number, seed: number) {
  let h = (ix * 374761393 + iy * 668265263 + seed * 2147483647) | 0
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  h ^= h >>> 16
  return (h >>> 0) / 4294967295
}
const smooth = (t: number) => t * t * (3 - 2 * t)
function vnoise(x: number, y: number, seed: number) {
  const ix = Math.floor(x), iy = Math.floor(y)
  const fx = smooth(x - ix), fy = smooth(y - iy)
  const a = hash(ix, iy, seed), b = hash(ix + 1, iy, seed)
  const c = hash(ix, iy + 1, seed), d = hash(ix + 1, iy + 1, seed)
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy
}
/** Fractal noise in roughly [−1, 1]. */
function fbm(x: number, y: number, seed: number) {
  return (vnoise(x, y, seed) * 0.6 + vnoise(x * 2.1, y * 2.1, seed + 11) * 0.28 + vnoise(x * 4.3, y * 4.3, seed + 23) * 0.12) * 2 - 1
}
const g = (lon: number, lat: number, cx: number, cy: number, sx: number, sy: number) =>
  Math.exp(-(((lon - cx) / sx) ** 2) - ((lat - cy) / sy) ** 2)
const sig = (x: number) => 1 / (1 + Math.exp(-x))
const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x))

// ------------------------------------------------------------ geography

/** 0 on the plains, 1 on the Tibetan plateau / high Himalaya. */
const elev = (lon: number, lat: number) => (lon > 73.5 ? sig((lat - (35.6 - (lon - 73) * 0.33)) * 2.2) : 0)
/** Orography that matters for rain skill: Ghats, Himalaya front, NE hills. */
const oro = (lon: number, lat: number) =>
  clamp(
    Math.exp(-(((lon - (73.6 + (lat - 8) * 0.12)) / 0.9) ** 2)) * (lat > 8 && lat < 21 ? 1 : 0) +
      Math.exp(-(((lat - (33.5 - (lon - 73) * 0.33)) / 1.2) ** 2)) * (lon > 74 && lon < 96 ? 1 : 0) +
      g(lon, lat, 92.5, 25, 2, 1.5),
    0, 1,
  )
function isSea(lon: number, lat: number, inIndia: boolean) {
  if (inIndia) return false
  if (lat > 22.5) return false
  if (lon > 92.5 && lat > 15) return false // Myanmar
  if (lon > 79.6 && lon < 82 && lat > 5.9 && lat < 9.9) return false // Sri Lanka
  return true
}

// ------------------------------------------------------------- scenario

interface Scenario {
  summary: RunSummary
  label: string
  season: Run['regime']['season']
  monsoon: number
  heat: number
  modelsByVar: Record<VarId, ModelId[]>
  /** Which training profile each model's skill surface borrows (C10 table). */
  profile: Partial<Record<ModelId, ModelId>>
  seed: number
}

const all = (m: ModelId[]): Record<VarId, ModelId[]> => ({ rain: m, t2m: m, wind: m, mslp: m })
const S3: ModelId[] = ['hres', 'graphcast', 'pangu', 'fuxi', 'gencast']
const S1: ModelId[] = ['hres', 'graphcast', 'pangu']
const LIVE: ModelId[] = ['ifs', 'aifs', 'gfs']

const SCENARIOS: Scenario[] = [
  {
    summary: { id: 'live-20260929', kind: 'live', init: '2026-09-29T00:00Z', status: 'ok', models: LIVE },
    label: 'Monsoon withdrawal', season: 'JJAS', monsoon: 0.55, heat: 0, seed: 29,
    modelsByVar: all(LIVE), profile: { ifs: 'hres', aifs: 'fuxi', gfs: 'pangu' },
  },
  {
    summary: { id: 'live-20260928', kind: 'live', init: '2026-09-28T00:00Z', status: 'partial', models: ['ifs', 'gfs'] },
    label: 'Monsoon withdrawal', season: 'JJAS', monsoon: 0.6, heat: 0, seed: 28,
    modelsByVar: all(['ifs', 'gfs']), profile: { ifs: 'hres', gfs: 'pangu' },
  },
  {
    summary: { id: 'live-20260927', kind: 'live', init: '2026-09-27T00:00Z', status: 'ok', models: LIVE },
    label: 'Monsoon normal', season: 'JJAS', monsoon: 0.7, heat: 0, seed: 27,
    modelsByVar: all(LIVE), profile: { ifs: 'hres', aifs: 'fuxi', gfs: 'pangu' },
  },
  {
    summary: { id: 'hindcast-20200715', kind: 'hindcast', init: '2020-07-15T00:00Z', status: 'ok', models: S3 },
    label: 'Monsoon active', season: 'JJAS', monsoon: 1, heat: 0, seed: 2020,
    // Pangu has no precipitation in WeatherBench2: never give it a rain weight (B4.1).
    modelsByVar: { rain: ['hres', 'graphcast', 'fuxi', 'gencast'], t2m: S3, wind: S3, mslp: S3 },
    profile: {},
  },
  {
    summary: { id: 'hindcast-20220428', kind: 'hindcast', init: '2022-04-28T00:00Z', status: 'ok', models: S1 },
    label: 'Heat', season: 'MAM', monsoon: 0.12, heat: 1, seed: 2022,
    modelsByVar: { rain: ['hres', 'graphcast'], t2m: S1, wind: S1, mslp: S1 },
    profile: {},
  },
]

function scenario(id: string) {
  const s = SCENARIOS.find((x) => x.summary.id === id)
  if (!s) throw new Error(`unknown run ${id}`)
  return s
}

// ---------------------------------------------------------------- truth

function truthAt(s: Scenario, v: VarId, lead: number, lon: number, lat: number, inIndia: boolean): number {
  const n = fbm(lon / 3.2 + lead * 0.35, lat / 3.2, s.seed)
  const e = elev(lon, lat)
  const sea = isSea(lon, lat, inIndia)
  switch (v) {
    case 'rain': {
      const m = s.monsoon
      const ghats = 105 * Math.exp(-(((lon - (73.3 + (lat - 8) * 0.13)) / 0.9) ** 2)) * sig((lat - 8) * 2) * sig((21 - lat) * 2)
      const ne = 75 * g(lon, lat, 91.5, 25.5, 2.6, 1.6)
      const trough = 26 * Math.exp(-(((lat - (22 + (lon - 80) * 0.05)) / 2.3) ** 2)) * sig((lon - 74) * 1.5) * sig((89 - lon) * 1.5)
      const low = 60 * g(lon, lat, 88.5 - lead * 0.7, 19.5 + lead * 0.35, 2.4, 2.2)
      const arab = 14 * g(lon, lat, 69, 14, 4, 5)
      const eq = 10 * g(lon, lat, 86, 8, 9, 3)
      // Pre-monsoon: thunderstorms over the north-east and Kerala only.
      const pre = (1 - m) * (40 * g(lon, lat, 91.5, 26, 2.5, 1.8) + 18 * g(lon, lat, 76.5, 9.5, 1.5, 2))
      let r = m * (ghats + ne + trough + low + arab + eq) + pre
      r *= 1 - 0.85 * e
      if (lon < 74 && lat > 24) r *= 0.15
      r *= 0.5 + 0.9 * (n * 0.5 + 0.5)
      return Math.max(0, r - 2)
    }
    case 't2m': {
      const thar = (6 + 9 * s.heat) * g(lon, lat, 72.5, 26.5, 6, 4.5)
      const central = (2 + 6 * s.heat) * g(lon, lat, 79, 24, 6, 4)
      const damp = -0.07 * Math.min(60, truthAt(s, 'rain', lead, lon, lat, inIndia))
      const base = sea ? 28.6 + 0.4 * n : 27 + 2 * s.heat + thar + central + damp - 26 * e + 1.3 * n
      return base
    }
    case 'wind': {
      const jet = (4 + 9 * s.monsoon) * g(lon, lat, 66.5, 13, 6, 5)
      const bay = (2 + 6 * s.monsoon) * g(lon, lat, 88 - lead * 0.6, 17 + lead * 0.3, 3.5, 3)
      const w = 3.5 + jet + bay + (sea ? 1.8 : 0) - 1.5 * e + 1.3 * n
      return Math.max(0.4, w)
    }
    case 'mslp': {
      const heatLow = (6 + 5 * s.heat) * g(lon, lat, 70, 29, 6, 5)
      const monLow = 4 * s.monsoon * g(lon, lat, 88.5 - lead * 0.7, 19.5 + lead * 0.35, 2.4, 2.2)
      return 1007.5 + (22 - lat) * 0.22 - heatLow - monLow + 0.9 * n
    }
  }
}

// --------------------------------------------------------------- skill

const SEEDS: Record<ModelId, number> = { hres: 101, graphcast: 202, pangu: 303, fuxi: 404, gencast: 505, ifs: 101, aifs: 606, gfs: 707 }
/** RMSE at Day 1 for a typical model, per variable. */
const BASE_RMSE: Record<VarId, number> = { rain: 6, t2m: 1.25, wind: 1.35, mslp: 1.05 }
/** Lead growth: GraphCast leads early, GenCast (an ensemble mean) late. */
const GROWTH: Record<ModelId, [number, number]> = {
  hres: [1, 0.3], graphcast: [0.84, 0.29], pangu: [0.95, 0.31], fuxi: [1.02, 0.24], gencast: [1.08, 0.2],
  ifs: [1, 0.3], aifs: [0.98, 0.26], gfs: [1.12, 0.33],
}
const BIAS: Record<ModelId, Record<VarId, number>> = {
  hres: { rain: 1.2, t2m: -0.4, wind: 0.2, mslp: 0.3 },
  graphcast: { rain: -2.1, t2m: 0.3, wind: -0.3, mslp: -0.2 },
  pangu: { rain: 0, t2m: 0.6, wind: -0.5, mslp: 0.4 },
  fuxi: { rain: -2.8, t2m: 0.2, wind: -0.4, mslp: -0.1 },
  gencast: { rain: -3.4, t2m: -0.1, wind: -0.6, mslp: 0 },
  ifs: { rain: 1.1, t2m: -0.5, wind: 0.2, mslp: 0.3 },
  aifs: { rain: -2.4, t2m: 0.3, wind: -0.3, mslp: -0.2 },
  gfs: { rain: 3.1, t2m: 1.1, wind: 0.7, mslp: -0.6 },
}

function mseAt(s: Scenario, model: ModelId, v: VarId, lead: number, lon: number, lat: number, inIndia: boolean): number {
  const p = s.profile[model] ?? model
  const [a, b] = GROWTH[p]
  const o = oro(lon, lat)
  const sea = isSea(lon, lat, inIndia) ? 1 : 0
  let mod = 0
  switch (p) {
    case 'hres': mod = -0.38 * o + 0.12; break
    case 'graphcast': mod = 0.34 * o - 0.08 - 0.1 * sea; break
    case 'pangu': mod = -0.22 * sea + 0.1 * o + (v === 'wind' ? -0.12 : 0); break
    case 'fuxi': mod = 0.12 * o - 0.12 * g(lon, lat, 80, 22, 6, 5); break
    case 'gencast': mod = v === 'rain' ? 0.35 * o : -0.05; break
  }
  // Live models without a training counterpart start near equal (C10).
  if (model === 'aifs' || model === 'gfs') mod *= 0.4
  if (model === 'gfs') mod += 0.12
  const noise = 0.28 * fbm(lon / 4 + lead * 0.2, lat / 4, SEEDS[model] + s.seed + VAR_IDS.indexOf(v) * 31)
  const rmse = BASE_RMSE[v] * (a + b * (lead - 1)) * (1 + mod + noise)
  const scale = v === 'rain' ? 0.35 + truthAt(s, 'rain', lead, lon, lat, inIndia) / 30 : 1
  return (Math.max(0.15, rmse) * scale) ** 2
}

/**
 * Unit wind direction (toward which the air moves). Monsoon: south-westerly
 * across the Arabian Sea and peninsula, westerlies north of 28° N, cyclonic
 * turning round the Bay low and the heat low. Pre-monsoon: north-westerlies.
 */
function windDir(s: Scenario, lead: number, lon: number, lat: number): [number, number] {
  const m = s.monsoon
  let dx = 0, dy = 0
  // large-scale flow
  const south = sig((26 - lat) * 0.6)
  dx += m * 0.75 * south + (1 - m) * 0.8 * sig((lat - 18) * 0.5)
  dy += m * 0.65 * south - (1 - m) * 0.55 * sig((lat - 18) * 0.5)
  dx += 0.9 * sig((lat - 29) * 0.8)
  // cyclonic (anticlockwise) circulation round the lows
  const lows: [number, number, number, number][] = [
    [88.5 - lead * 0.7, 19.5 + lead * 0.35, 3.2, 1.6 * m],
    [70, 29, 5, 0.6 + 0.8 * s.heat],
  ]
  for (const [cx, cy, r, a] of lows) {
    const w = a * g(lon, lat, cx, cy, r, r)
    const ex = (lon - cx) / r, ey = (lat - cy) / r
    dx += -ey * w * 1.6
    dy += ex * w * 1.6
  }
  const rot = 0.35 * fbm(lon / 5 + lead * 0.3, lat / 5, s.seed + 91)
  const c = Math.cos(rot), sn = Math.sin(rot)
  const rx = dx * c - dy * sn, ry = dx * sn + dy * c
  const n = Math.hypot(rx, ry) || 1
  return [rx / n, ry / n]
}

// ---------------------------------------------------------------- cache

const cache = new Map<string, unknown>()
function memo<T>(key: string, make: () => T): T {
  if (!cache.has(key)) cache.set(key, make())
  return cache.get(key) as T
}

function eachCell(fn: (k: number, lon: number, lat: number, inIndia: boolean) => number) {
  const out = new Float32Array(GRID.ny * GRID.nx)
  const idx = stateIndex(GRID)
  for (let i = 0; i < GRID.ny; i++)
    for (let j = 0; j < GRID.nx; j++) {
      const k = i * GRID.nx + j
      out[k] = fn(k, GRID.lon0 + j * GRID.step, GRID.lat0 + i * GRID.step, idx[k] >= 0)
    }
  return out
}

const truth = (s: Scenario, v: VarId, lead: number) =>
  memo(`t|${s.summary.id}|${v}|${lead}`, () => eachCell((_, lon, lat, ind) => truthAt(s, v, lead, lon, lat, ind)))

const mse = (s: Scenario, m: ModelId, v: VarId, lead: number) =>
  memo(`m|${s.summary.id}|${m}|${v}|${lead}`, () => eachCell((_, lon, lat, ind) => mseAt(s, m, v, lead, lon, lat, ind)))

/** Raw model forecast: truth + bias + error whose size matches its MSE. */
const forecast = (s: Scenario, m: ModelId, v: VarId, lead: number) =>
  memo(`f|${s.summary.id}|${m}|${v}|${lead}`, () => {
    const t = truth(s, v, lead), e = mse(s, m, v, lead)
    return eachCell((k, lon, lat) => {
      const err = Math.sqrt(e[k]) * 1.2 * fbm(lon / 2.4 + lead, lat / 2.4, SEEDS[m] * 7 + s.seed)
      const val = t[k] + BIAS[m][v] + err
      return v === 'rain' ? Math.max(0, val) : val
    })
  })

const weights = (s: Scenario, v: VarId, lead: number) =>
  memo(`w|${s.summary.id}|${v}|${lead}`, () => {
    const models = s.modelsByVar[v]
    const inv = models.map((m) => mse(s, m, v, lead).map((x) => 1 / x))
    const n = GRID.ny * GRID.nx
    const w = models.map(() => new Float32Array(n))
    const dom = new Uint8Array(n)
    for (let k = 0; k < n; k++) {
      let sum = 0, best = 0
      for (let a = 0; a < models.length; a++) sum += inv[a][k]
      for (let a = 0; a < models.length; a++) {
        w[a][k] = inv[a][k] / sum
        if (w[a][k] > w[best][k]) best = a
      }
      dom[k] = best
    }
    return { models, w, dom }
  })

const blend = (s: Scenario, v: VarId, lead: number) =>
  memo(`b|${s.summary.id}|${v}|${lead}`, () => {
    const { models, w } = weights(s, v, lead)
    const f = models.map((m) => forecast(s, m, v, lead))
    return eachCell((k) => {
      let x = 0
      models.forEach((m, a) => { x += w[a][k] * (f[a][k] - BIAS[m][v]) })
      return v === 'rain' ? Math.max(0, x) : x
    })
  })

// ------------------------------------------------------------------ API

export function listRuns(): RunSummary[] {
  return SCENARIOS.map((s) => s.summary)
}

export function getRun(id: string): Run {
  const s = scenario(id)
  const live = s.summary.kind === 'live'
  const failed = s.summary.status === 'partial'
  const steps: Run['steps'] = live
    ? [
        { name: 'fetch NOAA GFS 00 UTC', status: 'ok', seconds: 214 },
        { name: 'fetch ECMWF IFS open data', status: 'ok', seconds: 167 },
        failed
          ? { name: 'fetch ECMWF AIFS', status: 'failed', seconds: 900, note: 'timeout after 900 s; run continued with IFS + GFS' }
          : { name: 'fetch ECMWF AIFS', status: 'ok', seconds: 141 },
        { name: 'harmonise to 0.5° grid', status: 'ok', seconds: 38 },
        { name: 'regime from analysis (init)', status: 'ok', seconds: 4 },
        { name: 'apply weights B4', status: 'ok', seconds: 6 },
        { name: 'extreme probabilities', status: 'ok', seconds: 11 },
        { name: 'write bundle', status: 'ok', seconds: 9 },
        { name: 'online weight update (truth D−1)', status: 'ok', seconds: 21 },
      ]
    : [
        { name: 'load WeatherBench2 stores', status: 'ok', seconds: 412 },
        { name: 'harmonise to 0.5° grid', status: 'ok', seconds: 55 },
        { name: 'regime labels (init)', status: 'ok', seconds: 7 },
        { name: 'apply weights B3', status: 'ok', seconds: 5 },
        { name: 'extreme probabilities', status: 'ok', seconds: 12 },
        { name: 'verify vs ERA5 / CHIRPS', status: 'ok', seconds: 96 },
      ]
  return {
    ...s.summary,
    grid: GRID,
    leads: LEADS,
    vars: VAR_IDS,
    modelsByVar: s.modelsByVar,
    regime: { season: s.season, label: s.label, basis: 'init' },
    rung: live ? 'B4' : 'B3',
    steps,
    provenance: 'synthetic',
  }
}

const uvCache = new WeakMap<Float32Array, { u: Float32Array; v: Float32Array }>()
/** u, v from a speed field (each speed array is unique to its run, model and lead). */
function withWind(s: Scenario, lead: number, speed: Float32Array) {
  let uv = uvCache.get(speed)
  if (!uv) {
    const u = new Float32Array(speed.length), v = new Float32Array(speed.length)
    eachCell((k, lon, lat) => {
      const [dx, dy] = windDir(s, lead, lon, lat)
      u[k] = dx * speed[k]
      v[k] = dy * speed[k]
      return 0
    })
    uv = { u, v }
    uvCache.set(speed, uv)
  }
  return uv
}

export function getField(id: string, v: VarId, lead: number): Field {
  const s = scenario(id)
  const values = blend(s, v, lead)
  return { var: v, lead, units: VARS[v].units, values, ...(v === 'wind' ? withWind(s, lead, values) : {}) }
}

export function getModelField(id: string, m: ModelId, v: VarId, lead: number): Field {
  const s = scenario(id)
  const values = forecast(s, m, v, lead)
  return { var: v, lead, units: VARS[v].units, values, ...(v === 'wind' ? withWind(s, lead, values) : {}) }
}

export function getWeights(id: string, v: VarId, lead: number): WeightSet {
  const { models, w, dom } = weights(scenario(id), v, lead)
  return { var: v, lead, models, weights: w, dominant: dom }
}

const EXTREME_DEF: Record<ExtremeId, { v: VarId; thr: number; spread: number }> = {
  rain64: { v: 'rain', thr: 64.5, spread: 14 },
  rain115: { v: 'rain', thr: 115.6, spread: 20 },
  rain204: { v: 'rain', thr: 204.5, spread: 28 },
  heat: { v: 't2m', thr: 40, spread: 1.4 },
  wind15: { v: 'wind', thr: 15, spread: 1.6 },
}

export function getExtremes(id: string, type: ExtremeId, lead: number): ExtremeMap {
  const s = scenario(id)
  const d = EXTREME_DEF[type]
  const prob = memo(`x|${id}|${type}|${lead}`, () => {
    const { models, w } = weights(s, d.v, lead)
    const f = models.map((m) => forecast(s, m, d.v, lead))
    const b = blend(s, d.v, lead)
    // Rain peaks are under-forecast by the mean; the quantile-mapped members
    // are what carry the tail (C7). Stand-in: stretch rain members by 1.35.
    const qm = d.v === 'rain' ? 1.35 : 1
    return eachCell((k) => {
      let pw = 0
      models.forEach((_, a) => { if (f[a][k] * qm >= d.thr) pw += w[a][k] })
      const pc = sig((b[k] * qm - d.thr) / d.spread)
      return clamp(0.5 * pw + 0.45 * pc, 0, 0.95)
    })
  })
  const idx = stateIndex(GRID)
  const acc = STATES.map((st) => ({ name: st.name, pmax: 0, sum: 0, cells: 0 }))
  for (let k = 0; k < idx.length; k++) {
    const si = idx[k]
    if (si < 0) continue
    acc[si].pmax = Math.max(acc[si].pmax, prob[k])
    acc[si].sum += prob[k]
    acc[si].cells++
  }
  return {
    type,
    lead,
    threshold: String(d.thr),
    prob,
    states: acc
      .filter((a) => a.cells > 0)
      .map((a) => ({ name: a.name, pmax: a.pmax, pmean: a.sum / a.cells, cells: a.cells }))
      .sort((x, y) => y.pmax - x.pmax),
  }
}

const REGIONS: { name: string; box: [number, number, number, number]; sea?: boolean }[] = [
  { name: 'North-west', box: [24, 35, 68, 78] },
  { name: 'Central', box: [18, 26, 74, 86] },
  { name: 'North-east', box: [22, 29, 89, 97] },
  { name: 'South peninsula', box: [8, 18, 74, 81] },
  { name: 'Bay of Bengal', box: [10, 21, 82, 92], sea: true },
  { name: 'Arabian Sea', box: [8, 20, 64, 73], sea: true },
]

/** Error correlation between models; blends gain less than the independent-error ideal. */
const RHO = 0.85

export function getScorecard(id: string): Scorecard {
  return memo(`sc|${id}`, () => {
    const s = scenario(id)
    const idx = stateIndex(GRID)
    const rows: ScoreRow[] = []
    const regions: Scorecard['regions'] = []

    const score = (v: VarId, lead: number, keep: (k: number, lon: number, lat: number, ind: boolean) => boolean) => {
      const models = s.modelsByVar[v]
      const ms = models.map((m) => mse(s, m, v, lead))
      const acc = models.map(() => 0)
      let accB = 0, accB1 = 0, n = 0
      for (let i = 0; i < GRID.ny; i++)
        for (let j = 0; j < GRID.nx; j++) {
          const k = i * GRID.nx + j
          const lon = GRID.lon0 + j * GRID.step, lat = GRID.lat0 + i * GRID.step
          if (!keep(k, lon, lat, idx[k] >= 0)) continue
          let inv = 0, sum = 0, min = Infinity
          models.forEach((_, a) => { acc[a] += ms[a][k]; inv += 1 / ms[a][k]; sum += ms[a][k]; min = Math.min(min, ms[a][k]) })
          // Out-of-sample penalty: learned weights are imperfect, worst for rain at long leads.
          const pen = 1 + (lead / 10) * (v === 'rain' ? 0.2 : 0.05)
          accB += (RHO * min + (1 - RHO) / inv) * pen
          accB1 += RHO * (sum / models.length) + ((1 - RHO) * sum) / models.length ** 2
          n++
        }
      const rmse: ScoreRow['rmse'] = {}
      models.forEach((m, a) => { rmse[m] = Math.sqrt(acc[a] / n) })
      rmse.b1 = Math.sqrt(accB1 / n)
      rmse.blend = Math.sqrt(accB / n)
      const best = models.reduce((x, y) => (rmse[y]! < rmse[x]! ? y : x))
      const delta = rmse.blend - rmse[best]!
      const half = 0.35 * Math.abs(delta) + 0.012 * rmse[best]! * (1 + lead / 4) * (v === 'rain' ? 3 : 1)
      return { rmse, best, delta, ci: [delta - half, delta + half] as [number, number] }
    }

    for (const v of VAR_IDS)
      for (const lead of LEADS) rows.push({ var: v, lead, ...score(v, lead, (_, __, ___, ind) => ind) })

    for (const v of VAR_IDS)
      for (const r of REGIONS) {
        const [la0, la1, lo0, lo1] = r.box
        const x = score(v, 3, (_, lon, lat, ind) => lat >= la0 && lat <= la1 && lon >= lo0 && lon <= lo1 && (r.sea ? isSea(lon, lat, ind) : ind))
        regions.push({ var: v, name: r.name, delta: x.delta, ci: x.ci })
      }

    return {
      validation: s.summary.kind === 'hindcast' && s.summary.models.length === 3
        ? 'Leave-one-year-out 2018 / 2020 / 2022 (S1, S2)'
        : s.summary.kind === 'hindcast'
          ? 'Blocked months within 2020 (S3, S4)'
          : 'Rolling 30 days of live runs vs truth D−1',
      rows,
      regions,
    }
  })
}

export function getCell(id: string, v: VarId, lead: number, i: number, j: number): CellReport {
  const s = scenario(id)
  const k = i * GRID.nx + j
  const { models, w } = weights(s, v, lead)
  const lat = GRID.lat0 + i * GRID.step, lon = GRID.lon0 + j * GRID.step
  const h = hash(i, j, s.seed)
  return {
    i, j, lat, lon, var: v, lead,
    blend: blend(s, v, lead)[k],
    members: models.map((m, a) => ({
      model: m,
      value: forecast(s, m, v, lead)[k],
      weight: w[a][k],
      mse: mse(s, m, v, lead)[k],
      bias: BIAS[m][v],
    })),
    mseByLead: models.map((m) => ({ model: m, mse: LEADS.map((L) => mse(s, m, v, L)[k]) })),
    nRegime: s.summary.kind === 'live' ? 8 + Math.floor(h * 14) : 14 + Math.floor(h * 46),
    nSeason: s.summary.kind === 'live' ? 30 : s.season === 'JJAS' ? 122 : 92,
    k: 20,
  }
}

export function getMeteogram(id: string, i: number, j: number): Meteogram {
  const s = scenario(id)
  const k = i * GRID.nx + j
  return {
    i, j,
    lat: GRID.lat0 + i * GRID.step,
    lon: GRID.lon0 + j * GRID.step,
    leads: LEADS,
    vars: VAR_IDS.map((v) => {
      const models = s.modelsByVar[v]
      return {
        var: v,
        blend: LEADS.map((L) => blend(s, v, L)[k]),
        members: models.map((m, a) => ({
          model: m,
          values: LEADS.map((L) => forecast(s, m, v, L)[k]),
          weights: LEADS.map((L) => weights(s, v, L).w[a][k]),
        })),
      }
    }),
  }
}

export const SYNTHETIC_GRID = GRID
