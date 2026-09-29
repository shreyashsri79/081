import { create } from 'zustand'
import type { ExtremeId, ModelId, VarId } from './contract'
import type { Fly } from '@/components/WeatherMap'

/** What the map explorer is colouring: a forecast variable, the weights, or an extreme. */
export type MapLayerId = VarId | 'dominant' | ExtremeId

export interface Overlays { particles: boolean; isobars: boolean; cities: boolean; smooth: boolean; basemap: boolean }

interface Desk {
  run: string
  v: VarId
  lead: number
  /** Selected grid cell [i, j]; drives the meteogram and the inspector. */
  cell: [number, number] | null
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

export const useDesk = create<Desk>((set) => ({
  run: 'hindcast-20200715',
  v: 'rain',
  lead: 3,
  cell: [30, 18], // 20.0° N, 74.0° E — the Western Ghats edge, where the weights are most interesting
  weightView: 'dominant',
  member: null,
  extreme: 'rain64',
  layer: 'rain',
  overlays: { particles: true, isobars: false, cities: true, smooth: true, basemap: true },
  // Open beside the map on wide screens; on a phone it would cover the map, so start closed.
  drawer: typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches,
  fly: null,
  set: (p) => set(p),
}))
