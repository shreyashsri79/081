import { useState } from 'react'
import { useWidth } from '@/components/Controls'

export interface Series {
  id: string
  label: string
  colour: string
  values: number[]
  /** 0–1 per lead: drawn as point size so heavily weighted days stand out. */
  weights?: number[]
  emphasis?: boolean
}

interface Props {
  leads: number[]
  series: Series[]
  current?: number
  onLead?: (lead: number) => void
  height?: number
  units: string
  digits?: number
  /** Draw the emphasised series as bars (rain) instead of a line. */
  bars?: boolean
  /** Shade between min and max of the non-emphasised series. */
  spread?: boolean
  hidden?: Set<string>
  yZero?: boolean
}

const M = { l: 40, r: 18, t: 8, b: 20 }

function niceTicks(lo: number, hi: number, n = 4) {
  const span = hi - lo || 1
  const step0 = span / n
  const mag = 10 ** Math.floor(Math.log10(step0))
  const step = [1, 2, 2.5, 5, 10].map((x) => x * mag).find((x) => x >= step0) ?? step0
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6))
  return out
}

/**
 * The house chart: something against lead time. Models in their hue, the blend
 * in ink and thicker. Hover reads every series at one lead; click sets the lead.
 */
export default function LeadChart({ leads, series, current, onLead, height = 150, units, digits = 1, bars, spread, hidden, yZero }: Props) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const [hov, setHov] = useState<number | null>(null)
  const shown = series.filter((s) => !hidden?.has(s.id))
  const all = shown.flatMap((s) => s.values).filter(Number.isFinite)
  let lo = Math.min(...all), hi = Math.max(...all)
  if (!all.length) { lo = 0; hi = 1 }
  if (yZero || bars) lo = Math.min(0, lo)
  const pad = (hi - lo) * 0.08 || 1
  lo = yZero || bars ? lo : lo - pad
  hi += pad
  const iw = Math.max(10, w - M.l - M.r), ih = height - M.t - M.b
  const x = (a: number) => M.l + (leads.length === 1 ? iw / 2 : (a / (leads.length - 1)) * iw)
  const y = (v: number) => M.t + (1 - (v - lo) / (hi - lo)) * ih
  const ticks = niceTicks(lo, hi)
  const members = shown.filter((s) => !s.emphasis)
  const bw = Math.max(3, (iw / leads.length) * 0.42)

  const band = spread && members.length > 1
    ? leads.map((_, a) => { const v = members.map((s) => s.values[a]); return [Math.min(...v), Math.max(...v)] })
    : null

  const hoverAt = (px: number) => {
    const a = Math.round(((px - M.l) / iw) * (leads.length - 1))
    return a >= 0 && a < leads.length ? a : null
  }

  return (
    <div ref={ref} className="relative w-full" style={{ height }}>
      {w > 0 && (
        <svg width={w} height={height} className="block"
          onMouseMove={(e) => setHov(hoverAt(e.clientX - e.currentTarget.getBoundingClientRect().left))}
          onMouseLeave={() => setHov(null)}
          onClick={(e) => { const a = hoverAt(e.clientX - e.currentTarget.getBoundingClientRect().left); if (a != null) onLead?.(leads[a]) }}
          style={{ cursor: onLead ? 'pointer' : undefined }}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={M.l} x2={M.l + iw} y1={y(t)} y2={y(t)} stroke="#d5d2cc" />
              <text x={M.l - 5} y={y(t) + 3.5} textAnchor="end" className="mono" fontSize={10} fill="#7a878c">{t}</text>
            </g>
          ))}
          {leads.map((L, a) => (
            <text key={L} x={x(a)} y={height - 5} textAnchor="middle" className="mono" fontSize={10} fill={L === current ? '#0e2129' : '#7a878c'} fontWeight={L === current ? 600 : 400}>D{L}</text>
          ))}
          {current != null && leads.includes(current) && (
            <rect x={x(leads.indexOf(current)) - bw / 2 - 4} y={M.t} width={bw + 8} height={ih} fill="rgb(14 33 41 / .06)" />
          )}
          {band && (
            <path
              d={`M${band.map(([, h], a) => `${x(a)},${y(h)}`).join('L')}L${band.map(([l], a) => `${x(a)},${y(l)}`).reverse().join('L')}Z`}
              fill="rgb(14 33 41 / .08)"
            />
          )}
          {bars && shown.filter((s) => s.emphasis).map((s) => s.values.map((v, a) => (
            <rect key={`${s.id}${a}`} x={x(a) - bw / 2} y={y(Math.max(0, v))} width={bw} height={Math.max(0, y(0) - y(Math.max(0, v)))} fill={s.colour} opacity={0.85} />
          )))}
          {members.map((s) => (
            <g key={s.id}>
              <polyline points={s.values.map((v, a) => `${x(a)},${y(v)}`).join(' ')} fill="none" stroke={s.colour} strokeWidth={1.4} strokeLinejoin="round" />
              {s.weights && s.values.map((v, a) => (
                <circle key={a} cx={x(a)} cy={y(v)} r={1.5 + s.weights![a] * 4.5} fill={s.colour} stroke="#f8f7f5" strokeWidth={0.8} />
              ))}
            </g>
          ))}
          {!bars && shown.filter((s) => s.emphasis).map((s) => (
            <polyline key={s.id} points={s.values.map((v, a) => `${x(a)},${y(v)}`).join(' ')} fill="none" stroke={s.colour} strokeWidth={2.6} strokeLinejoin="round" />
          ))}
          {hov != null && <line x1={x(hov)} x2={x(hov)} y1={M.t} y2={M.t + ih} stroke="#0e2129" strokeDasharray="2 3" />}
          <text x={4} y={M.t + 8} className="mono" fontSize={10} fill="#7a878c">{units}</text>
        </svg>
      )}
      {hov != null && (
        <div className="pointer-events-none absolute z-10 frame raised bg-surface px-2 py-1 text-[11.5px]"
          style={{ left: Math.min(x(hov) + 10, w - 150), top: 4 }}>
          <div className="mono text-[10.5px] text-ink-3">Day {leads[hov]}</div>
          {shown.map((s) => (
            <div key={s.id} className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2.5" style={{ background: s.colour }} />
              <span className={s.emphasis ? 'font-semibold' : ''}>{s.label}</span>
              <span className="ml-auto pl-3 mono">{s.values[hov]?.toFixed(digits)}</span>
              {s.weights && <span className="mono text-ink-3">w {s.weights[hov].toFixed(2)}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Stacked weight bar per lead, one row: how trust shifts with lead time. */
export function WeightStrip({ leads, members, current, height = 16 }: { leads: number[]; members: { id: string; colour: string; weights: number[] }[]; current?: number; height?: number }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const iw = Math.max(10, w - M.l - M.r)
  const step = leads.length > 1 ? iw / (leads.length - 1) : iw
  const bw = Math.max(4, step * 0.7)
  return (
    <div ref={ref} className="w-full" style={{ height }}>
      {w > 0 && (
        <svg width={w} height={height} className="block">
          <text x={M.l - 5} y={height - 4} textAnchor="end" className="mono" fontSize={9.5} fill="#7a878c">w</text>
          {leads.map((L, a) => {
            let acc = 0
            const cx = M.l + (leads.length === 1 ? iw / 2 : a * step)
            return (
              <g key={L} opacity={current == null || current === L ? 1 : 0.75}>
                {members.map((m) => {
                  const h = m.weights[a] * height
                  const r = <rect key={m.id} x={cx - bw / 2} y={height - acc - h} width={bw} height={h} fill={m.colour} />
                  acc += h
                  return r
                })}
                {current === L && <rect x={cx - bw / 2} y={0.5} width={bw} height={height - 1} fill="none" stroke="#0e2129" />}
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}
