import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Minus, Plus, Scan } from 'lucide-react'
import { useReducedMotion } from 'motion/react'
import type { Grid } from '@/lib/contract'
import { sample, type Scale } from '@/lib/colour'
import { CITIES } from '@/lib/cities'
import { BOX, OUTLINE, STATES, fmtLat, fmtLon, stateAt, stateIndex } from '@/lib/geo'
import india from '@/geo/india.json'

type RGB = [number, number, number]

export type MapLayer =
  | { kind: 'scalar'; values: Float32Array; scale: Scale }
  | { kind: 'paint'; paint: (k: number) => RGB | null }

export interface Fly { lon: number; lat: number; zoom?: number; n: number }

/** Initial framing: put (lon, lat) at fraction (ax, ay) of the box, showing `span` degrees of latitude. */
export interface Home { lon: number; lat: number; span: number; ax: number; ay: number }

interface Props {
  grid: Grid
  layer: MapLayer | null
  /** Changes whenever the layer's content changes. */
  layerKey: string
  /** Bilinear-smoothed field (Ventusky look) vs raw grid cells. */
  smooth?: boolean
  wind?: { u: Float32Array; v: Float32Array } | null
  particles?: boolean
  /** MSLP values: draws isobars every 2 hPa with H / L centres. */
  isobars?: Float32Array | null
  cities?: boolean
  /** Text shown at each city, e.g. "31°". Null shows the name only. */
  cityValue?: (k: number) => string | null
  selected?: [number, number] | null
  onSelect?: (c: [number, number]) => void
  readout?: (k: number) => ReactNode
  stamp?: string
  fly?: Fly | null
  children?: ReactNode
  className?: string
  /** Pixels to keep clear on the right (an open drawer); zoom controls move left of it. */
  rightInset?: number
  /** OpenStreetMap tiles under the field. Falls back to plain ground when offline. */
  basemap?: boolean
  /** Field opacity over the basemap. */
  fieldOpacity?: number
  /** false: a backdrop. No pan, zoom, hover or controls. */
  interactive?: boolean
  home?: Home
  /** Opacity multiplier for field and wind outside India (1 = no emphasis). */
  outsideIndia?: number
}

// ---------------------------------------------------------------- world
//
// Web Mercator, so OpenStreetMap tiles line up. World units are degrees:
// x = lon − 65, y = M(40) − M(lat), with M the Mercator ordinate in degrees.

const DEG = 180 / Math.PI
const M = (lat: number) => DEG * Math.log(Math.tan(Math.PI / 4 + lat / (2 * DEG)))
const Minv = (m: number) => DEG * (2 * Math.atan(Math.exp(m / DEG)) - Math.PI / 2)
const MTOP = M(BOX.lat1)
const wx = (lon: number) => lon - BOX.lon0
const wy = (lat: number) => MTOP - M(lat)
const lonOf = (x: number) => x + BOX.lon0
const latOf = (y: number) => Minv(MTOP - y)
const WORLD_W = BOX.lon1 - BOX.lon0
const WORLD_H = MTOP - M(BOX.lat0)

function pathOf(rings: number[][][], close: boolean) {
  const p = new Path2D()
  for (const r of rings) {
    r.forEach(([lon, lat], k) => (k ? p.lineTo(wx(lon), wy(lat)) : p.moveTo(wx(lon), wy(lat))))
    if (close) p.closePath()
  }
  return p
}
let PATHS: { outline: Path2D; states: Path2D; neighbours: Path2D } | null = null
const paths = () =>
  (PATHS ??= {
    outline: pathOf(OUTLINE, true),
    states: pathOf(STATES.flatMap((s) => s.rings), true),
    neighbours: pathOf((india as { neighbours?: number[][][] }).neighbours ?? [], false),
  })

/** Bilinear sample of a grid field at fractional grid coordinates. */
function bilinear(g: Grid, f: Float32Array, gi: number, gj: number) {
  const i0 = Math.max(0, Math.min(g.ny - 2, Math.floor(gi))), j0 = Math.max(0, Math.min(g.nx - 2, Math.floor(gj)))
  const ti = Math.min(1, Math.max(0, gi - i0)), tj = Math.min(1, Math.max(0, gj - j0))
  const a = f[i0 * g.nx + j0], b = f[i0 * g.nx + j0 + 1], c = f[(i0 + 1) * g.nx + j0], d = f[(i0 + 1) * g.nx + j0 + 1]
  return a * (1 - ti) * (1 - tj) + b * (1 - ti) * tj + c * ti * (1 - tj) + d * ti * tj
}

/** 0 at the edge of the data, 1 once FEATHER degrees inside: the field dissolves into the basemap. */
const FEATHER = 4
function feather(lon: number, lat: number) {
  const d = Math.min(lon - BOX.lon0, BOX.lon1 - lon, lat - BOX.lat0, BOX.lat1 - lat) / FEATHER
  const t = Math.min(1, Math.max(0, d))
  return t * t * (3 - 2 * t)
}

// ------------------------------------------------------ OpenStreetMap tiles

const TILE_URL = (z: number, x: number, y: number) => `https://tile.openstreetmap.org/${z}/${x}/${y}.png`
const tiles = new Map<string, { img: HTMLImageElement; ok: boolean }>()
const tileListeners = new Set<() => void>()
function tile(z: number, x: number, y: number) {
  const key = `${z}/${x}/${y}`
  let t = tiles.get(key)
  if (!t) {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    t = { img, ok: false }
    tiles.set(key, t)
    const entry = t
    img.onload = () => { entry.ok = true; tileListeners.forEach((f) => f()) }
    img.src = TILE_URL(z, x, y)
  }
  return t
}

// ------------------------------------------------------------- isobars

interface Iso { major: Path2D; minor: Path2D; labels: { x: number; y: number; t: string }[]; centres: { x: number; y: number; hi: boolean; v: number }[] }

function isobars(g: Grid, f: Float32Array): Iso {
  let lo = Infinity, hi = -Infinity
  for (const v of f) { lo = Math.min(lo, v); hi = Math.max(hi, v) }
  const major = new Path2D(), minor = new Path2D()
  const labels: Iso['labels'] = []
  const X = (j: number) => wx(g.lon0 + j * g.step), Y = (i: number) => wy(g.lat0 + i * g.step)
  for (let level = Math.ceil(lo / 2) * 2; level <= hi; level += 2) {
    const p = level % 4 === 0 ? major : minor
    let count = 0
    for (let i = 0; i < g.ny - 1; i++)
      for (let j = 0; j < g.nx - 1; j++) {
        const a = f[i * g.nx + j], b = f[i * g.nx + j + 1], c = f[(i + 1) * g.nx + j + 1], d = f[(i + 1) * g.nx + j]
        const pts: [number, number][] = []
        const edge = (v0: number, v1: number, x0: number, y0: number, x1: number, y1: number) => {
          if ((v0 < level) !== (v1 < level)) { const t = (level - v0) / (v1 - v0); pts.push([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t]) }
        }
        edge(a, b, X(j), Y(i), X(j + 1), Y(i))
        edge(b, c, X(j + 1), Y(i), X(j + 1), Y(i + 1))
        edge(c, d, X(j + 1), Y(i + 1), X(j), Y(i + 1))
        edge(d, a, X(j), Y(i + 1), X(j), Y(i))
        for (let k = 0; k + 1 < pts.length; k += 2) {
          p.moveTo(pts[k][0], pts[k][1]); p.lineTo(pts[k + 1][0], pts[k + 1][1])
          if (++count % 90 === 45) labels.push({ x: pts[k][0], y: pts[k][1], t: String(level) })
        }
      }
  }
  const centres: Iso['centres'] = []
  const R = 5
  for (let i = R; i < g.ny - R; i++)
    for (let j = R; j < g.nx - R; j++) {
      const v = f[i * g.nx + j]
      let isMax = true, isMin = true, sum = 0, n = 0
      for (let di = -R; di <= R; di++)
        for (let dj = -R; dj <= R; dj++) {
          if (!di && !dj) continue
          const w = f[(i + di) * g.nx + j + dj]
          if (w >= v) isMax = false
          if (w <= v) isMin = false
          sum += w; n++
        }
      if ((isMax || isMin) && Math.abs(v - sum / n) > 0.8) centres.push({ x: X(j), y: Y(i), hi: isMax, v })
    }
  return { major, minor, labels, centres }
}

// ----------------------------------------------------------- component

interface View { s: number; tx: number; ty: number }
interface Drag { x: number; y: number; moved: boolean; pts: Map<number, [number, number]>; dist?: number }

export default function WeatherMap(props: Props) {
  const {
    grid, layer, layerKey, smooth = true, wind, particles, isobars: iso, cities, cityValue, selected = null, onSelect, readout,
    stamp, fly, children, className, rightInset = 0, basemap = true, fieldOpacity = 0.74, interactive = true, home, outsideIndia = 1,
  } = props
  const box = useRef<HTMLDivElement>(null)
  const base = useRef<HTMLCanvasElement>(null)
  const flow = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [view, setView] = useState<View | null>(null)
  const touched = useRef(false)
  const [hover, setHover] = useState<{ k: number; x: number; y: number } | null>(null)
  const [tileTick, setTileTick] = useState(0)
  const reduce = useReducedMotion()

  // Redraw when a tile arrives, batched to one frame.
  useEffect(() => {
    let raf = 0
    const on = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; setTileTick((t) => t + 1) }) }
    tileListeners.add(on)
    return () => { tileListeners.delete(on); cancelAnimationFrame(raf) }
  }, [])

  // ---- size and fit
  const homeKey = home ? `${home.lon},${home.lat},${home.span},${home.ax},${home.ay}` : ''
  const fitView = useCallback((w: number, h: number): View => {
    if (home) {
      const s = h / (M(home.lat + home.span / 2) - M(home.lat - home.span / 2))
      return { s, tx: home.ax * w - wx(home.lon) * s, ty: home.ay * h - wy(home.lat) * s }
    }
    const s = Math.min(w / WORLD_W, h / WORLD_H) * 0.96
    return { s, tx: (w - WORLD_W * s) / 2, ty: (h - WORLD_H * s) / 2 }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [homeKey])
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => {
      const w = Math.floor(e.contentRect.width), h = Math.floor(e.contentRect.height)
      setSize({ w, h })
      setView((v) => (!v || !touched.current ? fitView(w, h) : v))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [fitView])
  const s0 = size.w ? Math.min(size.w / WORLD_W, size.h / WORLD_H) * 0.96 : 1

  const clampView = useCallback((v: View): View => {
    const s = Math.min(s0 * 12, Math.max(s0 * 0.8, v.s))
    const minTx = size.w * 0.5 - WORLD_W * s, maxTx = size.w * 0.5
    const minTy = size.h * 0.5 - WORLD_H * s, maxTy = size.h * 0.5
    return { s, tx: Math.min(maxTx, Math.max(minTx, v.tx)), ty: Math.min(maxTy, Math.max(minTy, v.ty)) }
  }, [s0, size])

  const zoomAt = useCallback((f: number, px: number, py: number) => {
    touched.current = true
    setView((v) => {
      if (!v) return v
      const s = Math.min(s0 * 12, Math.max(s0 * 0.8, v.s * f))
      const k = s / v.s
      return clampView({ s, tx: px - (px - v.tx) * k, ty: py - (py - v.ty) * k })
    })
  }, [s0, clampView])

  // ---- fly to a place
  useEffect(() => {
    if (!fly || !size.w) return
    touched.current = true
    const from = view ?? fitView(size.w, size.h)
    const s1 = s0 * (fly.zoom ?? 3)
    const to = clampView({ s: s1, tx: size.w / 2 - wx(fly.lon) * s1, ty: size.h / 2 - wy(fly.lat) * s1 })
    if (reduce) { setView(to); return }
    let raf = 0
    const t0 = performance.now()
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / 650), e = 1 - (1 - p) ** 3
      setView({ s: from.s + (to.s - from.s) * e, tx: from.tx + (to.tx - from.tx) * e, ty: from.ty + (to.ty - from.ty) * e })
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fly?.n])

  // ---- field image, resampled onto Mercator rows (rebuilt only when the data changes)
  // Per-cell weight: 1 inside India, `outsideIndia` elsewhere (interpolated, so the step is soft).
  const emphasis = useMemo(() => {
    const idx = stateIndex(grid)
    const e = new Float32Array(idx.length)
    for (let k = 0; k < idx.length; k++) e[k] = idx[k] >= 0 ? 1 : outsideIndia
    return e
  }, [grid, outsideIndia])

  const image = useMemo(() => {
    if (!layer) return null
    // Scalars smooth by interpolating values. Paint layers are categorical, so
    // they are sampled per cell and softened by the browser's image smoothing.
    const smoothOn = smooth && layer.kind === 'scalar'
    const softPaint = smooth && layer.kind === 'paint'
    const h = smoothOn ? 0 : grid.step / 2
    const lonA = grid.lon0 - h, lonB = grid.lon0 + (grid.nx - 1) * grid.step + h
    const latA = grid.lat0 - h, latB = grid.lat0 + (grid.ny - 1) * grid.step + h
    const U = softPaint ? 1 : 4
    const iw = smoothOn ? (grid.nx - 1) * U + 1 : grid.nx * U
    const ih = smoothOn ? (grid.ny - 1) * U + 1 : grid.ny * (softPaint ? 2 : U)
    const mA = M(latA), mB = M(latB)
    const c = document.createElement('canvas')
    c.width = iw; c.height = ih
    const ctx = c.getContext('2d')!
    const img = ctx.createImageData(iw, ih)
    const colour = (k: number, gi: number, gj: number): RGB | null =>
      layer.kind === 'scalar'
        ? sample(layer.scale, smoothOn ? bilinear(grid, layer.values, gi, gj) : layer.values[k])
        : layer.paint(k)
    for (let py = 0; py < ih; py++) {
      const lat = Minv(mB - ((py + (smoothOn ? 0 : 0.5)) / (smoothOn ? ih - 1 : ih)) * (mB - mA))
      const gi = (lat - grid.lat0) / grid.step
      const ri = Math.max(0, Math.min(grid.ny - 1, Math.round(gi)))
      for (let px = 0; px < iw; px++) {
        const lon = smoothOn ? lonA + (px / (iw - 1)) * (lonB - lonA) : lonA + ((px + 0.5) / iw) * (lonB - lonA)
        const gj = (lon - grid.lon0) / grid.step
        const rj = Math.max(0, Math.min(grid.nx - 1, Math.round(gj)))
        // paint layers are categorical: nearest cell, even when drawn smooth
        const rgb = colour(ri * grid.nx + rj, gi, gj)
        if (!rgb) continue
        const o = (py * iw + px) * 4
        const a = basemap ? feather(lon, lat) * (outsideIndia < 1 ? bilinear(grid, emphasis, gi, gj) : 1) : 1
        img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2]; img.data[o + 3] = Math.round(255 * a)
      }
    }
    ctx.putImageData(img, 0, 0)
    return { c, smooth: smoothOn || softPaint, x0: wx(lonA), y0: wy(latB), w: lonB - lonA, h: mB - mA }
    // Keyed on the data itself, not only the key: a placeholder field kept while
    // the next one loads must never be painted with the next layer's scale.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layerKey, smooth, grid, layer && (layer.kind === 'scalar' ? layer.values : layer.paint), layer && layer.kind === 'scalar' && layer.scale, basemap, emphasis])

  const isoData = useMemo(() => (iso ? isobars(grid, iso) : null), [iso, grid])

  // ---- draw the static layer
  useEffect(() => {
    const c = base.current
    if (!c || !view || !size.w) return
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    c.width = size.w * dpr; c.height = size.h * dpr
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.fillStyle = '#e4e2de'
    ctx.fillRect(0, 0, size.w, size.h)

    // OpenStreetMap basemap, desaturated so the forecast colours lead
    let tilesDrawn = 0
    if (basemap) {
      const z = Math.max(2, Math.min(12, Math.ceil(Math.log2((360 * view.s * dpr) / 256))))
      const n = 2 ** z, span = 360 / n
      const xA = Math.floor(((lonOf(-view.tx / view.s) + 180) / 360) * n)
      const xB = Math.floor(((lonOf((size.w - view.tx) / view.s) + 180) / 360) * n)
      const mT = MTOP - (-view.ty / view.s), mBt = MTOP - (size.h - view.ty) / view.s
      const yA = Math.max(0, Math.floor(((1 - mT / 180) / 2) * n)), yB = Math.min(n - 1, Math.floor(((1 - mBt / 180) / 2) * n))
      ctx.save()
      ctx.filter = 'saturate(0.45) contrast(0.92) brightness(1.03)'
      for (let ty = yA; ty <= yB; ty++)
        for (let tx = xA; tx <= xB; tx++) {
          const t = tile(z, ((tx % n) + n) % n, ty)
          if (!t.ok) continue
          const x = (tx * span - 180 - BOX.lon0) * view.s + view.tx
          const y = (MTOP - 180 * (1 - (2 * ty) / n)) * view.s + view.ty
          ctx.drawImage(t.img, x, y, span * view.s + 0.5, span * view.s + 0.5)
          tilesDrawn++
        }
      ctx.restore()
    }

    const P = paths()
    ctx.save()
    ctx.setTransform(dpr * view.s, 0, 0, dpr * view.s, dpr * view.tx, dpr * view.ty)
    const px = 1 / view.s
    if (image) {
      ctx.globalAlpha = basemap && tilesDrawn ? fieldOpacity : 1
      ctx.imageSmoothingEnabled = image.smooth
      ctx.imageSmoothingQuality = 'high'
      ctx.drawImage(image.c, image.x0, image.y0, image.w, image.h)
      ctx.globalAlpha = 1
    }
    ctx.lineJoin = 'round'
    if (!tilesDrawn) { ctx.strokeStyle = 'rgba(14,33,41,0.55)'; ctx.lineWidth = 0.8 * px; ctx.stroke(P.neighbours) }
    ctx.strokeStyle = 'rgba(14,33,41,0.32)'; ctx.lineWidth = 0.6 * px; ctx.stroke(P.states)
    // Survey of India boundary, always on top of any basemap
    ctx.strokeStyle = 'rgba(248,247,245,0.8)'; ctx.lineWidth = 3 * px; ctx.stroke(P.outline)
    ctx.strokeStyle = '#0e2129'; ctx.lineWidth = 1.3 * px; ctx.stroke(P.outline)
    if (isoData) {
      ctx.strokeStyle = 'rgba(14,33,41,0.75)'; ctx.lineWidth = 1.1 * px; ctx.stroke(isoData.major)
      ctx.strokeStyle = 'rgba(14,33,41,0.45)'; ctx.lineWidth = 0.7 * px; ctx.stroke(isoData.minor)
    }
    // static wind arrows when motion is reduced
    if (wind && particles && reduce) {
      const stride = Math.max(1, Math.round(38 / (grid.step * view.s)))
      ctx.strokeStyle = 'rgba(14,33,41,0.6)'; ctx.lineWidth = 1 * px
      for (let i = 0; i < grid.ny; i += stride)
        for (let j = 0; j < grid.nx; j += stride) {
          const k = i * grid.nx + j, u = wind.u[k], v = wind.v[k], sp = Math.hypot(u, v)
          if (sp < 0.5) continue
          const x = wx(grid.lon0 + j * grid.step), y = wy(grid.lat0 + i * grid.step), L = (8 + sp) * px
          const ex = x + (u / sp) * L, ey = y - (v / sp) * L
          const a = Math.atan2(-(v / sp), u / sp)
          ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(ex, ey)
          ctx.lineTo(ex - Math.cos(a - 0.5) * 4 * px, ey - Math.sin(a - 0.5) * 4 * px)
          ctx.moveTo(ex, ey); ctx.lineTo(ex - Math.cos(a + 0.5) * 4 * px, ey - Math.sin(a + 0.5) * 4 * px)
          ctx.stroke()
        }
    }
    ctx.restore()

    const S = (x: number, y: number) => [x * view.s + view.tx, y * view.s + view.ty] as const
    ctx.textBaseline = 'middle'; ctx.textAlign = 'center'
    const halo = (t: string, x: number, y: number, font: string, fill: string) => {
      ctx.font = font; ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(248,247,245,0.9)'; ctx.strokeText(t, x, y); ctx.fillStyle = fill; ctx.fillText(t, x, y)
    }
    if (isoData) {
      for (const l of isoData.labels) { const [x, y] = S(l.x, l.y); halo(l.t, x, y, '500 10px "IBM Plex Mono"', '#0e2129') }
      for (const c of isoData.centres) {
        const [x, y] = S(c.x, c.y)
        halo(c.hi ? 'H' : 'L', x, y - 6, '700 20px "Source Serif 4 Variable", serif', '#0e2129')
        halo(c.v.toFixed(0), x, y + 10, '500 10px "IBM Plex Mono"', '#0e2129')
      }
    }

    // domain edge: on plain ground a dashed box says where data ends; over the
    // street map the field is feathered out instead, so no hard rectangle.
    if (!(basemap && tilesDrawn)) {
      ctx.setLineDash([4, 4]); ctx.strokeStyle = 'rgba(14,33,41,0.4)'; ctx.lineWidth = 1
      const [dx0, dy0] = S(0, 0), [dx1, dy1] = S(WORLD_W, WORLD_H)
      ctx.strokeRect(dx0, dy0, dx1 - dx0, dy1 - dy0)
      ctx.setLineDash([])
    }

    if (cities) {
      const zr = view.s / s0
      const placed: [number, number, number, number][] = []
      for (const c of CITIES) {
        if (c.rank === 2 && zr < 1.35) continue
        if (c.rank === 3 && zr < 2.2) continue
        const [x, y] = S(wx(c.lon), wy(c.lat))
        if (x < -40 || y < -20 || x > size.w + 40 || y > size.h + 20) continue
        const i = Math.round((c.lat - grid.lat0) / grid.step), j = Math.round((c.lon - grid.lon0) / grid.step)
        const inside = i >= 0 && i < grid.ny && j >= 0 && j < grid.nx
        const val = inside && cityValue ? cityValue(i * grid.nx + j) : null
        const bw = val ? Math.max(30, val.length * 7.4 + 10) : 0
        const half = Math.max(bw, c.name.length * 6) / 2
        const bb: [number, number, number, number] = [x - half, y - 11, x + half, y + 22]
        if (placed.some((p) => !(bb[2] < p[0] || bb[0] > p[2] || bb[3] < p[1] || bb[1] > p[3]))) continue
        placed.push(bb)
        if (val) {
          ctx.fillStyle = 'rgba(248,247,245,0.94)'; ctx.fillRect(x - bw / 2, y - 10, bw, 19)
          ctx.strokeStyle = '#0e2129'; ctx.lineWidth = 1; ctx.strokeRect(x - bw / 2 + 0.5, y - 9.5, bw - 1, 18)
          ctx.font = '600 12px "IBM Plex Mono"'; ctx.fillStyle = '#0e2129'; ctx.fillText(val, x, y)
          halo(c.name, x, y + 17, '500 11px "Geist Variable", sans-serif', '#0e2129')
        } else {
          ctx.fillStyle = '#0e2129'; ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill()
          halo(c.name, x, y + 12, '500 11px "Geist Variable", sans-serif', '#0e2129')
        }
      }
    }

    if (selected) {
      const [x, y] = S(wx(grid.lon0 + selected[1] * grid.step), wy(grid.lat0 + selected[0] * grid.step))
      ctx.fillStyle = '#0e2129'
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 7, y - 13); ctx.arc(x, y - 17, 8, Math.PI * 0.8, Math.PI * 0.2); ctx.closePath(); ctx.fill()
      ctx.fillStyle = '#f8f7f5'; ctx.beginPath(); ctx.arc(x, y - 17, 3, 0, Math.PI * 2); ctx.fill()
    }
  }, [view, size, image, isoData, cities, cityValue, selected, grid, s0, wind, particles, reduce, basemap, fieldOpacity, tileTick])

  // ---- wind particles (Ventusky / earth.nullschool style)
  useEffect(() => {
    const c = flow.current
    if (!c || !view || !size.w) return
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    c.width = size.w * dpr; c.height = size.h * dpr
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, size.w, size.h)
    if (!wind || !particles || reduce) return

    const lonA = Math.max(BOX.lon0, lonOf(-view.tx / view.s)), lonB = Math.min(BOX.lon1, lonOf((size.w - view.tx) / view.s))
    const latB = Math.min(BOX.lat1, latOf(-view.ty / view.s)), latA = Math.max(BOX.lat0, latOf((size.h - view.ty) / view.s))
    if (lonB <= lonA || latB <= latA) return
    const areaPx = (lonB - lonA) * view.s * (M(latB) - M(latA)) * view.s
    const N = Math.round(Math.min(5000, Math.max(600, areaPx / 170)))
    const lon = new Float32Array(N), lat = new Float32Array(N), age = new Uint16Array(N)
    const spawn = (k: number) => { lon[k] = lonA + Math.random() * (lonB - lonA); lat[k] = latA + Math.random() * (latB - latA); age[k] = Math.floor(Math.random() * 80) }
    for (let k = 0; k < N; k++) spawn(k)
    const K = 0.34 / view.s // world units per frame per m/s: constant speed on screen
    let raf = 0
    const frame = () => {
      ctx.globalCompositeOperation = 'destination-in'
      ctx.fillStyle = 'rgba(0,0,0,0.93)'; ctx.fillRect(0, 0, size.w, size.h)
      ctx.globalCompositeOperation = 'source-over'
      ctx.lineWidth = 1.15
      // four alpha buckets: particles fade toward the data edge (and outside India when emphasised)
      const buckets = [new Path2D(), new Path2D(), new Path2D(), new Path2D()]
      for (let k = 0; k < N; k++) {
        const gi = (lat[k] - grid.lat0) / grid.step, gj = (lon[k] - grid.lon0) / grid.step
        if (gi < 0 || gj < 0 || gi > grid.ny - 1 || gj > grid.nx - 1 || ++age[k] > 110) { spawn(k); continue }
        const u = bilinear(grid, wind.u, gi, gj), v = bilinear(grid, wind.v, gi, gj)
        const x0 = wx(lon[k]) * view.s + view.tx, y0 = wy(lat[k]) * view.s + view.ty
        lon[k] += u * K
        lat[k] += v * K * Math.cos(lat[k] / DEG) // Mercator stretch
        const x1 = wx(lon[k]) * view.s + view.tx, y1 = wy(lat[k]) * view.s + view.ty
        let a = basemap ? feather(lon[k], lat[k]) : 1
        if (outsideIndia < 1) a *= emphasis[Math.round(gi) * grid.nx + Math.round(gj)]
        if (a < 0.08) continue
        const p = buckets[Math.min(3, Math.floor(a * 4))]
        p.moveTo(x0, y0); p.lineTo(x1, y1)
      }
      buckets.forEach((p, b) => { ctx.strokeStyle = `rgba(14,33,41,${(0.7 * (b + 1)) / 4})`; ctx.stroke(p) })
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [wind, particles, reduce, view, size, grid, basemap, emphasis, outsideIndia])

  // ---- pointer interaction: drag to pan, wheel / pinch to zoom, click to select
  const drag = useRef<Drag | null>(null)
  const toCell = (x: number, y: number): [number, number] | null => {
    if (!view) return null
    const lon = lonOf((x - view.tx) / view.s), lat = latOf((y - view.ty) / view.s)
    const i = Math.round((lat - grid.lat0) / grid.step), j = Math.round((lon - grid.lon0) / grid.step)
    return i >= 0 && i < grid.ny && j >= 0 && j < grid.nx ? [i, j] : null
  }
  useEffect(() => {
    const el = box.current
    if (!el || !interactive) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      zoomAt(Math.exp(-e.deltaY * 0.0016), e.clientX - r.left, e.clientY - r.top)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [zoomAt, interactive])

  const onDown = (e: React.PointerEvent) => {
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    const d: Drag = drag.current ?? { x: e.clientX, y: e.clientY, moved: false, pts: new Map() }
    d.pts.set(e.pointerId, [e.clientX, e.clientY])
    if (d.pts.size === 2) { const [a, b] = [...d.pts.values()]; d.dist = Math.hypot(a[0] - b[0], a[1] - b[1]); d.moved = true }
    drag.current = d
  }
  const onMove = (e: React.PointerEvent) => {
    const r = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - r.left, y = e.clientY - r.top
    const d = drag.current
    if (!d) {
      const c = readout ? toCell(x, y) : null
      setHover(c ? { k: c[0] * grid.nx + c[1], x, y } : null)
      return
    }
    const prev = d.pts.get(e.pointerId)
    d.pts.set(e.pointerId, [e.clientX, e.clientY])
    if (d.pts.size === 2 && d.dist) {
      const [a, b] = [...d.pts.values()]
      const dist = Math.hypot(a[0] - b[0], a[1] - b[1])
      zoomAt(dist / d.dist, (a[0] + b[0]) / 2 - r.left, (a[1] + b[1]) / 2 - r.top)
      d.dist = dist
      return
    }
    if (!prev) return
    const dx = e.clientX - prev[0], dy = e.clientY - prev[1]
    if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 4) d.moved = true
    if (d.moved) {
      touched.current = true
      setHover(null)
      setView((v) => (v ? clampView({ s: v.s, tx: v.tx + dx, ty: v.ty + dy }) : v))
    }
  }
  const onUp = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d) return
    d.pts.delete(e.pointerId)
    if (d.pts.size > 0) return
    if (!d.moved && onSelect) {
      const r = e.currentTarget.getBoundingClientRect()
      const c = toCell(e.clientX - r.left, e.clientY - r.top)
      if (c) onSelect(c)
    }
    drag.current = null
  }
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === '+' || e.key === '=') return zoomAt(1.3, size.w / 2, size.h / 2)
    if (e.key === '-') return zoomAt(1 / 1.3, size.w / 2, size.h / 2)
    if (!selected || !onSelect) return
    const m = ({ ArrowUp: [1, 0], ArrowDown: [-1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] } as Record<string, [number, number]>)[e.key]
    if (!m) return
    e.preventDefault()
    onSelect([Math.min(grid.ny - 1, Math.max(0, selected[0] + m[0])), Math.min(grid.nx - 1, Math.max(0, selected[1] + m[1]))])
  }

  const hi = hover ? Math.floor(hover.k / grid.nx) : 0, hj = hover ? hover.k % grid.nx : 0
  const hlat = grid.lat0 + hi * grid.step, hlon = grid.lon0 + hj * grid.step
  const hs = hover ? stateAt(hlon, hlat) : -1

  return (
    <div className={`relative h-full w-full overflow-hidden bg-surface-2 ${className ?? ''}`}>
      {interactive ? (
        <div
          ref={box}
          className="absolute inset-0 touch-none select-none outline-none"
          style={{ cursor: 'crosshair' }}
          tabIndex={0}
          role="application"
          aria-label="Forecast map of India. Drag to pan, scroll to zoom, click to pick a point; arrow keys move the point, + and − zoom."
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
          onPointerLeave={() => setHover(null)}
          onKeyDown={onKey}
          onDoubleClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); zoomAt(1.8, e.clientX - r.left, e.clientY - r.top) }}
        >
          <canvas ref={base} className="absolute inset-0 h-full w-full" />
          <canvas ref={flow} className="pointer-events-none absolute inset-0 h-full w-full" />
        </div>
      ) : (
        <div ref={box} className="pointer-events-none absolute inset-0" aria-hidden>
          <canvas ref={base} className="absolute inset-0 h-full w-full" />
          <canvas ref={flow} className="absolute inset-0 h-full w-full" />
        </div>
      )}

      {hover && readout && (
        <div className="pointer-events-none absolute z-20 frame raised bg-surface px-2.5 py-1.5 text-[12px]"
          style={{ left: Math.min(hover.x + 16, size.w - 200), top: Math.max(8, hover.y - 64) }}>
          <div className="mono text-[11px] text-ink-3">
            {fmtLat(hlat)} {fmtLon(hlon)}
            {hs >= 0 && <span className="ml-1.5 font-sans text-ink-2">{STATES[hs].name}</span>}
          </div>
          {readout(hover.k)}
        </div>
      )}

      {stamp && (
        <div className="pointer-events-none absolute bottom-[100px] left-3 z-10 hidden border border-bad bg-surface/90 px-2 py-0.5 mono text-[10.5px] font-medium tracking-wider text-bad md:block">
          {stamp}
        </div>
      )}

      {interactive && (
        <div className="absolute top-1/2 z-10 flex -translate-y-1/2 flex-col frame bg-surface raised transition-[right] duration-200" style={{ right: 12 + rightInset }}>
          <button type="button" className="grid size-8 place-items-center hover:bg-surface-2" onClick={() => zoomAt(1.4, size.w / 2, size.h / 2)} aria-label="Zoom in"><Plus className="size-4" /></button>
          <button type="button" className="grid size-8 place-items-center border-y border-rule hover:bg-surface-2" onClick={() => zoomAt(1 / 1.4, size.w / 2, size.h / 2)} aria-label="Zoom out"><Minus className="size-4" /></button>
          <button type="button" className="grid size-8 place-items-center hover:bg-surface-2" onClick={() => { touched.current = false; setView(fitView(size.w, size.h)) }} aria-label="Show all of India"><Scan className="size-4" /></button>
        </div>
      )}

      {basemap && (
        <div className="absolute bottom-0 z-10 bg-surface/85 px-1.5 py-0.5 text-[10.5px] leading-tight text-ink-2" style={{ right: rightInset }}>
          ©{' '}<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer" className="pointer-events-auto underline hover:text-ink">OpenStreetMap</a> contributors
        </div>
      )}

      {children}
    </div>
  )
}
