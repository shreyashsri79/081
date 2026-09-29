/**
 * The shape of everything the dashboard reads. Mirrors the C11 API table in
 * WORKFLOW_AND_DECK_81.md; blend/server.py must return exactly these.
 *
 *   GET /api/runs                        -> RunSummary[]
 *   GET /api/runs/:id                    -> Run
 *   GET /api/field?run=&var=&lead=       -> Field           (blended)
 *   GET /api/weights?run=&var=&lead=     -> WeightSet       (all models + dominant)
 *   GET /api/scorecard?run=              -> Scorecard
 *   GET /api/extremes?run=&type=&lead=   -> ExtremeMap
 *   GET /api/cell?run=&var=&lead=&i=&j=  -> CellReport
 *   GET /api/meteogram?run=&i=&j=        -> Meteogram
 *
 * Server side: blend/api_models.py (pydantic, same fields, camelCase on the wire).
 */

export type ModelId = 'hres' | 'graphcast' | 'pangu' | 'fuxi' | 'gencast' | 'ifs' | 'aifs' | 'gfs'
export type VarId = 'rain' | 't2m' | 'wind' | 'mslp'
/** Engine runs name their events (Run.extremes, e.g. 'rain_p95'); the synthetic source uses lib/models EXTREMES. */
export type ExtremeId = string
export type Season = 'JF' | 'MAM' | 'JJAS' | 'OND'
export type Rung = 'B0' | 'B1' | 'B2' | 'B2c' | 'B3s' | 'B3' | 'B3c' | 'B4'

/** Regular lat/lon grid; values are row-major, row 0 = southernmost. */
export interface Grid {
  lat0: number
  lon0: number
  step: number
  ny: number
  nx: number
}

export interface Regime {
  season: Season
  /** e.g. "Monsoon active", "Break", "Depression", "Western disturbance", "Heat" */
  label: string
  /** How the label was obtained. Never the true valid-day regime (C4 leakage rule). */
  basis: 'init' | 'forecast'
}

export type StepStatus = 'ok' | 'failed' | 'skipped'

export interface RunStep {
  name: string
  status: StepStatus
  seconds: number
  note?: string
}

export interface RunSummary {
  id: string
  kind: 'live' | 'hindcast'
  /** ISO time of the model initialisation, UTC */
  init: string
  status: 'ok' | 'partial' | 'failed'
  models: ModelId[]
}

export interface Run extends RunSummary {
  grid: Grid
  leads: number[]
  vars: VarId[]
  /** Which models contribute to which variable (rain has fewer, see B4.1). */
  modelsByVar: Record<VarId, ModelId[]>
  regime: Regime
  rung: Rung
  steps: RunStep[]
  /** 'synthetic' until the engine produces real output. Shown on every screen. */
  provenance: 'synthetic' | 'measured'
  /** Honesty notes from the exporter: truth used, out-of-sample fold, rung per variable, gaps. */
  notes?: string[]
  /** Extreme events this run provides (ids for /api/extremes); absent in the synthetic source. */
  extremes?: { id: string; var: VarId; name: string; short: string; threshold: string; available: boolean; note?: string }[]
}

export interface Field {
  var: VarId
  lead: number
  units: string
  values: Float32Array
  /** Wind only: eastward and northward components (m/s), for particles. */
  u?: Float32Array
  v?: Float32Array
}

export interface WeightSet {
  var: VarId
  lead: number
  models: ModelId[]
  /** One array per model, same order as `models`; each cell sums to 1. */
  weights: Float32Array[]
  /** Index into `models` of the largest weight per cell. */
  dominant: Uint8Array
}

export interface ScoreRow {
  var: VarId
  lead: number
  /** RMSE per source. 'b1' = equal mean, 'blend' = the shipped rung. */
  rmse: Partial<Record<ModelId | 'b1' | 'blend', number>>
  /** Best single model on training data (B0). */
  best: ModelId
  /** blend − best, with 95 % block-bootstrap CI. Negative = blend better. */
  delta: number
  ci: [number, number]
}

export interface Scorecard {
  validation: string
  rows: ScoreRow[]
  /** Blend − best single model by region, Day 3, per variable (C8 breakdown). */
  regions: { var: VarId; name: string; delta: number; ci: [number, number] }[]
}

export interface ExtremeMap {
  type: ExtremeId
  lead: number
  threshold: string
  prob: Float32Array
  /** State roll-up: max cell probability inside the state. */
  states: { name: string; pmax: number; pmean: number; cells: number }[]
  /** false: this indicator cannot be produced for this run; `note` says why. */
  available?: boolean
  /** false until quantile mapping + isotonic calibration (Phase G). */
  calibrated?: boolean
  method?: string
  note?: string
}

export interface CellReport {
  i: number
  j: number
  lat: number
  lon: number
  var: VarId
  lead: number
  blend: number
  members: { model: ModelId; value: number; weight: number; mse: number; bias: number }[]
  /** MSE per model at every lead, for the skill-vs-lead sparkline. */
  mseByLead: { model: ModelId; mse: number[] }[]
  /** Cases behind the regime-specific MSE, and the shrinkage constant (C5). */
  nRegime: number
  nSeason: number
  k: number
}

/**
 * Everything at one cell across every lead: the MultiModel meteogram.
 *   GET /api/meteogram?run=&i=&j=
 */
export interface Meteogram {
  i: number
  j: number
  lat: number
  lon: number
  leads: number[]
  vars: {
    var: VarId
    blend: number[]
    members: { model: ModelId; values: number[]; weights: number[] }[]
  }[]
}
