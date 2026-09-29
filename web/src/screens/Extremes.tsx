import WeatherMap from '@/components/WeatherMap'
import { LeadSlider, Legend, Panel } from '@/components/Controls'
import { useExtremes, useRun, useSource } from '@/lib/api'
import { PROB, css, sample } from '@/lib/colour'
import type { ExtremeId } from '@/lib/contract'
import { EXTREMES } from '@/lib/models'
import { useDesk } from '@/lib/store'

const TYPES: ExtremeId[] = ['rain64', 'rain115', 'rain204', 'heat', 'wind15']

/**
 * Outcome 4: extremes as probabilities, never read off the blended mean
 * (averaging smooths peaks away, C7). State roll-up = max cell probability.
 */
export default function Extremes() {
  const { run, lead, cell, extreme, set } = useDesk()
  const r = useRun(run).data
  const x = useExtremes(run, extreme, lead).data
  const synthetic = useSource().data !== 'http'
  const offSeason = r && ((extreme === 'heat' && r.regime.season !== 'MAM') || (extreme.startsWith('rain') && r.regime.season === 'MAM'))

  return (
    <div className="grid gap-3 p-3 sm:p-4 xl:grid-cols-[minmax(0,1fr)_380px]">
      <Panel
        label={`${EXTREMES[extreme].name} · probability`}
        right={
          <div className="seg flex-wrap" role="group" aria-label="Indicator">
            {TYPES.map((t) => (
              <button key={t} type="button" aria-pressed={extreme === t} onClick={() => set({ extreme: t })} title={EXTREMES[t].threshold}>
                {EXTREMES[t].short}
              </button>
            ))}
          </div>
        }
      >
        <div className="flex flex-col gap-3 p-3">
          <div className="flex flex-wrap items-baseline gap-x-3 text-[12.5px]">
            <span className="mono">{EXTREMES[extreme].threshold}</span>
            <span className="text-ink-3">Weighted exceedance of quantile-mapped members, calibrated. Not thresholded from the blend mean.</span>
          </div>
          {offSeason && (
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
                stamp={synthetic ? 'SYNTHETIC' : undefined}
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
