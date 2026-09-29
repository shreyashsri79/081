"""C4 Weather regime labels for each init day, from ERA5, using only information known at forecast time.

Indices (one value per date d, all available by 00 UTC on d):
  cmz_rain      Core Monsoon Zone mean rain, 24 h ending 00 UTC d          (mm)
  nw_rain       NW India mean rain, 24 h ending 00 UTC d                     (mm)
  heat_t2m      NW + central India mean T2m at 12 UTC on d-1 (~17:30 IST)   (K)
  bay_mslp_min  minimum MSLP over the Bay / central India at 00 UTC d        (Pa)

Each index is standardised against a day-of-year climatology from C.CLIM_YEARS (no test year inside).
Labels, in priority order:
  depression          JJAS, bay_mslp_min anomaly < -1.5 sigma
  active / break      JJAS, CMZ rain anomaly > +1 / < -1 sigma on d, d-1 and d-2 (past days only)
  western_disturbance Dec-Apr, NW rain anomaly > +1 sigma
  heat                Mar-Jun, heat_t2m anomaly > +1 sigma
  normal              otherwise
"""

import dask
import numpy as np
import pandas as pd
import xarray as xr

from . import config as C
from .sources import open_store


def _box_series(ds, var, box, hour, how="mean"):
    lat0, lat1, lon0, lon1 = box
    da = ds[var].sel(latitude=slice(lat0, lat1), longitude=slice(lon0, lon1))
    da = da.isel(time=np.flatnonzero(pd.DatetimeIndex(da.time.values).hour == hour))
    if how == "min":
        return da.min(["latitude", "longitude"])
    return da.weighted(np.cos(np.deg2rad(da.latitude))).mean(["latitude", "longitude"])


def download_indices(start: str, end: str, workers: int = 32) -> pd.DataFrame:
    """Daily regime indices from ERA5 for [start, end]. Small: four numbers per day."""
    ds = open_store(C.ERA5).sortby("latitude").sel(time=slice(start, end))
    B = C.REGIME_BOXES
    lazy = {
        "cmz_rain": _box_series(ds, C.RAIN, B["cmz"], 0) * 1000.0,
        "nw_rain": _box_series(ds, C.RAIN, B["nw"], 0) * 1000.0,
        "heat_t2m": _box_series(ds, C.T2M, B["heat"], 12),
        "bay_mslp_min": _box_series(ds, C.MSLP, B["bay"], 0, how="min"),
    }
    with dask.config.set(scheduler="threads", num_workers=workers):
        done = dask.compute(*lazy.values())
    cols = {}
    for name, da in zip(lazy, done):
        idx = pd.DatetimeIndex(da.time.values).normalize()
        if name == "heat_t2m":
            idx = idx + pd.Timedelta(days=1)  # 12 UTC on d-1 is the latest afternoon known at 00 UTC on d
        cols[name] = pd.Series(da.values, index=idx)
    df = pd.DataFrame(cols).sort_index()
    df.index.name = "date"
    return df


def _zscore(s: pd.Series, clim_years) -> pd.Series:
    """Standardised anomaly vs a 31-day-smoothed day-of-year climatology from clim_years."""
    clim = s[(s.index.year >= clim_years[0]) & (s.index.year <= clim_years[1])].dropna()
    if clim.empty:
        raise ValueError(f"no climatology data in {clim_years}")
    doy = np.minimum(clim.index.dayofyear, 365)
    stats = []
    for f in ("mean", "std"):
        v = clim.groupby(doy).agg(f).reindex(range(1, 366)).interpolate(limit_direction="both")
        v = pd.concat([v, v, v]).rolling(31, center=True, min_periods=1).mean().iloc[365:730]
        v.index = range(1, 366)
        stats.append(v)
    mu, sd = stats
    d = np.minimum(s.index.dayofyear, 365)
    return (s - mu.reindex(d).values) / sd.reindex(d).values


def label(indices: pd.DataFrame, clim_years=C.CLIM_YEARS) -> pd.DataFrame:
    """Regime label per date plus the standardised indices behind it."""
    z = pd.DataFrame({c: _zscore(indices[c], clim_years) for c in indices.columns})
    m = z.index.month
    jjas, dec_apr, mar_jun = m.isin([6, 7, 8, 9]), m.isin([12, 1, 2, 3, 4]), m.isin([3, 4, 5, 6])
    # three consecutive days ending on d, looking backwards only
    wet3 = z.cmz_rain.rolling(3, min_periods=3).min() > 1.0
    dry3 = z.cmz_rain.rolling(3, min_periods=3).max() < -1.0

    reg = pd.Series("normal", index=z.index)
    reg[mar_jun & (z.heat_t2m > 1.0)] = "heat"
    reg[dec_apr & (z.nw_rain > 1.0)] = "western_disturbance"
    reg[jjas & dry3] = "break"
    reg[jjas & wet3] = "active"
    reg[jjas & (z.bay_mslp_min < -1.5)] = "depression"   # highest priority, written last
    out = z.add_prefix("z_")
    out["regime"] = reg
    out["season"] = [C.SEASON_OF_MONTH[x] for x in m]
    return out


def regime_keys(dates, labels: pd.DataFrame) -> np.ndarray:
    """'SEASON:regime' for each init date; dates without a label count as normal."""
    d = pd.DatetimeIndex(dates).normalize()
    reg = labels["regime"].reindex(d).fillna("normal").values
    return np.array([f"{C.SEASON_OF_MONTH[x]}:{r}" for x, r in zip(d.month, reg)])


def all_keys():
    return [f"{s}:{r}" for s in C.SEASONS for r in C.REGIMES]
