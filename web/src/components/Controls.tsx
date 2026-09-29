import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Pause, Play } from 'lucide-react'
import type { VarId } from '@/lib/contract'
import { css, sample, type Scale } from '@/lib/colour'
import { VARS } from '@/lib/models'
import { useRun } from '@/lib/api'
import { useDesk } from '@/lib/store'
import { cn, validDate } from '@/lib/utils'

/** Width of an element, tracked. Charts draw to real pixels, not a stretched viewBox. */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [w, setW] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

export function Panel({ label, right, children, className }: { label: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn('frame flex min-w-0 flex-col bg-surface', className)}>
      <header className="flex min-h-10 flex-wrap items-center gap-2 border-b border-rule px-3 py-2">
        <h2 className="label">{label}</h2>
        {right && <div className="ml-auto flex flex-wrap items-center gap-2">{right}</div>}
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  )
}

export function VarPicker({ value, onChange, vars = ['rain', 't2m', 'wind', 'mslp'] }: { value: VarId; onChange: (v: VarId) => void; vars?: VarId[] }) {
  return (
    <div className="seg" role="group" aria-label="Variable">
      {vars.map((v) => (
        <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)} title={VARS[v].name}>
          {VARS[v].short}
        </button>
      ))}
    </div>
  )
}

/** Day 1–10 scrubber with play. Lead is the axis of the whole product. */
export function LeadSlider() {
  const { run, lead, set } = useDesk()
  const r = useRun(run).data
  const [playing, setPlaying] = useState(false)
  const leads = r?.leads ?? [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  const max = leads[leads.length - 1]

  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => {
      const cur = useDesk.getState().lead
      useDesk.getState().set({ lead: cur >= max ? leads[0] : cur + 1 })
    }, 900)
    return () => clearInterval(t)
  }, [playing, max, leads])

  return (
    <div className="flex items-center gap-3">
      <button type="button" className="btn btn-line !px-2" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play through leads'}>
        {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
      </button>
      <div className="flex min-w-0 flex-1 flex-col">
        <input
          type="range"
          className="instrument w-full"
          min={leads[0]}
          max={max}
          step={1}
          value={lead}
          onChange={(e) => set({ lead: +e.target.value })}
          aria-label="Lead time in days"
        />
        <div className="mt-1 flex justify-between mono text-[10.5px] text-ink-3">
          {leads.map((L) => (
            <button key={L} type="button" onClick={() => set({ lead: L })} className={cn('w-5 text-center hover:text-ink', L === lead && 'font-medium text-ink')}>
              D{L}
            </button>
          ))}
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="mono text-[15px] font-medium leading-none">Day {lead}</div>
        {r && <div className="mono text-[10.5px] text-ink-3">valid {validDate(r.init, lead)}</div>}
      </div>
    </div>
  )
}

/** Horizontal colour bar with ticks. Stepped scales draw as equal-width bins. */
export function Legend({ scale, units, format = (v) => String(v) }: { scale: Scale; units: string; format?: (v: number) => string }) {
  const stops = scale.stops
  return (
    <div className="flex items-end gap-2">
      <div className="min-w-0 flex-1">
        <div className="flex h-2.5 border border-ink">
          {scale.stepped
            ? stops.map(([v]) => <div key={v} className="flex-1" style={{ background: css(sample(scale, v)) }} />)
            : <div className="flex-1" style={{ background: `linear-gradient(90deg, ${stops.map(([, c], i) => `${c} ${(i / (stops.length - 1)) * 100}%`).join(',')})` }} />}
        </div>
        <div className="relative mt-0.5 flex justify-between mono text-[10px] text-ink-3">
          {scale.stepped
            ? stops.map(([v]) => <span key={v} className="flex-1 text-left">{v === 0 ? '0' : format(v)}</span>)
            : scale.ticks.map((t) => <span key={t}>{format(t)}</span>)}
        </div>
      </div>
      <span className="mono text-[11px] text-ink-2">{units}</span>
    </div>
  )
}

export function Swatch({ colour, label, muted, onClick }: { colour: string; label: string; muted?: boolean; onClick?: () => void }) {
  const Tag = onClick ? 'button' : 'span'
  return (
    <Tag type={onClick ? 'button' : undefined} onClick={onClick} className={cn('flex items-center gap-1.5 text-[12px]', muted && 'opacity-35', onClick && 'hover:underline')} aria-pressed={onClick ? !muted : undefined}>
      <span className="inline-block h-2.5 w-3.5" style={{ background: colour }} />
      {label}
    </Tag>
  )
}
