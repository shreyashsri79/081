import { useState } from 'react'
import type { VarId } from '@/lib/contract'
import { useMeteogram, useRun } from '@/lib/api'
import { useDesk } from '@/lib/store'
import { BLEND_COLOUR, MODELS, VARS } from '@/lib/models'
import { STATES, fmtLat, fmtLon, stateAt } from '@/lib/geo'
import LeadChart, { WeightStrip } from './charts/LeadChart'
import { Swatch } from './Controls'

/**
 * MultiModel meteogram for the selected cell (after meteoblue): every model,
 * every variable, Day 1–10, with the blend in ink. Dot size and the strip
 * under each panel are the blend weights, so "who was trusted when" reads
 * straight off the chart.
 */
export default function Meteogram({ vars = ['rain', 't2m', 'wind', 'mslp'], compact }: { vars?: VarId[]; compact?: boolean }) {
  const { run, cell, lead, v: active, set } = useDesk()
  const r = useRun(run).data
  const mg = useMeteogram(run, cell).data
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  if (!cell) return <p className="p-4 text-[13px] text-ink-3">Click a cell on the map.</p>
  if (!mg || !r) return <div className="h-40" />

  const toggle = (id: string) => setHidden((h) => { const n = new Set(h); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const si = stateAt(mg.lon, mg.lat)

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-rule px-3 py-2">
        <span className="mono text-[13px] font-medium">{fmtLat(mg.lat)} {fmtLon(mg.lon)}</span>
        <span className="text-[12.5px] text-ink-2">{si >= 0 ? STATES[si].name : 'outside India'}</span>
        <span className="mono text-[11px] text-ink-3">cell {cell[0]},{cell[1]}</span>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 border-b border-rule px-3 py-2">
        <Swatch colour={BLEND_COLOUR} label="Blend" />
        {r.models.map((m) => (
          <Swatch key={m} colour={MODELS[m].colour} label={MODELS[m].short} muted={hidden.has(m)} onClick={() => toggle(m)} />
        ))}
        <span className="ml-auto text-[11px] text-ink-3">dot size = weight</span>
      </div>
      {mg.vars.filter((x) => vars.includes(x.var)).map((x) => {
        const info = VARS[x.var]
        const series = [
          ...x.members.map((m) => ({ id: m.model, label: MODELS[m.model].short, colour: MODELS[m.model].colour, values: m.values, weights: m.weights })),
          { id: 'blend', label: 'Blend', colour: BLEND_COLOUR, values: x.blend, emphasis: true },
        ]
        return (
          <div key={x.var} className={x.var === active ? 'bg-paper/60' : ''}>
            <button type="button" onClick={() => set({ v: x.var })} className="flex w-full items-baseline gap-2 px-3 pt-2 text-left">
              <span className={`text-[12.5px] font-semibold ${x.var === active ? '' : 'text-ink-2'}`}>{info.name}</span>
              <span className="mono text-[11px] text-ink-3">blend D{lead} {x.blend[mg.leads.indexOf(lead)]?.toFixed(info.digits)} {info.units}</span>
              {x.var === 'rain' && r.modelsByVar.rain.length < r.models.length && (
                <span className="ml-auto text-[10.5px] text-ink-3">
                  {r.models.filter((m) => !r.modelsByVar.rain.includes(m)).map((m) => MODELS[m].short).join(', ')}: no precipitation output
                </span>
              )}
            </button>
            <LeadChart
              leads={mg.leads}
              series={series}
              hidden={hidden}
              current={lead}
              onLead={(L) => set({ lead: L })}
              units={info.units}
              digits={info.digits}
              bars={x.var === 'rain'}
              spread={x.var !== 'rain'}
              height={compact ? 110 : 132}
            />
            <div className="px-0 pb-2">
              <WeightStrip leads={mg.leads} current={lead}
                members={x.members.map((m) => ({ id: m.model, colour: MODELS[m.model].colour, weights: m.weights }))} />
            </div>
          </div>
        )
      })}
    </div>
  )
}
