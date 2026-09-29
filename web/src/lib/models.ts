import type { ExtremeId, ModelId, VarId } from './contract'

export interface ModelInfo {
  id: ModelId
  name: string
  short: string
  family: 'Physics NWP' | 'AI' | 'AI ensemble'
  /** CSS custom property, so charts and Tailwind share one source. */
  colour: string
}

/** Okabe–Ito, fixed per model everywhere (PPT guide §7.1). */
export const MODELS: Record<ModelId, ModelInfo> = {
  hres: { id: 'hres', name: 'IFS HRES', short: 'HRES', family: 'Physics NWP', colour: '#0072b2' },
  graphcast: { id: 'graphcast', name: 'GraphCast', short: 'GraphCast', family: 'AI', colour: '#e69f00' },
  pangu: { id: 'pangu', name: 'Pangu-Weather', short: 'Pangu', family: 'AI', colour: '#009e73' },
  fuxi: { id: 'fuxi', name: 'FuXi', short: 'FuXi', family: 'AI', colour: '#cc79a7' },
  gencast: { id: 'gencast', name: 'GenCast (mean)', short: 'GenCast', family: 'AI ensemble', colour: '#d55e00' },
  // Live sources (C10). ECMWF open IFS is the same system as HRES and shares its hue.
  ifs: { id: 'ifs', name: 'ECMWF IFS (open)', short: 'IFS', family: 'Physics NWP', colour: '#0072b2' },
  aifs: { id: 'aifs', name: 'ECMWF AIFS', short: 'AIFS', family: 'AI', colour: '#56b4e9' },
  gfs: { id: 'gfs', name: 'NOAA GFS', short: 'GFS', family: 'Physics NWP', colour: '#6b5b45' },
}

export const BLEND_COLOUR = '#0e2129'

export interface VarInfo {
  id: VarId
  name: string
  short: string
  units: string
  digits: number
}

export const VARS: Record<VarId, VarInfo> = {
  rain: { id: 'rain', name: '24 h rainfall', short: 'Rain', units: 'mm', digits: 1 },
  t2m: { id: 't2m', name: '2 m temperature', short: 'T2m', units: '°C', digits: 1 },
  wind: { id: 'wind', name: '10 m wind speed', short: 'Wind', units: 'm/s', digits: 1 },
  mslp: { id: 'mslp', name: 'Mean sea-level pressure', short: 'MSLP', units: 'hPa', digits: 1 },
}

/** Events of the synthetic source; engine runs carry their own list (Run.extremes). */
export const EXTREMES: Record<ExtremeId, { name: string; short: string; threshold: string; var: VarId }> = {
  rain64: { name: 'Heavy rain', short: 'Heavy', threshold: '≥ 64.5 mm / 24 h', var: 'rain' },
  rain115: { name: 'Very heavy rain', short: 'Very heavy', threshold: '≥ 115.6 mm / 24 h', var: 'rain' },
  rain204: { name: 'Extremely heavy rain', short: 'Extreme', threshold: '≥ 204.5 mm / 24 h', var: 'rain' },
  heat: { name: 'Heat wave', short: 'Heat', threshold: 'IMD criterion, T2m proxy', var: 't2m' },
  wind15: { name: 'High wind', short: 'Wind', threshold: '10 m wind ≥ 15 m/s', var: 'wind' },
}

export const fmt = (v: number, digits = 1) => (Number.isFinite(v) ? v.toFixed(digits) : '—')
