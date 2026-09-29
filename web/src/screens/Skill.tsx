import { useState } from 'react'
import { Panel, Swatch, VarPicker } from '@/components/Controls'
import LeadChart from '@/components/charts/LeadChart'
import { useRun, useScorecard, useSource } from '@/lib/api'
import type { VarId } from '@/lib/contract'
import { cellColour, refRmse, verdict, type Ref } from '@/lib/score'
import { BLEND_COLOUR, MODELS, VARS } from '@/lib/models'
import { useDesk } from '@/lib/store'
import { cn } from '@/lib/utils'

/**
 * Outcome 3, after the WeatherBench 2 scorecard: blend RMSE against a chosen
 * reference, per variable and lead. Green = blend better, red = worse, grey =
 * the 95 % block-bootstrap CI includes zero, so no claim is made.
 */
export default function Skill() {
  const { run, v, lead, set } = useDesk()
  const r = useRun(run).data
  const sc = useScorecard(run).data
  const synthetic = useSource().data !== 'http'
  const [ref, setRef] = useState<Ref>('best')
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  if (!r || !sc) return null

  const leads = r.leads
  const vars = r.vars
  const rowsFor = (x: VarId) => sc.rows.filter((row) => row.var === x)
  const refs: { id: Ref; label: string }[] = [
    { id: 'best', label: 'Best single (B0)' },
    { id: 'b1', label: 'Equal mean (B1)' },
    ...r.models.map((m) => ({ id: m as Ref, label: MODELS[m].short })),
  ]
  const toggle = (id: string) => setHidden((h) => { const n = new Set(h); if (n.has(id)) n.delete(id); else n.add(id); return n })

  const vr = rowsFor(v)
  const models = r.modelsByVar[v]
  const series = [
    ...models.map((m) => ({ id: m, label: MODELS[m].short, colour: MODELS[m].colour, values: vr.map((x) => x.rmse[m]!) })),
    { id: 'b1', label: 'Equal mean', colour: '#9a948a', values: vr.map((x) => x.rmse.b1!) },
    { id: 'blend', label: `Blend (${r.rung})`, colour: BLEND_COLOUR, values: vr.map((x) => x.rmse.blend!), emphasis: true },
  ]
  const regions = sc.regions.filter((x) => x.var === v)
  const span = Math.max(...regions.map((x) => Math.max(Math.abs(x.ci[0]), Math.abs(x.ci[1])))) || 1

  return (
    <div className="grid gap-3 p-3 sm:p-4">
      <Panel
        label="Scorecard · blend RMSE vs reference"
        right={
          <>
            {synthetic && <span className="border border-bad px-1.5 py-0.5 mono text-[10.5px] tracking-wider text-bad">SYNTHETIC · NOT A RESULT</span>}
            <label className="flex items-center gap-2 text-[12.5px]">
              <span className="text-ink-3">vs</span>
              <select value={ref} onChange={(e) => setRef(e.target.value as Ref)} className="frame bg-surface px-2 py-1 text-[12.5px]">
                {refs.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
              </select>
            </label>
          </>
        }
      >
        <div className="overflow-x-auto p-3 scroll-thin">
          <table className="w-full min-w-[720px] border-collapse text-[12.5px]">
            <thead>
              <tr>
                <th className="w-44 pb-1.5 text-left text-[11px] font-medium text-ink-3">Variable</th>
                {leads.map((L) => (
                  <th key={L} className={cn('pb-1.5 text-center mono text-[11px] font-medium', L === lead ? 'text-ink' : 'text-ink-3')}>D{L}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {vars.map((x) => (
                <tr key={x}>
                  <td className="py-0.5 pr-2">
                    <button type="button" onClick={() => set({ v: x })} className={cn('text-left hover:underline', x === v ? 'font-semibold' : 'text-ink-2')}>
                      {VARS[x].name}
                    </button>
                    <div className="text-[10.5px] text-ink-3">{r.modelsByVar[x].map((m) => MODELS[m].short).join(' · ')}</div>
                  </td>
                  {rowsFor(x).map((row) => {
                    const vd = verdict(row, ref)
                    return (
                      <td key={row.lead} className="p-0.5">
                        {vd ? (
                          <button
                            type="button"
                            onClick={() => set({ v: x, lead: row.lead })}
                            className={cn('flex h-11 w-full flex-col items-center justify-center mono text-[12px]', x === v && row.lead === lead && 'outline outline-2 outline-ink')}
                            style={cellColour(vd.pct, vd.sig)}
                            title={`Blend ${row.rmse.blend!.toFixed(2)} vs ${refRmse(row, ref)!.toFixed(2)} ${VARS[x].units} RMSE${ref === 'best' ? ` (best: ${MODELS[row.best].short})` : ''}; 95% CI of Δ [${row.ci[0].toFixed(2)}, ${row.ci[1].toFixed(2)}]`}
                          >
                            <span className="font-medium">{vd.pct > 0 ? '+' : ''}{vd.pct.toFixed(1)}%</span>
                            {ref === 'best' && <span className="text-[9.5px] opacity-75">{MODELS[row.best].short}</span>}
                          </button>
                        ) : <div className="flex h-11 items-center justify-center text-[11px] text-ink-3 hatch">n/a</div>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-ink-2">
            <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-4" style={{ background: 'rgb(47 125 90 / .75)' }} />blend lower RMSE</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-4" style={{ background: 'rgb(196 52 42 / .75)' }} />blend higher RMSE</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-4 bg-[#ece9e4]" />95 % CI includes 0: no claim</span>
            <span className="ml-auto text-ink-3">{sc.validation}</span>
          </div>
        </div>
      </Panel>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_380px]">
        <Panel label={`RMSE by lead · ${VARS[v].name}`} right={<VarPicker value={v} onChange={(x) => set({ v: x })} />}>
          <div className="flex flex-wrap gap-x-3 gap-y-1 px-3 pt-2">
            {series.map((s) => <Swatch key={s.id} colour={s.colour} label={s.label} muted={hidden.has(s.id)} onClick={s.emphasis ? undefined : () => toggle(s.id)} />)}
          </div>
          <div className="p-2">
            <LeadChart leads={leads} series={series} hidden={hidden} current={lead} onLead={(L) => set({ lead: L })} units={`${VARS[v].units} RMSE`} digits={2} height={260} />
          </div>
        </Panel>
        <Panel label={`By region · Day 3 · ${VARS[v].short}`}>
          <div className="flex flex-col gap-2 p-3">
            {regions.map((x) => {
              const sig = x.ci[1] < 0 || x.ci[0] > 0
              const pos = (d: number) => 50 + (d / span) * 48
              return (
                <div key={x.name} className="grid grid-cols-[110px_1fr_52px] items-center gap-2 text-[12.5px]">
                  <span className="text-ink-2">{x.name}</span>
                  <div className="relative h-5 bg-paper">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-ink-3" />
                    <div className="absolute top-1/2 h-px" style={{ left: `${pos(x.ci[0])}%`, width: `${pos(x.ci[1]) - pos(x.ci[0])}%`, background: '#0e2129' }} />
                    <div className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2" style={{ left: `${pos(x.delta)}%`, background: !sig ? '#7a878c' : x.delta < 0 ? '#2f7d5a' : '#c4342a' }} />
                  </div>
                  <span className="text-right mono text-[11.5px]">{x.delta > 0 ? '+' : ''}{x.delta.toFixed(2)}</span>
                </div>
              )
            })}
            <p className="mt-1 text-[11.5px] text-ink-3">Blend − best single model RMSE ({VARS[v].units}), with 95 % CI. Left of the line = blend better.</p>
          </div>
        </Panel>
      </div>
    </div>
  )
}
