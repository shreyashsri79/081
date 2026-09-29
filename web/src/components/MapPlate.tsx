import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Grid } from '@/lib/contract'
import { ASPECT, BOX, OUTLINE, STATES, fmtLat, fmtLon, project, ringsToPath, stateIndex } from '@/lib/geo'

type RGB = [number, number, number]

interface Props {
  grid: Grid
  /** Colour of cell k, or null to leave it blank. Recomputed when `version` changes. */
  paint: (k: number) => RGB | null
  version: string
  selected: [number, number] | null
  onSelect: (c: [number, number]) => void
  readout: (k: number) => ReactNode
  /** Stamp shown over the plate, e.g. "SYNTHETIC". */
  stamp?: string
  caption?: ReactNode
}

const PAD = { l: 34, r: 8, t: 8, b: 22 }

/**
 * The plate: a gridded field over India, drawn cell by cell with no
 * smoothing, because the grid is the truth of the data. Cells outside India
 * are shown faded; the outline and state lines sit on top.
 */
export default function MapPlate({ grid, paint, version, selected, onSelect, readout, stamp, caption }: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState({ w: 600, h: 600 })
  const [hover, setHover] = useState<{ k: number; x: number; y: number } | null>(null)

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => {
      const W = e.contentRect.width, H = e.contentRect.height
      const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b
      const h = Math.max(200, Math.min(ih, iw / ASPECT))
      setSize({ w: Math.round(h * ASPECT), h: Math.round(h) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const idx = useMemo(() => stateIndex(grid), [grid])

  // Cell rectangle in plate pixels.
  const cellRect = (i: number, j: number) => {
    const lon = grid.lon0 + j * grid.step, lat = grid.lat0 + i * grid.step, h = grid.step / 2
    const [x0, y0] = project(lon - h, lat + h, size.w, size.h)
    const [x1, y1] = project(lon + h, lat - h, size.w, size.h)
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
  }

  useEffect(() => {
    const c = canvas.current
    if (!c) return
    const off = document.createElement('canvas')
    off.width = grid.nx
    off.height = grid.ny
    const octx = off.getContext('2d')!
    const img = octx.createImageData(grid.nx, grid.ny)
    for (let i = 0; i < grid.ny; i++)
      for (let j = 0; j < grid.nx; j++) {
        const k = i * grid.nx + j
        const p = (grid.ny - 1 - i) * grid.nx + j // image row 0 is north
        const rgb = paint(k)
        if (!rgb) continue
        img.data[p * 4] = rgb[0]
        img.data[p * 4 + 1] = rgb[1]
        img.data[p * 4 + 2] = rgb[2]
        img.data[p * 4 + 3] = idx[k] >= 0 ? 255 : 120
      }
    octx.putImageData(img, 0, 0)

    const dpr = Math.min(2, window.devicePixelRatio || 1)
    c.width = size.w * dpr
    c.height = size.h * dpr
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.imageSmoothingEnabled = false
    const a = cellRect(grid.ny - 1, 0), b = cellRect(0, grid.nx - 1)
    ctx.clearRect(0, 0, size.w, size.h)
    ctx.drawImage(off, a.x, a.y, b.x + b.w - a.x, b.y + b.h - a.y)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, size, grid, idx])

  const outline = useMemo(() => ringsToPath(OUTLINE, size.w, size.h), [size])
  const states = useMemo(() => STATES.map((s) => ringsToPath(s.rings, size.w, size.h)).join(''), [size])

  const toCell = (x: number, y: number): [number, number] | null => {
    const lon = BOX.lon0 + (x / size.w) * (BOX.lon1 - BOX.lon0)
    const lat = BOX.lat1 - (y / size.h) * (BOX.lat1 - BOX.lat0)
    const i = Math.round((lat - grid.lat0) / grid.step), j = Math.round((lon - grid.lon0) / grid.step)
    return i >= 0 && i < grid.ny && j >= 0 && j < grid.nx ? [i, j] : null
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (!selected) return
    const d: Record<string, [number, number]> = { ArrowUp: [1, 0], ArrowDown: [-1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }
    const m = d[e.key]
    if (!m) return
    e.preventDefault()
    const i = Math.min(grid.ny - 1, Math.max(0, selected[0] + m[0])), j = Math.min(grid.nx - 1, Math.max(0, selected[1] + m[1]))
    onSelect([i, j])
  }

  const sel = selected && cellRect(selected[0], selected[1])
  const hov = hover && cellRect(Math.floor(hover.k / grid.nx), hover.k % grid.nx)
  const lats = [10, 15, 20, 25, 30, 35]
  const lons = [70, 75, 80, 85, 90, 95]

  return (
    <div ref={wrap} className="relative flex h-full min-h-[320px] w-full items-center justify-center">
      <div className="relative" style={{ width: size.w + PAD.l + PAD.r, height: size.h + PAD.t + PAD.b }}>
        <div className="absolute frame bg-surface" style={{ left: PAD.l, top: PAD.t, width: size.w, height: size.h }}>
          <canvas ref={canvas} style={{ width: size.w, height: size.h }} className="absolute inset-0" aria-hidden />
          <svg
            width={size.w}
            height={size.h}
            className="absolute inset-0 cursor-crosshair outline-none"
            tabIndex={0}
            role="application"
            aria-label="Map of India. Click a cell to inspect it; arrow keys move the selection."
            onKeyDown={onKey}
            onMouseMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              const c = toCell(e.clientX - r.left, e.clientY - r.top)
              setHover(c ? { k: c[0] * grid.nx + c[1], x: e.clientX - r.left, y: e.clientY - r.top } : null)
            }}
            onMouseLeave={() => setHover(null)}
            onClick={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              const c = toCell(e.clientX - r.left, e.clientY - r.top)
              if (c) onSelect(c)
            }}
          >
            {lats.map((la) => { const y = project(0, la, size.w, size.h)[1]; return <line key={la} x1={0} x2={size.w} y1={y} y2={y} stroke="rgb(14 33 41 / .08)" /> })}
            {lons.map((lo) => { const x = project(lo, 0, size.w, size.h)[0]; return <line key={lo} y1={0} y2={size.h} x1={x} x2={x} stroke="rgb(14 33 41 / .08)" /> })}
            <path d={states} fill="none" stroke="rgb(14 33 41 / .35)" strokeWidth={0.6} strokeLinejoin="round" />
            <path d={outline} fill="none" stroke="#0e2129" strokeWidth={1.1} strokeLinejoin="round" />
            {hov && <rect x={hov.x} y={hov.y} width={hov.w} height={hov.h} fill="none" stroke="#0e2129" strokeWidth={1} />}
            {sel && (
              <g pointerEvents="none">
                <rect x={sel.x - 2} y={sel.y - 2} width={sel.w + 4} height={sel.h + 4} fill="none" stroke="#f8f7f5" strokeWidth={3} />
                <rect x={sel.x - 2} y={sel.y - 2} width={sel.w + 4} height={sel.h + 4} fill="none" stroke="#0e2129" strokeWidth={1.5} />
              </g>
            )}
          </svg>
          {stamp && (
            <div className="pointer-events-none absolute right-2 top-2 border border-bad bg-surface/90 px-2 py-0.5 mono text-[10.5px] font-medium tracking-wider text-bad">
              {stamp}
            </div>
          )}
          {hover && (
            <div
              className="pointer-events-none absolute z-10 frame raised bg-surface px-2.5 py-1.5 text-[12px]"
              style={{ left: Math.min(hover.x + 14, size.w - 190), top: Math.max(4, hover.y - 58) }}
            >
              <div className="mono text-[11px] text-ink-3">
                {fmtLat(grid.lat0 + Math.floor(hover.k / grid.nx) * grid.step)} {fmtLon(grid.lon0 + (hover.k % grid.nx) * grid.step)}
                {idx[hover.k] >= 0 && <span className="ml-1.5 font-sans text-ink-2">{STATES[idx[hover.k]].name}</span>}
              </div>
              {readout(hover.k)}
            </div>
          )}
        </div>
        {lats.map((la) => (
          <span key={la} className="absolute mono text-[10px] text-ink-3" style={{ left: 0, top: PAD.t + project(0, la, size.w, size.h)[1] - 7, width: PAD.l - 5, textAlign: 'right' }}>{la}°N</span>
        ))}
        {lons.map((lo) => (
          <span key={lo} className="absolute mono text-[10px] text-ink-3" style={{ top: PAD.t + size.h + 4, left: PAD.l + project(lo, 0, size.w, size.h)[0] - 14, width: 28, textAlign: 'center' }}>{lo}°E</span>
        ))}
      </div>
      {caption && <div className="absolute bottom-0 left-0 text-[11px] text-ink-3">{caption}</div>}
    </div>
  )
}
