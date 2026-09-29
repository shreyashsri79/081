import { useEffect } from 'react'
import type { Grid } from './contract'
import { useEvents, useRun, useRuns } from './api'
import { START, useDesk } from './store'

const same = (a: Grid | null, b: Grid) =>
  !!a && a.lat0 === b.lat0 && a.lon0 === b.lon0 && a.step === b.step && a.ny === b.ny && a.nx === b.nx

/**
 * Keeps the desk state valid for whatever the data source holds:
 * - the selected run exists (the engine may not have the synthetic default id);
 * - the selected cell points at the same place when the grid changes (0.5° synthetic -> 1.5° engine).
 */
export function useDeskSync() {
  const { run, cell, grid, extreme, layer, set } = useDesk()
  const runs = useRuns().data
  const r = useRun(run).data
  const events = useEvents(run)

  // extreme events differ between sources and runs: keep the selection on one this run has
  useEffect(() => {
    if (!r || !events.length) return
    const ids = events.map((e) => e.id)
    const first = events.find((e) => e.available)?.id ?? ids[0]
    const isEvent = !['rain', 't2m', 'wind', 'mslp', 'dominant'].includes(layer)
    if (!ids.includes(extreme) || (isEvent && !ids.includes(layer)))
      set({ extreme: ids.includes(extreme) ? extreme : first, ...(isEvent && !ids.includes(layer) ? { layer: first } : {}) })
  }, [r, events, extreme, layer, set])

  useEffect(() => {
    if (runs?.length && !runs.some((x) => x.id === run)) set({ run: runs[0].id, member: null })
  }, [runs, run, set])

  useEffect(() => {
    const g = r?.grid
    if (!g || same(grid, g)) return
    const p = grid && cell ? { lat: grid.lat0 + cell[0] * grid.step, lon: grid.lon0 + cell[1] * grid.step } : START
    const clamp = (x: number, n: number) => Math.min(n - 1, Math.max(0, x))
    set({
      grid: g,
      cell: [clamp(Math.round((p.lat - g.lat0) / g.step), g.ny), clamp(Math.round((p.lon - g.lon0) / g.step), g.nx)],
    })
  }, [r, grid, cell, set])
}
