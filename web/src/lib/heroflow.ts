/**
 * Hero-only wind field: a hand-built stand-in for the look of a real late-monsoon surface wind map
 * (Ventusky-style), used purely as the landing page's moving backdrop. Not model data; the forecast desk
 * always draws bundle winds.
 *
 * Returns (u, v) in m/s-like units at (lon, lat) and time t (seconds). Pattern:
 *   - south-westerly monsoon flow across the Arabian Sea into the west coast, strongest near 10-15° N;
 *   - westerlies across the Bay of Bengal, curling round a cyclonic swirl near the Andamans;
 *   - arcs and eddies near the equator south-west of India;
 *   - a fast westerly jet over Tibet and the Karakoram, bending round the Afghan high;
 *   - light, variable air over the Indian landmass and the Gangetic plain.
 * Vortex centres drift slowly so the loop never looks canned.
 */

const g = (x: number, y: number, cx: number, cy: number, sx: number, sy: number) =>
  Math.exp(-(((x - cx) / sx) ** 2) - ((y - cy) / sy) ** 2)

type Vortex = { cx: number; cy: number; r: number; s: number; ax: number; ay: number; w: number }

// s > 0: anticlockwise (cyclonic in the northern hemisphere)
const VORTICES: Vortex[] = [
  { cx: 91.5, cy: 15.5, r: 4.5, s: 9, ax: 1.2, ay: 0.8, w: 0.05 },     // Bay of Bengal / Andaman swirl
  { cx: 66, cy: 1.5, r: 5.5, s: -8, ax: 1.5, ay: 1.0, w: 0.04 },       // eddies south-west of India
  { cx: 80.5, cy: -2.5, r: 4, s: 7, ax: 1.0, ay: 0.7, w: 0.06 },       // equatorial curl south of Sri Lanka
  { cx: 62, cy: 33, r: 5, s: -6, ax: 1.0, ay: 0.8, w: 0.03 },          // Afghan high
  { cx: 71, cy: 27, r: 3.5, s: 4, ax: 0.8, ay: 0.6, w: 0.05 },         // Thar heat low
  { cx: 58, cy: 16, r: 4, s: -5, ax: 1.2, ay: 0.9, w: 0.045 },         // Arabian Sea anticyclonic bend
]

// Smooth scalar "weather" texture so streak speed and direction vary like a real field.
function texture(lon: number, lat: number, t: number) {
  return (
    Math.sin(lon * 0.21 + t * 0.03) * Math.cos(lat * 0.27 - t * 0.02) +
    0.6 * Math.sin(lon * 0.47 - lat * 0.33 + t * 0.05) +
    0.35 * Math.cos(lon * 0.9 + lat * 0.7 - t * 0.07)
  )
}

export function heroWind(lon: number, lat: number, t: number): [number, number] {
  // large-scale flow by latitude band
  const sw = g(lon, lat, 66, 12, 22, 7)                 // Arabian Sea monsoon
  const bay = g(lon, lat, 88, 11, 14, 6)                // Bay of Bengal westerlies
  const eq = g(lon, lat, 78, 2, 40, 5)                  // near-equatorial westerlies
  const jet = 1 / (1 + Math.exp(-(lat - 31) * 0.9))     // subtropical jet over Tibet
  const trades = 1 / (1 + Math.exp((lat + 4) * 0.8))    // south-easterly trades far south
  let u = 11 * sw + 8 * bay + 5 * eq + 13 * jet - 5 * trades
  let v = 4.5 * sw + 1.5 * bay + 0.5 * eq + 1.5 * jet * Math.sin(lon * 0.08) + 3 * trades

  // light, variable air over the Indian landmass and the Gangetic plain
  const land = g(lon, lat, 78.5, 21.5, 8, 9) + 0.8 * g(lon, lat, 83, 26, 9, 3)
  const damp = 1 - 0.75 * Math.min(1, land)
  u = u * damp + land * (-1.5 + 1.2 * texture(lon, lat, t))
  v = v * damp + land * (0.8 * texture(lat, lon, t + 40))

  // Himalaya: flow turns along the range instead of crossing it
  const ridge = g(lat, 0, 29.5 - (lon - 80) * 0.33, 0, 1.6, 1)
  v *= 1 - 0.8 * ridge
  u += 3 * ridge

  // drifting vortices
  for (const k of VORTICES) {
    const cx = k.cx + k.ax * Math.sin(t * k.w), cy = k.cy + k.ay * Math.cos(t * k.w * 1.3)
    const dx = lon - cx, dy = lat - cy
    const r2 = (dx * dx + dy * dy) / (k.r * k.r)
    const f = k.s * Math.exp(-r2) / k.r
    u += -dy * f
    v += dx * f
  }

  // small-scale texture on everything
  const n = texture(lon, lat, t)
  const speed = Math.hypot(u, v)
  const turn = 0.25 * n
  const c = Math.cos(turn), s = Math.sin(turn)
  const k = 1 + 0.25 * n
  return [(u * c - v * s) * k + (speed < 1 ? 0.6 * n : 0), (u * s + v * c) * k]
}
