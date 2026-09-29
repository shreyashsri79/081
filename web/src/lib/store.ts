import { create } from 'zustand'
import type { ExtremeId, Grid, ModelId, VarId } from './contract'
import type { Fly } from '@/components/WeatherMap'

/** What the map explorer is colouring: a forecast variable, the weights, or an extreme. */
export type MapLayerId = VarId | 'dominant' | ExtremeId

export interface Overlays { particles: boolean; isobars: boolean; cities: boolean; smooth: boolean; basemap: boolean }

interface Desk {
  run: string
  v: VarId
  lead: number
  /** Selected grid cell [i, j]; drives the meteogram and the inspector. Indices into `grid`. */
  cell: [number, number] | null
  /** The grid `cell` refers to; null until the first run loads (then `cell` is placed at START). */
  grid: Grid | null
  /** Weights screen: 'dominant' or one model's weight map. */
  weightView: 'dominant' | ModelId
  /** Forecast screen: blended field, or one raw member for comparison. */
  member: ModelId | null
  extreme: ExtremeId
  layer: MapLayerId
  overlays: Overlays
  drawer: boolean
  fly: Fly | null
  set: (p: Partial<Omit<Desk, 'set'>>) => void
}

/** First selected point: 20.0° N, 74.0° E, the Western Ghats edge, where the weights are most interesting. */
export const START = { lat: 20.0, lon: 74.0 }

/** `?run=live-20260929` in the URL opens that run (handy for demos); otherwise the monsoon hindcast. */
const urlRun = typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('run') : null

export const useDesk = create<Desk>((set) => ({
  run: urlRun ?? 'hindcast-20200715',
  v: 'rain',
  lead: 3,
  cell: null,
  grid: null,
  weightView: 'dominant',
  member: null,
  extreme: 'rain_p95',
  layer: 'rain',
  overlays: { particles: true, isobars: false, cities: true, smooth: true, basemap: true },
  // Open beside the map on wide screens; on a phone it would cover the map, so start closed.
  drawer: typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches,
  fly: null,
  set: (p) => set(p),
}))
