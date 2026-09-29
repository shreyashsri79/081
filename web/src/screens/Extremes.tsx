import WeatherMap from '@/components/WeatherMap'
import { LeadSlider, Legend, Panel } from '@/components/Controls'
import { useEvents, useExtremes, useRun, useStamp } from '@/lib/api'
import { PROB, css, sample } from '@/lib/colour'
import { useDesk } from '@/lib/store'

/**
 * Outcome 4: extremes as probabilities, never read off the blended mean
 * (averaging smooths peaks away, C7). State roll-up = max cell probability.
 */
export default function Extremes() {
  const { run, lead, cell, extreme, set } = useDesk()
  const r = useRun(run).data
  const stamp = useStamp(run)
  const events = useEvents(run)
  const ev = events.find((e) => e.id === extreme) ?? events[0]
  const x = useExtremes(run, ev?.id, lead).data
  const offSeason = r && ev && ((ev.var === 't2m' && r.regime.season !== 'MAM') || (ev.var === 'rain' && r.regime.season === 'MAM'))

  return (
    <div className="grid gap-3 p-3 sm:p-4 xl:grid-cols-[minmax(0,1fr)_380px]">
      <Panel
        label={`${ev?.name ?? 'Extreme'} · probability`}
        right={
          <div className="seg flex-wrap" role="group" aria-label="Indicator">
            {events.map((e) => (
              <button key={e.id} type="button" aria-pressed={extreme === e.id} onClick={() => set({ extreme: e.id })} title={e.threshold}>
                {e.short}
              </button>
            ))}
          </div>
        }
      >
        <div className="flex flex-col gap-3 p-3">
          <div className="flex flex-wrap items-baseline gap-x-3 text-[12.5px]">
            <span className="mono">{ev?.threshold}</span>
            <span className="text-ink-3">
              {x?.method ? `${x.method[0].toUpperCase()}${x.method.slice(1)}.` : 'Weighted exceedance of members (illustrative).'} Not thresholded from the blend mean.
            </span>
            {x?.calibrated === false && <span className="border border-warn px-1.5 py-0.5 mono text-[10.5px] text-warn">UNCALIBRATED</span>}
            {x?.calibrated && <span className="border border-good px-1.5 py-0.5 mono text-[10.5px] text-good">CALIBRATED</span>}
          </div>
          {x?.available === false && (
            <p className="border border-warn bg-warn-bg px-3 py-1.5 text-[12.5px] text-warn">{x.note ?? 'Not available for this run.'}</p>
          )}
          {x?.available !== false && x?.note && <p className="text-[12px] text-ink-3">{x.note}</p>}
          {x?.available !== false && offSeason && (
            <p className="border border-warn bg-warn-bg px-3 py-1.5 text-[12.5px] text-warn">
              Out of season for this run ({r?.regime.season}). Low probabilities here are expected, not a fault.
            </p>
          )}
          <div className="aspect-[0.95] w-full md:aspect-auto md:h-[min(64vh,600px)]">
            {r && x && (
              <WeatherMap
                grid={r.grid}
                layer={{ kind: 'scalar', values: x.prob, scale: PROB }}
                layerKey={`${run}|${extreme}|${lead}`}
                cities
                cityValue={(k) => `${Math.round(x.prob[k] * 100)}%`}
                selected={cell}
                onSelect={(c) => set({ cell: c })}
                stamp={stamp ?? undefined}
                readout={(k) => <div className="mono text-[13px] font-medium">p = {(x.prob[k] * 100).toFixed(0)}%</div>}
              />
            )}
          </div>
          <Legend scale={PROB} units="probability" format={(v) => `${Math.round(v * 100)}%`} />
          <LeadSlider />
        </div>
      </Panel>
      <Panel label={`States · Day ${lead}`}>
        <div className="max-h-[calc(100dvh-220px)] overflow-y-auto scroll-thin">
          <table className="w-full text-[12.5px]">
            <thead className="sticky top-0 bg-surface">
              <tr className="border-b border-rule text-left text-[11px] text-ink-3">
                <th className="px-3 py-1.5 font-medium">State</th>
                <th className="py-1.5 text-right font-medium">max</th>
                <th className="px-3 py-1.5 text-right font-medium">mean</th>
              </tr>
            </thead>
            <tbody>
              {x?.states.map((s) => (
                <tr key={s.name} className="border-b border-rule/60">
                  <td className="px-3 py-1.5">{s.name}</td>
                  <td className="py-1.5 text-right">
                    <span className="inline-flex items-center gap-2">
                      <span className="inline-block h-2.5 w-2.5" style={{ background: css(sample(PROB, s.pmax)) }} />
                      <span className="mono w-9">{(s.pmax * 100).toFixed(0)}%</span>
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-right mono text-ink-2">{(s.pmean * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-3 py-2 text-[11.5px] text-ink-3">District roll-up needs a district boundary file; states for the MVP.</p>
        </div>
      </Panel>
    </div>
  )
}
