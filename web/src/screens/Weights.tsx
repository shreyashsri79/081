import { useMemo } from 'react'
import WeatherMap from '@/components/WeatherMap'
import { LeadSlider, Panel, VarPicker } from '@/components/Controls'
import LeadChart, { WeightStrip } from '@/components/charts/LeadChart'
import { useCell, useMeteogram, useRun, useStamp, useWeights } from '@/lib/api'
import { hexToRgb } from '@/lib/colour'
import { PAPER, dominantPaint, mix } from '@/lib/paint'
import type { ModelId } from '@/lib/contract'
import { MODELS, VARS } from '@/lib/models'
import { useDesk } from '@/lib/store'
import { cn } from '@/lib/utils'

/**
 * Outcome 2: who the blend trusted, where. Dominant view colours each cell by
 * its largest weight, faded by how decisive that weight is; the per-model
 * view shows one model's weight from 0 to 1.
 */
export default function Weights() {
  const { run, v, lead, cell, weightView, set } = useDesk()
  const r = useRun(run).data
  const ws = useWeights(run, v, lead).data
  const rep = useCell(run, v, lead, cell).data
  const mg = useMeteogram(run, cell).data
  const stamp = useStamp(run)
  const view = ws && weightView !== 'dominant' && !ws.models.includes(weightView) ? 'dominant' : weightView

  const paint = useMemo(() => {
    if (!ws) return () => null
    if (view === 'dominant') return dominantPaint(ws)
    const cols = ws.models.map((m) => hexToRgb(MODELS[m].colour))
    const a = ws.models.indexOf(view as ModelId)
    return (k: number) => mix(cols[a], Math.min(1, ws.weights[a][k] * 1.25))
  }, [ws, view])

  const vm = mg?.vars.find((x) => x.var === v)

  return (
    <div className="grid gap-3 p-3 sm:p-4 xl:grid-cols-[minmax(0,1fr)_420px]">
      <Panel label="Weight map" right={<VarPicker value={v} onChange={(x) => set({ v: x })} />}>
        <div className="flex flex-col gap-3 p-3">
          <div className="seg flex-wrap" role="group" aria-label="View">
            <button type="button" aria-pressed={view === 'dominant'} onClick={() => set({ weightView: 'dominant' })}>Dominant model</button>
            {r?.models.map((m) => {
              const has = ws?.models.includes(m)
              return (
                <button key={m} type="button" disabled={!has} aria-pressed={view === m} onClick={() => set({ weightView: m })}
                  title={has ? undefined : `${MODELS[m].name} has no ${VARS[v].name.toLowerCase()} output`}>
                  <span className="mr-1 inline-block size-2" style={{ background: MODELS[m].colour }} />
                  {MODELS[m].short}
                </button>
              )
            })}
          </div>
          <div className="aspect-[0.95] w-full md:aspect-auto md:h-[min(66vh,620px)]">
            {r && ws && (
              <WeatherMap
                grid={r.grid}
                layer={{ kind: 'paint', paint }}
                layerKey={`${run}|${v}|${lead}|${view}`}
                smooth={false}
                cities
                cityValue={(k) => (view === 'dominant' ? MODELS[ws.models[ws.dominant[k]]].short : ws.weights[ws.models.indexOf(view as ModelId)][k].toFixed(2))}
                selected={cell}
                onSelect={(c) => set({ cell: c })}
                stamp={stamp ?? undefined}
                readout={(k) => (
                  <div className="mt-0.5 flex flex-col gap-0.5">
                    {ws.models.map((m, a) => (
                      <div key={m} className="flex items-center gap-1.5 text-[12px]">
                        <span className="inline-block h-2 w-2.5" style={{ background: MODELS[m].colour }} />
                        <span className={cn(ws.dominant[k] === a && 'font-semibold')}>{MODELS[m].short}</span>
                        <span className="ml-auto pl-4 mono">{ws.weights[a][k].toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                )}
              />
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
            {view === 'dominant'
              ? <>
                  {ws?.models.map((m) => (
                    <span key={m} className="flex items-center gap-1.5">
                      <span className="inline-block h-2.5 w-7" style={{ background: `linear-gradient(90deg, rgb(${mix(hexToRgb(MODELS[m].colour), 0.18).join(' ')}), ${MODELS[m].colour})` }} />
                      {MODELS[m].short}
                    </span>
                  ))}
                  <span className="text-ink-3">pale = near-equal weights, full = one model trusted</span>
                </>
              : <span className="flex items-center gap-2"><span className="mono text-[11px]">0</span><span className="inline-block h-2.5 w-40" style={{ background: `linear-gradient(90deg, rgb(${PAPER.join(' ')}), ${MODELS[view as ModelId].colour})` }} /><span className="mono text-[11px]">0.8+</span><span className="text-ink-3">weight</span></span>}
          </div>
          <LeadSlider />
        </div>
      </Panel>

      <div className="flex flex-col gap-3">
        <Panel label="Why these weights">
          {rep ? (
            <div className="flex flex-col gap-3 p-3 text-[13px]">
              <div className="frame bg-paper px-3 py-2 mono text-[12px] leading-relaxed">
                {r && ['B2c', 'B3c', 'B4'].includes(r.rung)
                  ? <>w = argmin<sub>w</sub> wᵀΣw, w ≥ 0, Σ<sub>m</sub> w<sub>m</sub> = 1</>
                  : <>w<sub>m</sub> = (1 / MSE<sub>m</sub>) / Σ<sub>k</sub> (1 / MSE<sub>k</sub>)</>}
                <div className="font-sans text-[11.5px] text-ink-3">
                  {r && ['B2c', 'B3c', 'B4'].includes(r.rung)
                    ? <>Σ = error covariance between models after bias correction, for this cell and lead: models that make the same mistakes are not double-counted (rung {r.rung})</>
                    : <>MSE after bias correction, for this cell, lead, season and regime (rung {r?.rung})</>}
                </div>
              </div>
              <table className="w-full text-[12.5px]">
                <thead>
                  <tr className="border-b border-rule text-left text-[11px] text-ink-3">
                    <th className="py-1 font-medium">Model</th><th className="text-right font-medium">MSE</th><th className="text-right font-medium">bias</th><th className="text-right font-medium">weight</th>
                  </tr>
                </thead>
                <tbody>
                  {[...rep.members].sort((a, b) => b.weight - a.weight).map((m) => (
                    <tr key={m.model} className="border-b border-rule/60">
                      <td className="py-1.5"><span className="mr-1.5 inline-block h-2 w-2.5" style={{ background: MODELS[m.model].colour }} />{MODELS[m.model].short}</td>
                      <td className="text-right mono">{m.mse.toFixed(2)}</td>
                      <td className="text-right mono">{m.bias > 0 ? '+' : ''}{m.bias.toFixed(1)}</td>
                      <td className="text-right">
                        <span className="inline-flex items-center gap-2">
                          <span className="inline-block h-2" style={{ width: m.weight * 70, background: MODELS[m.model].colour }} />
                          <span className="mono w-9">{m.weight.toFixed(2)}</span>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {r?.kind === 'live' ? (
                <p className="text-[12px] text-ink-2">
                  Live run: the prior is each model&apos;s training counterpart (IFS ← HRES, AIFS ← GraphCast, GFS ← HRES
                  with 1.5× error). As earlier live forecasts are checked against the analysis, their own errors take over:
                  <span className="mono"> Σ = (n·Σ<sub>online</sub> + k·Σ<sub>prior</sub>) / (n + k)</span>, k = <span className="mono">{rep.k}</span> days (B4).
                  MSE and bias above are the values in use.
                </p>
              ) : (
                <p className="text-[12px] text-ink-2">
                  Regime MSE from <span className="mono">{rep.nRegime}</span> cases, shrunk toward the season value
                  (<span className="mono">{rep.nSeason}</span> cases) with k = <span className="mono">{rep.k}</span>:
                  <span className="mono"> MSE = (n·MSE<sub>regime</sub> + k·MSE<sub>season</sub>) / (n + k)</span>.
                  {rep.nRegime < rep.k && <span className="text-warn"> Few regime cases: weights lean on the season.</span>}
                </p>
              )}
            </div>
          ) : <p className="p-4 text-[13px] text-ink-3">Click a cell on the map.</p>}
        </Panel>
        <Panel label={`Weight across lead · ${VARS[v].short}`}>
          {vm && mg ? (
            <div className="pb-2 pt-1">
              <LeadChart
                leads={mg.leads}
                current={lead}
                onLead={(L) => set({ lead: L })}
                units="w"
                digits={2}
                yZero
                height={140}
                series={vm.members.map((m) => ({ id: m.model, label: MODELS[m.model].short, colour: MODELS[m.model].colour, values: m.weights }))}
              />
              <WeightStrip leads={mg.leads} current={lead} height={22}
                members={vm.members.map((m) => ({ id: m.model, colour: MODELS[m.model].colour, weights: m.weights }))} />
            </div>
          ) : <div className="h-40" />}
        </Panel>
      </div>
    </div>
  )
}
