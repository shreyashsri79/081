import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { AlertTriangle, ArrowRight, CloudRain, Layers, MousePointerClick, Pause, Play, Plug, RefreshCw } from 'lucide-react'
import MapPlate from '@/components/MapPlate'
import WeatherMap from '@/components/WeatherMap'
import LeadChart, { WeightStrip } from '@/components/charts/LeadChart'
import { LineReveal, Marquee, NumberTicker, Reveal } from '@/components/motion'
import { useExtremes, useField, useMeteogram, usePrefetchLeads, useRun, useRuns, useScorecard, useStamp, useWeights } from '@/lib/api'
import { PROB, SCALES, sample } from '@/lib/colour'
import type { ModelId, VarId } from '@/lib/contract'
import { stateIndex } from '@/lib/geo'
import { BLEND_COLOUR, MODELS, VARS } from '@/lib/models'
import { dominantPaint, dominantShare } from '@/lib/paint'
import { cellColour, verdict } from '@/lib/score'
import { cn, validDate } from '@/lib/utils'

/** The landing shows the five-model hindcast when it exists: it is the one with every model. */
const DEFAULT_RUN = 'hindcast-20200715'

/** DEFAULT_RUN if the source has it, else its first hindcast (the engine may hold other dates). */
function useLandingRun() {
  const runs = useRuns().data
  if (!runs || runs.some((r) => r.id === DEFAULT_RUN)) return DEFAULT_RUN
  return runs.find((r) => r.kind === 'hindcast')?.id ?? runs[0]?.id ?? DEFAULT_RUN
}

/** Grid cell nearest to a place, for whatever grid the run has (0.5° synthetic, 1.5° engine). */
function useCellAt(run: string, lat: number, lon: number): [number, number] | null {
  const g = useRun(run).data?.grid
  if (!g) return null
  const i = Math.round((lat - g.lat0) / g.step), j = Math.round((lon - g.lon0) / g.step)
  return i >= 0 && i < g.ny && j >= 0 && j < g.nx ? [i, j] : null
}
/** Nagpur, the PPT guide's "five friends" question. */
const NAGPUR = { lat: 21.15, lon: 79.09 }
const HERO_VAR: VarId = 't2m'
const WB2: ModelId[] = ['hres', 'graphcast', 'pangu', 'fuxi', 'gencast']
const COUNT: Record<number, string> = { 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six' }

function Stamp({ children = 'ILLUSTRATIVE' }: { children?: ReactNode }) {
  const stamp = useStamp(useLandingRun())
  if (!stamp) return null
  return <span className="border border-bad bg-surface/90 px-1.5 py-0.5 mono text-[10px] tracking-wider text-bad">{stamp} · {children}</span>
}

// ------------------------------------------------------------------ hero

/**
 * Full-bleed OpenStreetMap of India under the synthetic dominant-model field,
 * wind flowing over it, Day 1 → 10 on loop. The copy sits on a glass panel.
 */
function Hero() {
  const RUN = useLandingRun()
  const reduce = useReducedMotion()
  const wide = useMedia('(min-width: 1024px)')
  const [lead, setLead] = useState(1)
  const [playing, setPlaying] = useState(!reduce)
  const r = useRun(RUN).data
  usePrefetchLeads(RUN, lead, { weights: HERO_VAR, wind: true })
  const wsQ = useWeights(RUN, HERO_VAR, lead).data
  const ws = wsQ?.var === HERO_VAR ? wsQ : undefined
  const wind = useField(RUN, 'wind', lead).data
  const mask = useMemo(() => (r ? stateIndex(r.grid) : undefined), [r])
  const paint = useMemo(() => (ws ? dominantPaint(ws) : null), [ws])
  const share = useMemo(() => (ws ? dominantShare(ws, mask) : []), [ws, mask])

  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => setLead((L) => (L >= 10 ? 1 : L + 1)), 1600)
    return () => clearInterval(t)
  }, [playing])

  return (
    <section className="relative min-h-[660px] overflow-hidden border-b border-ink lg:h-[calc(100dvh-89px)]">
      <div className="absolute inset-0">
        {r && (
          <WeatherMap
            interactive={false}
            grid={r.grid}
            layer={paint ? { kind: 'paint', paint } : null}
            layerKey={`hero|${lead}`}
            smooth
            wind={wind?.u ? { u: wind.u, v: wind.v! } : null}
            particles
            fieldOpacity={0.78}
            outsideIndia={0.22}
            home={wide ? { lon: 81, lat: 22.5, span: 37, ax: 0.7, ay: 0.5 } : { lon: 80.5, lat: 22.5, span: 30, ax: 0.5, ay: 0.2 }}
          />
        )}
      </div>
      {/* a soft wash on the text side, so the glass panel reads on any tile */}
      <div className="pointer-events-none absolute inset-0 to-transparent bg-gradient-to-t from-paper/60 via-paper/10 lg:bg-gradient-to-r lg:from-paper/60 lg:via-paper/15" />

      <div className="relative z-10 flex h-full items-end px-4 pb-6 pt-[42vh] sm:px-8 lg:items-center lg:py-0">
        <div className="frame raised w-full max-w-[620px] bg-surface/55 p-6 backdrop-blur-md backdrop-saturate-150 sm:p-9">
          <Reveal><div className="label text-ink-2">SIH 2026 · PS26081 · MoES / NCMRWF</div></Reveal>
          <h1 className="t-hero mt-5 !text-[clamp(40px,5.6vw,88px)]">
            <LineReveal lines={['Right model,', 'right place,', <span key="w" className="italic">right weather.</span>]} />
          </h1>
          <Reveal delay={0.35}>
            <p className="mt-5 max-w-[34rem] text-[16.5px] leading-relaxed text-ink-2">
              Physics models and AI models forecast India's weather every day, and they disagree. None is best everywhere.
              Samanvay is built to read each model's track record for every place, lead time, season and monsoon regime, and to
              blend them into one forecast, with a map of who it trusted and why.
            </p>
          </Reveal>
          <Reveal delay={0.45} className="mt-6 flex flex-wrap gap-3">
            <Link to="/forecast" className="btn btn-ink !px-5 !py-3 !text-[15px]">Open the forecast desk <ArrowRight className="size-4" /></Link>
            <a href="#how" className="btn btn-line !bg-surface/60 !px-5 !py-3 !text-[15px]">How it blends</a>
          </Reveal>
          <Reveal delay={0.55}>
            <dl className="mt-7 grid grid-cols-3 gap-x-5 gap-y-4 border-t border-ink pt-5 sm:grid-cols-5">
              {[
                { v: 5, l: 'models, physics + AI' },
                { v: 4, l: 'variables' },
                { v: 10, l: 'lead days' },
                { v: 64.5, d: 1, l: 'mm heavy-rain line' },
                { v: 3, l: 'years left out, in turn' },
              ].map((x, k) => (
                <div key={x.l}>
                  <dt className="sr-only">{x.l}</dt>
                  <dd><NumberTicker value={x.v} digits={x.d ?? 0} delay={0.6 + k * 0.08} className="text-[28px] font-medium leading-none tracking-tight" /></dd>
                  <div className="mt-1 text-[11.5px] leading-snug text-ink-2">{x.l}</div>
                </div>
              ))}
            </dl>
          </Reveal>
        </div>
      </div>

      {/* what the backdrop is showing */}
      <div className="absolute bottom-6 right-4 z-10 hidden w-[360px] frame raised bg-surface/70 p-3 backdrop-blur-md md:block sm:right-8">
        <div className="flex items-center gap-3">
          <button type="button" className="btn btn-line !px-2" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play Day 1 to 10'}>
            {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
          </button>
          <div>
            <div className="label text-ink-3">Lead</div>
            <div className="mono text-[26px] font-medium leading-none tracking-tight">D{String(lead).padStart(2, '0')}</div>
          </div>
          <div className="ml-auto self-start"><Stamp /></div>
        </div>
        <div className="mt-3 flex h-2.5 w-full overflow-hidden border border-ink">
          {share.map((s) => (
            <motion.div key={s.model} layout transition={{ duration: 0.6, ease: [0.2, 0.7, 0.3, 1] }}
              style={{ width: `${s.share * 100}%`, background: MODELS[s.model].colour }} />
          ))}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-3 text-[11.5px]">
          {share.map((s) => (
            <span key={s.model} className="flex items-center gap-1">
              <span className="inline-block size-2" style={{ background: MODELS[s.model].colour }} />
              {MODELS[s.model].short} <span className="mono text-ink-3">{Math.round(s.share * 100)}%</span>
            </span>
          ))}
        </div>
        <p className="mt-2 text-[11.5px] leading-snug text-ink-2">
          Most-trusted model per place for {VARS[HERO_VAR].name}, with the wind, Day 1 → 10.
        </p>
        <div className="mt-2 flex gap-1">
          {Array.from({ length: 10 }, (_, k) => k + 1).map((L) => (
            <button key={L} type="button" onClick={() => { setPlaying(false); setLead(L) }}
              className={cn('h-1.5 flex-1', L <= lead ? 'bg-ink' : 'bg-rule-2')} aria-label={`Day ${L}`} />
          ))}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------- five friends

function FiveFriends() {
  const RUN = useLandingRun()
  const nagpur = useCellAt(RUN, NAGPUR.lat, NAGPUR.lon)
  const mg = useMeteogram(RUN, nagpur).data
  const runModels = useRun(RUN).data?.models
  const lead = 3
  const rain = mg?.vars.find((v) => v.var === 'rain')
  const a = mg ? mg.leads.indexOf(lead) : 0
  // every model in the run; those without precipitation (Pangu) show as "no rain output"
  const rows = rain
    ? (runModels ?? WB2).map((m) => {
        const mem = rain.members.find((x) => x.model === m)
        return { model: m, value: mem?.values[a], weight: mem?.weights[a] }
      })
    : []
  const max = Math.max(1, ...rows.map((r) => r.value ?? 0), rain?.blend[a] ?? 0)
  const init = useRun(RUN).data?.init
  const day = init ? new Date(validDate(init, lead)).toLocaleDateString('en-GB', { weekday: 'long', timeZone: 'UTC' }) : 'Thursday'

  return (
    <section className="border-y border-ink bg-surface px-4 py-16 sm:px-8">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div className="flex flex-col gap-5">
          <Reveal><div className="label text-ink-2">The problem</div></Reveal>
          <Reveal><h2 className="t-section">Ask {COUNT[rows.length] ?? 'five'} models about {day}’s rain in Nagpur.</h2></Reveal>
          <Reveal delay={0.1}>
            <p className="max-w-[32rem] text-[16px] leading-relaxed text-ink-2">
              You get five answers. Averaging them invents a road nobody suggested, and always following one model ignores that
              each is good somewhere and poor elsewhere. The right question is: <span className="font-semibold text-ink">who has been right
              here, this many days ahead, in this season and this kind of monsoon weather?</span>
            </p>
          </Reveal>
          <Reveal delay={0.2}>
            <p className="text-[12.5px] text-ink-3">{mg ? `${mg.lat.toFixed(1)}° N ${mg.lon.toFixed(1)}° E · ` : ''}Day {lead} · 24 h rainfall. Pangu-Weather has no precipitation output, so it cannot vote on rain.</p>
          </Reveal>
        </div>
        <div className="frame flex flex-col gap-2 bg-paper p-4 sm:p-5">
          <div className="flex items-center justify-between">
            <span className="label">Day {lead} rain, one cell</span>
            <Stamp />
          </div>
          {rows.map((r, k) => (
            <Reveal key={r.model} delay={k * 0.12}>
              <div className="grid grid-cols-[108px_1fr_64px] items-center gap-3 py-1">
                <span className="flex items-center gap-2 text-[13.5px]">
                  <span className="inline-block h-3 w-3" style={{ background: MODELS[r.model].colour }} />{MODELS[r.model].short}
                </span>
                {r.value == null
                  ? <span className="hatch h-5 text-[11px] leading-5 text-ink-3 pl-2">no rain output</span>
                  : (
                    <div className="relative h-5">
                      <motion.div className="absolute inset-y-0 left-0" style={{ background: MODELS[r.model].colour }}
                        initial={{ width: 0 }} whileInView={{ width: `${(r.value / max) * 100}%` }} viewport={{ once: true }}
                        transition={{ duration: 0.7, delay: 0.1 + k * 0.12 }} />
                    </div>
                  )}
                <span className="text-right mono text-[13px]">{r.value == null ? '—' : `${r.value.toFixed(0)} mm`}</span>
              </div>
            </Reveal>
          ))}
          <Reveal delay={0.7}>
            <div className="mt-2 border-t border-ink pt-3">
              <div className="grid grid-cols-[108px_1fr_64px] items-center gap-3">
                <span className="text-[13.5px] font-semibold">Blend</span>
                <div className="relative h-6">
                  <motion.div className="absolute inset-y-0 left-0" style={{ background: BLEND_COLOUR }}
                    initial={{ width: 0 }} whileInView={{ width: `${((rain?.blend[a] ?? 0) / max) * 100}%` }} viewport={{ once: true }}
                    transition={{ duration: 0.8, delay: 0.85 }} />
                </div>
                <span className="text-right mono text-[14px] font-medium">{rain?.blend[a].toFixed(0)} mm</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-2">
                <span className="text-ink-3">weights</span>
                {rows.filter((r) => r.weight != null).map((r) => (
                  <span key={r.model} className="flex items-center gap-1">
                    <span className="inline-block size-2" style={{ background: MODELS[r.model].colour }} />
                    <span className="mono">{r.weight!.toFixed(2)}</span>
                  </span>
                ))}
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

// ------------------------------------------------------------- pipeline

function LineUp() {
  const rows: [string, ModelId | null, string, string][] = [
    ['IFS HRES', 'hres', '0–240 h, 6-hourly', 'yes'],
    ['GraphCast', 'graphcast', '6–240 h', 'yes'],
    ['Pangu-Weather', 'pangu', '6–240 h', 'no'],
    ['FuXi', 'fuxi', 'to 15 days', 'yes (from 6 h)'],
    ['GenCast mean', 'gencast', '12 h–15 days', 'yes'],
    ['ERA5 (truth)', null, '—', 'yes, in metres'],
  ]
  return (
    <div className="frame bg-surface">
      <table className="w-full text-[12.5px]">
        <thead><tr className="border-b border-rule text-left text-[11px] text-ink-3"><th className="px-3 py-2 font-medium">Source</th><th className="font-medium">Native leads</th><th className="px-3 font-medium">24 h rain</th></tr></thead>
        <tbody>
          {rows.map(([n, m, l, r]) => (
            <tr key={n} className="border-b border-rule/60">
              <td className="px-3 py-2"><span className="mr-2 inline-block size-2.5 align-middle" style={{ background: m ? MODELS[m].colour : '#7a878c' }} />{n}</td>
              <td className="mono text-[12px]">{l}</td>
              <td className={cn('px-3 mono text-[12px]', r === 'no' && 'text-bad')}>{r}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center gap-2 bg-ink px-3 py-2 text-[12.5px] text-paper">
        <ArrowRight className="size-4" /> one grid · Day 1–10 at 24 h · mm, °C, m/s, hPa · common mask
      </div>
    </div>
  )
}

function TrackRecord() {
  const RUN = useLandingRun()
  const sc = useScorecard(RUN).data
  const r = useRun(RUN).data
  if (!sc || !r) return <div className="h-64" />
  const rows = sc.rows.filter((x) => x.var === 't2m')
  return (
    <div className="frame bg-surface p-3">
      <div className="mb-1 flex items-center justify-between"><span className="label">T2m RMSE by lead</span><Stamp /></div>
      <LeadChart leads={r.leads} units="°C" digits={2} height={250}
        series={r.modelsByVar.t2m.map((m) => ({ id: m, label: MODELS[m].short, colour: MODELS[m].colour, values: rows.map((x) => x.rmse[m]!) }))} />
      <p className="mt-1 text-[11.5px] text-ink-3">Early days favour one model, late days another. The same holds by region, season and regime.</p>
    </div>
  )
}

function WeightCard() {
  const RUN = useLandingRun()
  const nagpur = useCellAt(RUN, NAGPUR.lat, NAGPUR.lon)
  const mg = useMeteogram(RUN, nagpur).data
  const t = mg?.vars.find((v) => v.var === 't2m')
  return (
    <div className="frame flex flex-col gap-3 bg-surface p-4">
      <div className="flex items-center justify-between"><span className="label">Weights, Nagpur, T2m</span><Stamp /></div>
      <div className="frame bg-paper px-3 py-3 text-center mono text-[18px] sm:text-[22px]">
        w<sub>m</sub> = (1/MSE<sub>m</sub>) / Σ<sub>k</sub> (1/MSE<sub>k</sub>)
      </div>
      {t && mg && (
        <>
          <WeightStrip leads={mg.leads} height={70} members={t.members.map((m) => ({ id: m.model, colour: MODELS[m.model].colour, weights: m.weights }))} />
          <div className="flex justify-between px-10 mono text-[10.5px] text-ink-3"><span>D1</span><span>D10</span></div>
        </>
      )}
      <p className="text-[12px] text-ink-2">MSE after removing each model's own bias, keyed by cell × lead × season × regime; sparse regime bins shrink toward the season (k = 20).</p>
    </div>
  )
}

function MiniMap({ kind }: { kind: 'blend' | 'prob' }) {
  const RUN = useLandingRun()
  const r = useRun(RUN).data
  const f = useField(RUN, 'rain', 3).data
  const x = useExtremes(RUN, 'rain64', 3).data
  const paint = useMemo(() => (k: number) =>
    kind === 'blend'
      ? (f && Number.isFinite(f.values[k]) ? sample(SCALES.rain, f.values[k]) : null)
      : (x && Number.isFinite(x.prob[k]) ? sample(PROB, x.prob[k]) : null), [kind, f, x])
  return (
    <div className="frame bg-surface p-3">
      <div className="mb-1 flex items-center justify-between">
        <span className="label">{kind === 'blend' ? 'Blended 24 h rain · Day 3' : 'P(rain ≥ 64.5 mm) · Day 3'}</span><Stamp />
      </div>
      <div className="aspect-[1.02] w-full lg:aspect-auto lg:h-[min(56vh,520px)]">
        {r && (f || x) && (
          <MapPlate grid={r.grid} paint={paint} version={`mini|${kind}|${!!f}|${!!x}`} selected={null} onSelect={() => {}}
            readout={(k) => <div className="mono text-[12.5px]">{kind === 'blend' ? `${f?.values[k].toFixed(1)} mm` : `${Math.round((x?.prob[k] ?? 0) * 100)}%`}</div>} />
        )}
      </div>
    </div>
  )
}

function MiniScore() {
  const RUN = useLandingRun()
  const sc = useScorecard(RUN).data
  const r = useRun(RUN).data
  if (!sc || !r) return <div className="h-64" />
  return (
    <div className="frame bg-surface p-3">
      <div className="mb-2 flex items-center justify-between"><span className="label">Blend vs best single model</span><Stamp children="NOT A RESULT" /></div>
      <div className="grid gap-1" style={{ gridTemplateColumns: '64px repeat(10, minmax(0, 1fr))' }}>
        <span />
        {r.leads.map((L) => <span key={L} className="text-center mono text-[10px] text-ink-3">D{L}</span>)}
        {r.vars.map((v) => (
          <FragmentRow key={v} label={VARS[v].short}>
            {sc.rows.filter((x) => x.var === v).map((row, k) => {
              const vd = verdict(row, 'best')!
              return (
                <motion.span key={row.lead} className="flex h-8 items-center justify-center mono text-[10px]" style={cellColour(vd.pct, vd.sig)}
                  initial={{ opacity: 0, scale: 0.9 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ delay: k * 0.04 }}>
                  {vd.pct.toFixed(0)}%
                </motion.span>
              )
            })}
          </FragmentRow>
        ))}
      </div>
      <p className="mt-2 text-[11.5px] text-ink-3">Grey: the 95 % block-bootstrap interval includes zero, so no gain is claimed.</p>
    </div>
  )
}
function FragmentRow({ label, children }: { label: string; children: ReactNode }) {
  return <><span className="self-center text-[12px] text-ink-2">{label}</span>{children}</>
}

const STEPS: { n: string; title: string; body: string; visual: ReactNode }[] = [
  { n: '01', title: 'Line them up', body: 'Every source is brought to one grid, one set of lead days, one set of units and one land-sea mask. Models are only ever scored on the same days.', visual: <LineUp /> },
  { n: '02', title: 'Read the track record', body: 'Each model is scored against truth (ERA5; CHIRPS for rain) for every cell, lead, season and regime: monsoon active or break, depression, western disturbance, heat.', visual: <TrackRecord /> },
  { n: '03', title: 'Set the weights', body: 'Inverse error weights, per cell. A model that has been twice as accurate here gets twice the say. Transparent enough to check by hand, and updated daily as truth arrives.', visual: <WeightCard /> },
  { n: '04', title: 'Blend', body: 'One forecast for rain, temperature, wind and pressure, Day 1–10, built from bias-corrected members and their weights.', visual: <MiniMap kind="blend" /> },
  { n: '05', title: 'Warn on extremes', body: 'Averaging smooths peaks, so heavy rain, heat waves and high wind come out as calibrated probabilities, not read off the blended mean.', visual: <MiniMap kind="prob" /> },
  { n: '06', title: 'Prove it', body: 'Scored on years the weights never saw, with confidence intervals. Where the blend does not help, the scorecard will say so.', visual: <MiniScore /> },
]

/** True when the media query matches; drives which pipeline layout is mounted. */
function useMedia(q: string) {
  const [on, setOn] = useState(() => window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q)
    const f = () => setOn(m.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [q])
  return on
}

function Pipeline() {
  // Mount one layout only: the synthetic visuals are costly to compute twice.
  const wide = useMedia('(min-width: 1024px)')
  const [active, setActive] = useState(0)
  const refs = useRef<(HTMLDivElement | null)[]>([])
  useEffect(() => {
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => { if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.step)) }),
      { rootMargin: '-45% 0px -45% 0px' },
    )
    refs.current.forEach((el) => el && io.observe(el))
    return () => io.disconnect()
  }, [])

  return (
    <section id="how" className="px-4 py-16 sm:px-8">
      <Reveal><div className="label text-ink-2">How it blends</div></Reveal>
      <Reveal><h2 className="t-section mt-3 max-w-[18ch]">Six steps, designed to run every morning at 06:00 IST.</h2></Reveal>
      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="flex flex-col">
          {STEPS.map((s, k) => (
            <div key={s.n} ref={(el) => { refs.current[k] = el }} data-step={k}
              className={cn('flex flex-col gap-3 border-t border-rule py-8 transition-opacity duration-300 lg:min-h-[62vh] lg:justify-center', active === k ? 'opacity-100' : 'lg:opacity-35')}>
              <div className="flex items-baseline gap-4">
                <span className="mono text-[13px] text-ink-3">{s.n}</span>
                <h3 className="t-display text-[28px] sm:text-[34px]">{s.title}</h3>
              </div>
              <p className="max-w-[30rem] text-[16px] leading-relaxed text-ink-2">{s.body}</p>
              {!wide && <div className="mt-3">{s.visual}</div>}
            </div>
          ))}
        </div>
        {wide && <div>
          <div className="sticky top-[calc(var(--masthead)+40px)]">
            <AnimatePresence mode="wait">
              <motion.div key={active} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}>
                {STEPS[active].visual}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>}
      </div>
    </section>
  )
}

// ------------------------------------------------------------ the matrix

const AVAIL: Record<ModelId, { vars: VarId[]; years: number[] }> = {
  hres: { vars: ['rain', 't2m', 'wind', 'mslp'], years: [2018, 2020, 2022] },
  graphcast: { vars: ['rain', 't2m', 'wind', 'mslp'], years: [2018, 2020, 2022] },
  pangu: { vars: ['t2m', 'wind', 'mslp'], years: [2018, 2020, 2022] },
  fuxi: { vars: ['rain', 't2m', 'wind', 'mslp'], years: [2020] },
  gencast: { vars: ['rain', 't2m', 'wind', 'mslp'], years: [2020] },
} as Record<ModelId, { vars: VarId[]; years: number[] }>

export function Matrix() {
  const cols: { key: string; label: string; has: (m: ModelId) => boolean }[] = [
    ...(['rain', 't2m', 'wind', 'mslp'] as VarId[]).map((v) => ({ key: v, label: VARS[v].short, has: (m: ModelId) => AVAIL[m].vars.includes(v) })),
    ...[2018, 2020, 2022].map((y) => ({ key: String(y), label: String(y), has: (m: ModelId) => AVAIL[m].years.includes(y) })),
  ]
  return (
    <div className="overflow-x-auto scroll-thin">
      <div className="grid min-w-[520px] gap-1" style={{ gridTemplateColumns: `130px repeat(4, minmax(0,1fr)) 12px repeat(3, minmax(0,1fr))` }}>
        <span />
        {cols.map((c, k) => (
          <FragmentCell key={c.key} gap={k === 4}>
            <span className="pb-1 text-center mono text-[11px] text-ink-3">{c.label}</span>
          </FragmentCell>
        ))}
        {WB2.map((m, r) => (
          <FragmentRow key={m} label={MODELS[m].name}>
            {cols.map((c, k) => (
              <FragmentCell key={c.key} gap={k === 4}>
                <motion.span
                  className={cn('block h-9', !c.has(m) && 'hatch border border-rule')}
                  style={c.has(m) ? { background: MODELS[m].colour } : undefined}
                  initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ delay: r * 0.06 + k * 0.03 }}
                  title={`${MODELS[m].name} · ${c.label}: ${c.has(m) ? 'available' : 'not available'}`}
                />
              </FragmentCell>
            ))}
          </FragmentRow>
        ))}
      </div>
    </div>
  )
}
function FragmentCell({ gap, children }: { gap: boolean; children: ReactNode }) {
  return <>{gap && <span />}{children}</>
}

function Availability() {
  return (
    <section className="border-y border-ink bg-surface px-4 py-16 sm:px-8">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div className="flex flex-col gap-4">
          <Reveal><div className="label text-ink-2">What can be blended, honestly</div></Reveal>
          <Reveal><h2 className="t-section">Rain has four voices, not five.</h2></Reveal>
          <Reveal delay={0.1}>
            <p className="text-[16px] leading-relaxed text-ink-2">
              Checked against the public WeatherBench 2 stores on 28 Sep. Pangu-Weather produces no precipitation, and FuXi and
              GenCast exist only for 2020. So the headline test uses HRES, GraphCast and Pangu across three years, each year left out in
              turn; the five-model set is tested inside 2020 on held-out months.
            </p>
          </Reveal>
          <Reveal delay={0.15}><Link to="/data" className="btn btn-line self-start">Data &amp; models <ArrowRight className="size-4" /></Link></Reveal>
        </div>
        <Reveal delay={0.1} className="frame bg-paper p-4 sm:p-5">
          <Matrix />
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-ink-2">
            <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-4 bg-ink" />available (model hue)</span>
            <span className="flex items-center gap-1.5"><span className="hatch inline-block h-3 w-4 border border-rule" />not available</span>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

// ------------------------------------------------------ different + honest

const DIFF = [
  { icon: Layers, t: 'Physics and AI in one blend', b: 'Weighted cell by cell, not model by model.' },
  { icon: CloudRain, t: 'Regime-aware weights', b: 'Active, break, depression, western disturbance, heat.' },
  { icon: RefreshCw, t: 'Adapts daily', b: 'Weights update as each day’s truth arrives.' },
  { icon: AlertTriangle, t: 'Extremes as probabilities', b: 'Calibrated, not a smoothed average.' },
  { icon: MousePointerClick, t: 'Explainable', b: 'Click any cell: weights, errors, and the cases behind them.' },
  { icon: Plug, t: 'NCUM-ready', b: 'Open data today; India’s models through an adapter.' },
]

const NOT_CLAIMED = [
  ['“Improves accuracy by X %”', 'Until the held-out run measures it. Then the exact number, with its interval.'],
  ['“Tested on NCUM”', 'The adapter is ready; it needs NCMRWF data to learn weights.'],
  ['“Beats IMD’s operational forecast”', 'We compare against the models we blend and against equal weights.'],
  ['“Real-time GraphCast”', 'Live inputs are ECMWF IFS, AIFS and NOAA GFS: the ones openly served daily.'],
  ['A rain weight for Pangu', 'It has no precipitation output.'],
]

function Different() {
  return (
    <section className="px-4 py-16 sm:px-8">
      <div className="grid gap-12 lg:grid-cols-2">
        <div>
          <Reveal><div className="label text-ink-2">What is different</div></Reveal>
          <div className="mt-6 grid gap-px border border-ink bg-ink sm:grid-cols-2">
            {DIFF.map((d, k) => (
              <Reveal key={d.t} delay={k * 0.05} className="h-full bg-paper">
                <div className="flex h-full flex-col gap-2 p-5">
                  <d.icon className="size-5" strokeWidth={1.6} />
                  <div className="t-display text-[19px]">{d.t}</div>
                  <p className="text-[13.5px] text-ink-2">{d.b}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
        <div>
          <Reveal><div className="label text-ink-2">What we will not claim</div></Reveal>
          <Reveal><p className="mt-3 max-w-[32rem] text-[16px] text-ink-2">Blending is a known idea; the judges know the literature. We win on the combination, the measurement and the honesty.</p></Reveal>
          <ul className="mt-6 flex flex-col">
            {NOT_CLAIMED.map(([c, why], k) => (
              <Reveal key={c} delay={k * 0.06}>
                <li className="grid grid-cols-[18px_1fr] gap-3 border-t border-rule py-3.5">
                  <span className="mt-1.5 size-2.5 bg-bad" />
                  <div>
                    <div className="text-[15px] font-medium line-through decoration-bad decoration-2">{c}</div>
                    <div className="text-[13.5px] text-ink-2">{why}</div>
                  </div>
                </li>
              </Reveal>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

const VOCAB = [
  'IFS HRES', 'GraphCast', 'Pangu-Weather', 'FuXi', 'GenCast', 'ECMWF AIFS', 'NOAA GFS', 'NCUM', 'NEPS-G · 23 members',
  'ERA5', 'CHIRPS 0.05°', '64.5 mm', '115.6 mm', '204.5 mm', 'JJAS', 'active / break', 'western disturbance',
  'LOYO 2018 · 2020 · 2022', 'λ = 0.95', 'k = 20', 'block bootstrap · 1,000', 'FSS', 'Brier skill', '06:00 IST',
]

export default function Landing() {
  return (
    <div>
      <Hero />
      <div className="border-t border-ink bg-ink py-3 text-paper">
        <Marquee items={VOCAB.map((v) => <span key={v} className="mono text-[13px] text-[#d9dfe1]">{v}</span>)} />
      </div>
      <FiveFriends />
      <Pipeline />
      <Availability />
      <Different />
      <section className="bg-ink px-4 py-16 text-paper sm:px-8">
        <div className="flex flex-col items-start gap-6 lg:flex-row lg:items-end lg:justify-between">
          <h2 className="t-section max-w-[16ch]">Pick a cell. See who the blend trusted, and why.</h2>
          <div className="flex flex-wrap gap-3">
            <Link to="/forecast" className="btn !bg-paper !px-5 !py-3 !text-[15px] !text-ink hover:!bg-surface-2">Open the forecast desk <ArrowRight className="size-4" /></Link>
            <Link to="/skill" className="btn !px-5 !py-3 !text-[15px] border border-paper text-paper hover:bg-paper hover:text-ink">See the scorecard</Link>
          </div>
        </div>
      </section>
    </div>
  )
}
