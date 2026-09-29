import { Panel } from '@/components/Controls'
import { useRun, useRuns } from '@/lib/api'
import { MODELS } from '@/lib/models'
import { useDesk } from '@/lib/store'
import { cn } from '@/lib/utils'

const DOT = { ok: 'bg-good', partial: 'bg-warn', failed: 'bg-bad', skipped: 'bg-ink-3' } as const

/** Outcome 5: the routine run, and what failed in it. Operational trust. */
export default function RunLog() {
  const { run, set } = useDesk()
  const runs = useRuns().data ?? []
  const r = useRun(run).data

  return (
    <div className="grid gap-3 p-3 sm:p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Panel label="Runs">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-rule text-left text-[11px] text-ink-3">
              <th className="px-3 py-1.5 font-medium">Init</th>
              <th className="py-1.5 font-medium">Kind</th>
              <th className="py-1.5 font-medium">Models</th>
              <th className="px-3 py-1.5 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((x) => (
              <tr key={x.id} onClick={() => set({ run: x.id, member: null })}
                className={cn('cursor-pointer border-b border-rule/60 hover:bg-paper', x.id === run && 'bg-paper')}>
                <td className="px-3 py-2 mono">{x.init.replace('T', ' ').replace('Z', ' UTC')}</td>
                <td className="py-2">{x.kind}</td>
                <td className="py-2">
                  <span className="flex flex-wrap gap-2">
                    {x.models.map((m) => (
                      <span key={m} className="flex items-center gap-1 text-[12px]">
                        <span className="inline-block size-2" style={{ background: MODELS[m].colour }} />{MODELS[m].short}
                      </span>
                    ))}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className="flex items-center gap-1.5"><span className={cn('size-2', DOT[x.status])} />{x.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="px-3 py-2 text-[11.5px] text-ink-3">Live runs: 15:00 IST daily (GitHub Actions) from ECMWF open data (IFS, AIFS) and NOAA GFS; each checks the earlier live forecasts against the analysis. Hindcasts: WeatherBench 2.</p>
      </Panel>
      <Panel label={r ? `Steps · ${r.id}` : 'Steps'}>
        {r && (
          <ol className="flex flex-col">
            {r.steps.map((s, k) => (
              <li key={s.name} className="grid grid-cols-[24px_1fr_auto] items-start gap-2 border-b border-rule/60 px-3 py-2 text-[13px]">
                <span className="mono text-[11px] text-ink-3">{String(k + 1).padStart(2, '0')}</span>
                <span>
                  <span className="flex items-center gap-1.5"><span className={cn('size-2', DOT[s.status])} />{s.name}</span>
                  {s.note && <span className="mt-0.5 block text-[12px] text-warn">{s.note}</span>}
                </span>
                <span className="mono text-[12px] text-ink-2">{s.seconds} s</span>
              </li>
            ))}
            <li className="flex justify-between px-3 py-2 text-[12px] text-ink-3">
              <span>total</span>
              <span className="mono">{r.steps.reduce((a, s) => a + s.seconds, 0)} s</span>
            </li>
          </ol>
        )}
      </Panel>
    </div>
  )
}
