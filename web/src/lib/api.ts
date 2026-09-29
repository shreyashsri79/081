import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { CellReport, ExtremeId, ExtremeMap, Field, Meteogram, ModelId, Run, RunSummary, Scorecard, VarId, WeightSet } from './contract'
// The synthetic source is only needed when no engine answers: load it on demand, outside the main bundle.
type Synth = typeof import('./synthetic')
let synthMod: Promise<Synth> | null = null
const synth = () => (synthMod ??= import('./synthetic'))

/**
 * One door to the data. If blend/server.py answers on /api it is used;
 * otherwise every call is served by the synthetic source and the UI says so.
 * The decision is made once, at the first request.
 */
let mode: Promise<'http' | 'synthetic'> | null = null
function source() {
  // The engine counts only if it answers with JSON and has at least one run to show.
  mode ??= fetch('/api/runs', { signal: AbortSignal.timeout(1500) })
    .then(async (r) => {
      if (!r.ok || !r.headers.get('content-type')?.includes('json')) return 'synthetic' as const
      const runs = await r.json()
      return Array.isArray(runs) && runs.length > 0 ? 'http' as const : 'synthetic' as const
    })
    .catch(() => 'synthetic' as const)
  return mode
}

async function get<T>(path: string, fallback: (s: Synth) => T, revive?: (x: any) => T): Promise<T> {
  if ((await source()) === 'synthetic') return fallback(await synth())
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
  const body = await r.json()
  return revive ? revive(body) : body
}

// JSON null (a masked cell) must become NaN: Float32Array.from would turn it into 0, a fake value.
const f32 = (a: (number | null)[]) => Float32Array.from(a, (x) => (x == null ? NaN : x))
const reviveField = (b: any): Field => ({ ...b, values: f32(b.values), u: b.u && f32(b.u), v: b.v && f32(b.v) })
const q = (o: Record<string, string | number>) => new URLSearchParams(Object.entries(o).map(([k, v]) => [k, String(v)])).toString()

export const api = {
  runs: () => get<RunSummary[]>('/api/runs', (s) => s.listRuns()),
  run: (id: string) => get<Run>(`/api/runs/${id}`, (s) => s.getRun(id)),
  field: (run: string, v: VarId, lead: number) =>
    get<Field>(`/api/field?${q({ run, var: v, lead })}`, (s) => s.getField(run, v, lead), reviveField),
  modelField: (run: string, model: ModelId, v: VarId, lead: number) =>
    get<Field>(`/api/field?${q({ run, var: v, lead, model })}`, (s) => s.getModelField(run, model, v, lead), reviveField),
  weights: (run: string, v: VarId, lead: number) =>
    get<WeightSet>(`/api/weights?${q({ run, var: v, lead })}`, (s) => s.getWeights(run, v, lead),
      (b) => ({ ...b, weights: b.weights.map(f32), dominant: Uint8Array.from(b.dominant) })),
  scorecard: (run: string) => get<Scorecard>(`/api/scorecard?${q({ run })}`, (s) => s.getScorecard(run)),
  extremes: (run: string, type: ExtremeId, lead: number) =>
    get<ExtremeMap>(`/api/extremes?${q({ run, type, lead })}`, (s) => s.getExtremes(run, type, lead), (b) => ({ ...b, prob: f32(b.prob) })),
  cell: (run: string, v: VarId, lead: number, i: number, j: number) =>
    get<CellReport>(`/api/cell?${q({ run, var: v, lead, i, j })}`, (s) => s.getCell(run, v, lead, i, j)),
  meteogram: (run: string, i: number, j: number) =>
    get<Meteogram>(`/api/meteogram?${q({ run, i, j })}`, (s) => s.getMeteogram(run, i, j)),
}

// Keep the previous map on screen while the next lead loads: no flash to blank.
const keep = <T,>(prev: T | undefined) => prev

export const useRuns = () => useQuery({ queryKey: ['runs'], queryFn: api.runs })
export const useRun = (id: string) => useQuery({ queryKey: ['run', id], queryFn: () => api.run(id) })
export const useField = (run: string, v: VarId, lead: number) =>
  useQuery({ queryKey: ['field', run, v, lead], queryFn: () => api.field(run, v, lead), placeholderData: keep })
export const useModelField = (run: string, m: ModelId | null, v: VarId, lead: number) =>
  useQuery({ queryKey: ['mfield', run, m, v, lead], queryFn: () => api.modelField(run, m!, v, lead), enabled: !!m, placeholderData: keep })
export const useWeights = (run: string, v: VarId, lead: number) =>
  useQuery({ queryKey: ['weights', run, v, lead], queryFn: () => api.weights(run, v, lead), placeholderData: keep })
export const useScorecard = (run: string) => useQuery({ queryKey: ['scorecard', run], queryFn: () => api.scorecard(run) })
export const useExtremes = (run: string, t: ExtremeId, lead: number) =>
  useQuery({ queryKey: ['extremes', run, t, lead], queryFn: () => api.extremes(run, t, lead), placeholderData: keep })
export const useCell = (run: string, v: VarId, lead: number, cell: [number, number] | null) =>
  useQuery({
    queryKey: ['cell', run, v, lead, cell?.[0], cell?.[1]],
    queryFn: () => api.cell(run, v, lead, cell![0], cell![1]),
    enabled: !!cell,
    placeholderData: keep,
  })
export const useMeteogram = (run: string, cell: [number, number] | null) =>
  useQuery({
    queryKey: ['meteogram', run, cell?.[0], cell?.[1]],
    queryFn: () => api.meteogram(run, cell![0], cell![1]),
    enabled: !!cell,
    placeholderData: keep,
  })
export const useSource = () => useQuery({ queryKey: ['source'], queryFn: source })

/**
 * Warm the cache for the next and previous day of what is on screen, so scrubbing the timeline or pressing play
 * never waits on the network. Only the layers visible now are fetched.
 */
export function usePrefetchLeads(run: string, lead: number, parts: { field?: VarId; wind?: boolean; weights?: VarId; extreme?: ExtremeId }) {
  const qc = useQueryClient()
  const { field, wind, weights, extreme } = parts
  useEffect(() => {
    const t = setTimeout(() => {
      for (const L of [lead + 1, lead - 1, lead + 2]) {
        if (L < 1 || L > 10) continue
        if (field) qc.prefetchQuery({ queryKey: ['field', run, field, L], queryFn: () => api.field(run, field, L) })
        if (wind && field !== 'wind') qc.prefetchQuery({ queryKey: ['field', run, 'wind', L], queryFn: () => api.field(run, 'wind', L) })
        if (weights) qc.prefetchQuery({ queryKey: ['weights', run, weights, L], queryFn: () => api.weights(run, weights, L) })
        if (extreme) qc.prefetchQuery({ queryKey: ['extremes', run, extreme, L], queryFn: () => api.extremes(run, extreme, L) })
      }
    }, 150)
    return () => clearTimeout(t)
  }, [qc, run, lead, field, wind, weights, extreme])
}

/**
 * Where the numbers on screen come from: 'local' (built-in synthetic source, no engine), 'demo' (engine connected,
 * serving generated demo bundles) or 'measured' (engine output). Anything but 'measured' is stamped on screen.
 */
export function useProvenance(run: string): 'local' | 'demo' | 'measured' | undefined {
  const src = useSource().data
  const r = useRun(run).data
  if (!src) return undefined
  if (src !== 'http') return 'local'
  return r?.provenance === 'measured' ? 'measured' : 'demo'
}

/** Stamp text for maps and charts: null for engine output, else what the numbers are. */
export function useStamp(run: string, local = 'SYNTHETIC DATA'): string | null {
  const p = useProvenance(run)
  return p === 'measured' || p === undefined ? null : p === 'demo' ? 'DEMO DATA' : local
}
