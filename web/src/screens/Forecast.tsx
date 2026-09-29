import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ChevronDown, CloudRain, Gauge, Layers, LineChart, Pause, Play, Search, Thermometer, Wind, X } from 'lucide-react'
import WeatherMap, { type MapLayer } from '@/components/WeatherMap'
import Meteogram from '@/components/Meteogram'
import { useEvents, useExtremes, useField, useModelField, usePrefetchLeads, useRun, useStamp, useWeights } from '@/lib/api'
import { PROB, SCALES, css, sample, type Scale } from '@/lib/colour'
import { CITIES } from '@/lib/cities'
import type { ExtremeId, VarId } from '@/lib/contract'
import { MODELS, VARS } from '@/lib/models'
import { dominantPaint } from '@/lib/paint'
import { useDesk, type MapLayerId } from '@/lib/store'
import { cn } from '@/lib/utils'

/**
 * The map explorer, after Ventusky and meteoblue: the map is the page, and
 * everything else floats on it. Layers on the left, the source on the right,
 * days along the bottom, the meteogram in a drawer when you pick a point.
 */

const GROUPS: { title: string; items: { id: MapLayerId; label: string; icon: typeof CloudRain }[] }[] = [
  {
    title: 'Blended forecast',
    items: [
      { id: 'rain', label: 'Rain, 24 h', icon: CloudRain },
      { id: 't2m', label: 'Temperature', icon: Thermometer },
      { id: 'wind', label: 'Wind', icon: Wind },
      { id: 'mslp', label: 'Pressure', icon: Gauge },
    ],
  },
  { title: 'Blend weights', items: [{ id: 'dominant', label: 'Most-trusted model', icon: Layers }] },
]
/** The layer list: fixed forecast and weight layers, plus whatever extreme events the run provides. */
function useGroups() {
  const { run } = useDesk()
  const events = useEvents(run)
  return [...GROUPS, { title: 'Extremes', items: events.map((e) => ({ id: e.id as MapLayerId, label: e.name, icon: AlertTriangle })) }]
}
const isVar = (l: MapLayerId): l is VarId => l === 'rain' || l === 't2m' || l === 'wind' || l === 'mslp'
const isExtreme = (l: MapLayerId): l is ExtremeId => !isVar(l) && l !== 'dominant'

const CITY_FMT: Record<VarId, (v: number) => string> = {
  rain: (v) => (v < 0.5 ? '0' : v.toFixed(0)),
  t2m: (v) => `${v.toFixed(0)}°`,
  wind: (v) => v.toFixed(0),
  mslp: (v) => v.toFixed(0),
}

const glass = 'frame bg-surface/95 raised backdrop-blur-sm'

function LayerRail() {
  const { layer, set } = useDesk()
  const groups = useGroups()
  const [open, setOpen] = useState(true)
  return (
    <div className={cn(glass, 'pointer-events-auto flex w-[210px] flex-col')}>
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex items-center justify-between border-b border-rule px-3 py-2">
        <span className="label">Layers</span>
        <ChevronDown className={cn('size-4 transition-transform', !open && '-rotate-90')} />
      </button>
      {open && groups.map((g) => (
        <div key={g.title} className="border-b border-rule/70 py-1 last:border-0">
          <div className="px-3 pb-0.5 pt-1.5 text-[10.5px] font-medium uppercase tracking-wider text-ink-3">{g.title}</div>
          {g.items.map((it) => (
            <button key={it.id} type="button" aria-pressed={layer === it.id}
              onClick={() => set({ layer: it.id, ...(isVar(it.id) ? { v: it.id } : {}), ...(isExtreme(it.id) ? { extreme: it.id } : {}) })}
              className={cn('flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[13.5px] hover:bg-surface-2', layer === it.id && 'bg-ink text-paper hover:bg-ink')}>
              <it.icon className="size-4 shrink-0" strokeWidth={1.7} />{it.label}
            </button>
          ))}
        </div>
      ))}
    </div>
  )
}

function MobileLayers() {
  const { layer, set } = useDesk()
  const groups = useGroups()
  return (
    <div className={cn(glass, 'pointer-events-auto flex max-w-full overflow-x-auto scroll-thin')}>
      {groups.flatMap((g) => g.items).map((it) => (
        <button key={it.id} type="button" aria-pressed={layer === it.id}
          onClick={() => set({ layer: it.id, ...(isVar(it.id) ? { v: it.id } : {}), ...(isExtreme(it.id) ? { extreme: it.id } : {}) })}
          className={cn('flex shrink-0 items-center gap-1.5 whitespace-nowrap border-r border-rule px-2.5 py-2 text-[12.5px]', layer === it.id && 'bg-ink text-paper')}>
          <it.icon className="size-3.5" />{it.label}
        </button>
      ))}
    </div>
  )
}

function CitySearch() {
  const { run, set } = useDesk()
  const r = useRun(run).data
  const [q, setQ] = useState('')
  const [focus, setFocus] = useState(false)
  const hits = q.trim() ? CITIES.filter((c) => c.name.toLowerCase().includes(q.trim().toLowerCase())).slice(0, 6) : []
  const pick = (c: (typeof CITIES)[number]) => {
    if (!r) return
    const g = r.grid
    set({
      cell: [Math.round((c.lat - g.lat0) / g.step), Math.round((c.lon - g.lon0) / g.step)],
      fly: { lon: c.lon, lat: c.lat, zoom: 3.2, n: Date.now() },
      drawer: true,
    })
    setQ(''); setFocus(false)
  }
  return (
    <div className="pointer-events-auto relative w-[210px]">
      <label className={cn(glass, 'flex items-center gap-2 px-2.5 py-1.5')}>
        <Search className="size-4 text-ink-3" />
        <input value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)}
          onKeyDown={(e) => { if (e.key === 'Enter' && hits[0]) pick(hits[0]) }}
          placeholder="Search a city" className="w-full bg-transparent text-[13.5px] outline-none placeholder:text-ink-3" aria-label="Search a city" />
      </label>
      {focus && hits.length > 0 && (
        <ul className={cn(glass, 'absolute inset-x-0 top-full z-30 mt-1')}>
          {hits.map((c) => (
            <li key={c.name}>
              <button type="button" onMouseDown={() => pick(c)} className="flex w-full items-baseline justify-between px-2.5 py-1.5 text-left text-[13px] hover:bg-surface-2">
                {c.name}<span className="mono text-[10.5px] text-ink-3">{c.lat.toFixed(1)}°N {c.lon.toFixed(1)}°E</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SourcePicker() {
  const { run, layer, v, member, set } = useDesk()
  const r = useRun(run).data
  if (!r) return null
  if (layer === 'dominant') {
    return (
      <div className={cn(glass, 'pointer-events-auto flex items-center gap-2 px-2.5 py-1.5')}>
        <span className="text-[12px] text-ink-3">Weights for</span>
        <div className="seg">
          {(['rain', 't2m', 'wind', 'mslp'] as VarId[]).map((x) => (
            <button key={x} type="button" aria-pressed={v === x} onClick={() => set({ v: x })}>{VARS[x].short}</button>
          ))}
        </div>
      </div>
    )
  }
  if (!isVar(layer)) return null
  const members = r.modelsByVar[layer]
  return (
    <label className={cn(glass, 'pointer-events-auto relative flex items-center gap-2 py-1.5 pl-2.5 pr-8')}>
      <span className="text-[12px] text-ink-3">Model</span>
      <span className="inline-block size-2.5" style={{ background: member ? MODELS[member].colour : '#0e2129' }} />
      <select value={member ?? ''} onChange={(e) => set({ member: (e.target.value || null) as typeof member })}
        className="appearance-none bg-transparent pr-1 text-[13.5px] font-medium outline-none">
        <option value="">Blend ({r.rung})</option>
        {members.map((m) => <option key={m} value={m}>{MODELS[m].name}</option>)}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 size-4" />
    </label>
  )
}

function OverlayToggles() {
  const { overlays, set } = useDesk()
  const items: [keyof typeof overlays, string][] = [['particles', 'Wind flow'], ['isobars', 'Isobars'], ['cities', 'City values'], ['smooth', 'Smooth'], ['basemap', 'Street map']]
  return (
    <div className={cn(glass, 'pointer-events-auto flex flex-col py-1')}>
      {items.map(([k, label]) => (
        <label key={k} className="flex cursor-pointer items-center gap-2 px-2.5 py-1 text-[12.5px] hover:bg-surface-2">
          <input type="checkbox" checked={overlays[k]} onChange={(e) => set({ overlays: { ...overlays, [k]: e.target.checked } })} className="accent-[#0e2129]" />
          {label}
        </label>
      ))}
    </div>
  )
}

function MapLegend({ scale, units, format }: { scale: Scale; units: string; format: (v: number) => string }) {
  const stops = scale.stops
  return (
    <div className={cn(glass, 'pointer-events-auto w-[300px] max-w-full px-2.5 py-2')}>
      <div className="flex h-2.5">
        {scale.stepped
          ? stops.map(([v]) => <div key={v} className="flex-1" style={{ background: css(sample(scale, v)) }} />)
          : <div className="flex-1" style={{ background: `linear-gradient(90deg, ${stops.map(([, c], i) => `${c} ${(i / (stops.length - 1)) * 100}%`).join(',')})` }} />}
      </div>
      <div className="mt-1 flex justify-between mono text-[10px] text-ink-2">
        {(scale.stepped ? stops.map(([v]) => v) : scale.ticks).map((t) => <span key={t}>{format(t)}</span>)}
        <span className="text-ink-3">{units}</span>
      </div>
    </div>
  )
}

function DominantLegend({ models }: { models: string[] }) {
  return (
    <div className={cn(glass, 'pointer-events-auto flex flex-wrap items-center gap-x-3 gap-y-1 px-2.5 py-2 text-[12px]')}>
      {models.map((m) => (
        <span key={m} className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-3.5" style={{ background: MODELS[m as keyof typeof MODELS].colour }} />{MODELS[m as keyof typeof MODELS].short}</span>
      ))}
      <span className="text-ink-3">pale = near-equal weights</span>
    </div>
  )
}

/** Day strip along the bottom, like Ventusky's timeline: weekday, date, lead. */
function Timeline() {
  const { run, lead, set } = useDesk()
  const r = useRun(run).data
  const [playing, setPlaying] = useState(false)
  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => { const L = useDesk.getState().lead; useDesk.getState().set({ lead: L >= 10 ? 1 : L + 1 }) }, 1100)
    return () => clearInterval(t)
  }, [playing])
  if (!r) return null
  const days = r.leads.map((L) => { const d = new Date(r.init); d.setUTCDate(d.getUTCDate() + L); return { L, d } })
  return (
    <div className={cn(glass, 'pointer-events-auto flex items-stretch')}>
      <button type="button" onClick={() => setPlaying((p) => !p)} className="grid w-11 shrink-0 place-items-center border-r border-rule hover:bg-surface-2" aria-label={playing ? 'Pause' : 'Play'}>
        {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
      </button>
      <div className="hidden shrink-0 flex-col justify-center border-r border-rule px-3 sm:flex">
        <span className="text-[10.5px] text-ink-3">init</span>
        <span className="mono text-[11.5px]">{r.init.slice(5, 10)} 00Z</span>
      </div>
      <div className="flex min-w-0 flex-1 overflow-x-auto scroll-thin" role="tablist" aria-label="Forecast day">
        {days.map(({ L, d }) => (
          <button key={L} type="button" role="tab" aria-selected={L === lead} onClick={() => { setPlaying(false); set({ lead: L }) }}
            className={cn('flex min-w-[64px] flex-1 flex-col items-center border-r border-rule/70 px-1 py-1.5 last:border-r-0 hover:bg-surface-2', L === lead && 'bg-ink text-paper hover:bg-ink')}>
            <span className="text-[11.5px] font-medium">{d.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' })} {d.getUTCDate()}</span>
            <span className={cn('mono text-[10px]', L === lead ? 'text-[#c9d2d5]' : 'text-ink-3')}>D{L}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function useWide() {
  const q = '(min-width: 1024px)'
  const [on, setOn] = useState(() => window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q)
    const f = () => setOn(m.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [])
  return on
}

export default function Forecast() {
  const { run, v, lead, cell, member, layer, overlays, drawer, fly, set } = useDesk()
  const wide = useWide()
  const r = useRun(run).data
  const stamp = useStamp(run)
  const fv: VarId = isVar(layer) ? layer : v
  const blend = useField(run, fv, lead).data
  const raw = useModelField(run, isVar(layer) ? member : null, fv, lead).data
  const windF = useField(run, 'wind', lead).data
  const mslpF = useField(run, 'mslp', lead).data
  const events = useEvents(run)
  // only ask for an event this run lists (the selection is re-pointed by useDeskSync when the run changes)
  const evId = isExtreme(layer) && events.some((e) => e.id === layer) ? layer : undefined
  usePrefetchLeads(run, lead, {
    field: isVar(layer) && !member ? layer : undefined,
    wind: overlays.particles,
    weights: layer === 'dominant' ? v : undefined,
    extreme: evId,
  })
  const wsQ = useWeights(run, v, lead).data
  const ws = wsQ?.var === v ? wsQ : undefined
  const xmQ = useExtremes(run, evId, lead).data
  const xm = xmQ && isExtreme(layer) && xmQ.type === layer ? xmQ : undefined

  // Placeholder data from the previous query is kept while loading: only use it if it is the right variable.
  const pick = (f: typeof blend) => (f && f.var === fv ? f : undefined)
  const field = isVar(layer) ? (member ? pick(raw) : pick(blend)) : null
  const windUV = layer === 'wind' && field?.u && field.lead === lead ? { u: field.u, v: field.v! } : windF?.u ? { u: windF.u, v: windF.v! } : null

  const mapLayer: MapLayer | null = useMemo(() => {
    if (isVar(layer)) return field ? { kind: 'scalar', values: field.values, scale: SCALES[layer] } : null
    if (layer === 'dominant') return ws ? { kind: 'paint', paint: dominantPaint(ws) } : null
    return xm ? { kind: 'scalar', values: xm.prob, scale: PROB } : null
  }, [layer, field, ws, xm])
  const layerKey = `${run}|${layer}|${fv}|${lead}|${member}|${!!mapLayer}|${v}`

  const cityValue = useMemo(() => {
    if (isVar(layer) && field) return (k: number) => (Number.isFinite(field.values[k]) ? CITY_FMT[layer](field.values[k]) : null)
    if (layer === 'dominant' && ws) return (k: number) => MODELS[ws.models[ws.dominant[k]]].short
    if (xm) return (k: number) => `${Math.round(xm.prob[k] * 100)}%`
    return undefined
  }, [layer, field, ws, xm])

  const readout = (k: number) => {
    if (isVar(layer) && field)
      return <div className="mono text-[14px] font-medium">{field.values[k].toFixed(VARS[layer].digits)} <span className="text-ink-3">{VARS[layer].units}</span>{member && <span className="ml-1.5 font-sans text-[11px] text-ink-3">{MODELS[member].short}</span>}</div>
    if (layer === 'dominant' && ws)
      return (
        <div className="mt-0.5 flex flex-col gap-0.5">
          {ws.models.map((m, a) => (
            <div key={m} className="flex items-center gap-1.5 text-[12px]">
              <span className="inline-block h-2 w-2.5" style={{ background: MODELS[m].colour }} />
              <span className={cn(ws.dominant[k] === a && 'font-semibold')}>{MODELS[m].short}</span>
              <span className="ml-auto pl-4 mono">{ws.weights[a][k].toFixed(2)}</span>
            </div>
          ))}
        </div>
      )
    if (xm) return <div className="mono text-[14px] font-medium">p = {Math.round(xm.prob[k] * 100)}%</div>
    return null
  }

  const legend = isVar(layer)
    ? <MapLegend scale={SCALES[layer]} units={VARS[layer].units} format={(x) => (layer === 'rain' && x === 0 ? '0' : String(x))} />
    : layer === 'dominant'
      ? <DominantLegend models={ws?.models ?? []} />
      : <MapLegend scale={PROB} units="probability" format={(x) => `${Math.round(x * 100)}`} />

  return (
    <div className="relative h-full min-h-[560px]">
      {r && (
        <WeatherMap
          grid={r.grid}
          layer={mapLayer}
          layerKey={layerKey}
          smooth={overlays.smooth}
          basemap={overlays.basemap}
          wind={windUV}
          particles={overlays.particles}
          isobars={overlays.isobars ? mslpF?.values ?? null : null}
          cities={overlays.cities}
          cityValue={cityValue}
          selected={cell}
          onSelect={(c) => set({ cell: c, drawer: true })}
          readout={readout}
          stamp={stamp ?? undefined}
          fly={fly}
          rightInset={drawer && cell && wide ? 440 : 0}
        >
          {isExtreme(layer) && xmQ?.type === layer && xmQ.available === false && (
            <div className={cn(glass, 'pointer-events-auto absolute left-1/2 top-16 z-10 max-w-[440px] -translate-x-1/2 border-warn bg-warn-bg px-3 py-2 text-[12.5px] text-warn')}>
              {xmQ.note ?? 'Not available for this run.'}
            </div>
          )}
          {/* top-left: search + layers */}
          <div className="pointer-events-none absolute left-3 top-3 z-10 flex flex-col gap-2">
            <CitySearch />
            <div className="hidden md:block"><LayerRail /></div>
          </div>
          <div className="pointer-events-none absolute inset-x-3 top-14 z-10 md:hidden"><MobileLayers /></div>
          {/* top-right: source + overlays */}
          <div className={cn('pointer-events-none absolute top-3 z-10 flex flex-col items-end gap-2 transition-[right] duration-200', drawer && cell ? 'right-3 lg:right-[452px]' : 'right-3')}>
            <SourcePicker />
            <div className="hidden sm:block"><OverlayToggles /></div>
          </div>
          {/* bottom: legend + days */}
          <div className={cn('pointer-events-none absolute bottom-6 left-3 z-10 flex flex-col gap-2', drawer && cell ? 'right-3 lg:right-[452px]' : 'right-3')}>
            <div className="flex justify-end">{legend}</div>
            <Timeline />
          </div>
          {/* the meteogram drawer (meteoblue) */}
          {drawer && cell && (
            <aside className={cn(glass, 'pointer-events-auto absolute z-20 flex flex-col bg-surface',
              'inset-x-0 bottom-0 max-h-[62%] lg:inset-x-auto lg:bottom-3 lg:right-3 lg:top-3 lg:max-h-none lg:w-[430px]')}>
              <header className="flex items-center gap-2 border-b border-rule px-3 py-2">
                <LineChart className="size-4" />
                <span className="label">Meteogram · all models</span>
                <button type="button" onClick={() => set({ drawer: false })} className="ml-auto grid size-7 place-items-center hover:bg-surface-2" aria-label="Close meteogram"><X className="size-4" /></button>
              </header>
              <div className="min-h-0 flex-1 overflow-y-auto scroll-thin"><Meteogram compact /></div>
            </aside>
          )}
          {!drawer && cell && (
            <button type="button" onClick={() => set({ drawer: true })} className={cn(glass, 'pointer-events-auto absolute right-3 top-[180px] z-10 hidden items-center gap-2 px-3 py-2 text-[13px] sm:flex')}>
              <LineChart className="size-4" /> Meteogram
            </button>
          )}
        </WeatherMap>
      )}
    </div>
  )
}
