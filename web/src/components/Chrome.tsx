import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { ChevronDown, Info } from 'lucide-react'
import { useProvenance, useRun, useRuns } from '@/lib/api'
import { useDesk } from '@/lib/store'
import { MODELS } from '@/lib/models'
import { cn } from '@/lib/utils'

export const BRAND = 'Samanvay'

const NAV = [
  { to: '/forecast', label: 'Forecast' },
  { to: '/weights', label: 'Weights' },
  { to: '/skill', label: 'Skill' },
  { to: '/extremes', label: 'Extremes' },
  { to: '/runs', label: 'Run log' },
  { to: '/data', label: 'Data & models' },
]

function Mark() {
  // Four model hues in one framed square: the blend, as a glyph.
  return (
    <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
      <rect x="2" y="2" width="10" height="10" fill="#0072b2" />
      <rect x="12" y="2" width="10" height="10" fill="#e69f00" />
      <rect x="2" y="12" width="10" height="10" fill="#009e73" />
      <rect x="12" y="12" width="10" height="10" fill="#cc79a7" />
      <rect x="2" y="2" width="20" height="20" fill="none" stroke="#0e2129" strokeWidth="1.5" />
    </svg>
  )
}

export function Masthead({ desk }: { desk: boolean }) {
  const { run, set } = useDesk()
  const runs = useRuns().data ?? []
  return (
    <header className="sticky top-0 z-40 border-b border-ink bg-paper">
      <div className="flex flex-wrap items-center gap-x-4 px-4 sm:px-6 md:h-14 md:flex-nowrap">
        <NavLink to="/" className="flex h-12 items-center gap-2 md:h-auto">
          <Mark />
          <span className="text-[17px] font-semibold tracking-[-0.02em]">{BRAND}</span>
          <span className="hidden mono text-[11px] text-ink-3 xl:inline">PS26081 · NCMRWF</span>
        </NavLink>
        <nav aria-label="Primary" className="order-last -mx-2 flex w-full items-center overflow-x-auto pb-2 md:order-none md:mx-0 md:ml-2 md:w-auto md:pb-0">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end
              className={({ isActive }) =>
                cn(
                  'relative whitespace-nowrap px-2.5 py-1.5 text-[14px] font-medium text-ink-2 hover:text-ink',
                  isActive && 'text-ink after:absolute after:inset-x-2.5 after:bottom-0 after:h-[2px] after:bg-ink md:after:-bottom-[9px]',
                )
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        {desk ? <label className="relative ml-auto flex min-w-0 items-center">
          <span className="sr-only">Run</span>
          <select
            value={run}
            onChange={(e) => set({ run: e.target.value, member: null })}
            className="frame w-full max-w-[260px] appearance-none truncate bg-surface py-1.5 pl-2.5 pr-8 mono text-[12px] hover:bg-surface-2 sm:text-[12.5px]"
          >
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.kind === 'live' ? 'LIVE' : 'HINDCAST'} {r.init.slice(0, 10)} 00 UTC{r.status !== 'ok' ? ` · ${r.status}` : ''}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 size-4" />
        </label> : (
          <NavLink to="/forecast" className="btn btn-ink ml-auto">Open desk</NavLink>
        )}
      </div>
    </header>
  )
}

/** Run header: what is on screen, where it came from, under which regime. */
export function RunStrip() {
  const { run } = useDesk()
  const r = useRun(run).data
  const [open, setOpen] = useState(false)
  if (!r) return <div className="h-10 border-b border-rule" />
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-rule bg-surface px-4 py-2 text-[12.5px] sm:px-6">
      <span className="flex items-center gap-1.5">
        <span className={cn('size-2', r.status === 'ok' ? 'bg-good' : r.status === 'partial' ? 'bg-warn' : 'bg-bad')} />
        <span className="mono">{r.kind === 'live' ? 'Live' : 'Hindcast'} · init {r.init.replace('T', ' ').replace('Z', ' UTC')}</span>
      </span>
      <span><span className="text-ink-3">Season</span> <span className="mono">{r.regime.season}</span></span>
      <span><span className="text-ink-3">Regime</span> <span className="font-medium">{r.regime.label}</span> <span className="text-ink-3">({r.regime.basis}-day label)</span></span>
      <span><span className="text-ink-3">Rung</span> <span className="mono">{r.rung}</span></span>
      <span className="flex items-center gap-2">
        <span className="text-ink-3">Models</span>
        {r.models.map((m) => (
          <span key={m} className="flex items-center gap-1">
            <span className="size-2.5" style={{ background: MODELS[m].colour }} />
            <span>{MODELS[m].short}</span>
          </span>
        ))}
      </span>
      <span className="mono text-ink-3">grid {r.grid.step}° · {r.grid.ny}×{r.grid.nx}</span>
      {r.notes?.length ? (
        <span className="relative ml-auto">
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
            className="flex items-center gap-1.5 border border-ink px-2 py-0.5 text-[12px] hover:bg-ink hover:text-paper">
            <Info className="size-3.5" /> Notes ({r.notes.length})
          </button>
          {open && (
            <ul className="frame raised absolute right-0 top-full z-50 mt-1 w-[min(92vw,520px)] bg-surface p-3 text-[12.5px] leading-snug">
              {r.notes.map((n) => <li key={n} className="border-b border-rule/60 py-1.5 last:border-0">{n}</li>)}
            </ul>
          )}
        </span>
      ) : null}
    </div>
  )
}

export function Disclosure() {
  const facts = useLocation().pathname === '/data'
  const { run } = useDesk()
  const runs = useRuns().data ?? []
  const prov = useProvenance(run)
  const synthetic = prov !== 'measured'
  const notes = useRun(run).data?.notes
  const note = notes?.find((n) => !n.startsWith('DEMO')) ?? notes?.[0]
  return (
    <div role="note" className="fixed inset-x-0 bottom-0 z-50 flex h-8 items-center gap-3 overflow-hidden bg-ink px-4 text-paper sm:px-6">
      <span className={cn('shrink-0 mono text-[11px] font-medium tracking-wider', synthetic && !facts ? 'text-[#f0a58f]' : 'text-[#9fd3b6]')}>
        {facts ? 'VERIFIED 28 SEP' : prov === 'demo' ? 'DEMO DATA' : synthetic ? 'SYNTHETIC DATA' : 'ENGINE CONNECTED'}
      </span>
      <p className="truncate text-[12px] text-[#d9dfe1]">
        {facts
          ? 'Facts on this page come from the WeatherBench 2 store check of 28 Sep 2026. Desk screens run on synthetic data until the engine is connected.'
          : prov === 'demo'
          ? `Engine connected, serving ${runs.length} demo run${runs.length === 1 ? '' : 's'}: generated inputs through the real pipeline. Not WeatherBench 2 forecasts; real bundles replace these.`
          : synthetic
          ? 'No engine output yet. Every field, weight and score on screen is generated for interface development. It is not a forecast and not a result. Do not screenshot for the deck.'
          : `measured · ${runs.length} run${runs.length === 1 ? '' : 's'} from blend/server.py${note ? ` · ${note}` : ''}`}
      </p>
    </div>
  )
}
