"""C3 Rain truth: CHIRPS 2.0 daily (0.25°, land only) block-averaged onto the WB2 1.5° grid.

A forecast `total_precipitation_24hr` valid at 00 UTC on day V covers 00 UTC V-1 to 00 UTC V, so CHIRPS
day V-1 is stored at time V 00 UTC. Values are stored in metres, like WB2, so harmonise.py treats
truth and forecasts the same way (m -> mm).
"""

import os
import urllib.request

import numpy as np
import pandas as pd
import xarray as xr

from . import config as C

URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/netcdf/p25/chirps-v2.0.{year}.days_p25.nc"
STEP = 1.5              # target grid spacing
SUB = 6                 # 0.25° cells per 1.5° cell, each direction
MIN_LAND = 0.5          # a coarse cell needs at least half its CHIRPS cells on land


def fetch(year: int, dest_dir: str) -> str:
    path = os.path.join(dest_dir, f"chirps_p25_{year}.nc")
    if not os.path.exists(path):
        urllib.request.urlretrieve(URL.format(year=year), path + ".tmp")
        os.replace(path + ".tmp", path)
    return path


def to_wb2_grid(raw: xr.DataArray, lats: np.ndarray, lons: np.ndarray) -> xr.DataArray:
    """Block mean of 0.25° CHIRPS onto 1.5° cells centred on (lats, lons); cell edges at centre ± 0.75°."""
    raw = raw.sortby("latitude").sortby("longitude")
    half = STEP / 2
    sub = raw.sel(latitude=slice(lats[0] - half, lats[-1] + half), longitude=slice(lons[0] - half, lons[-1] + half))
    ny, nx = len(lats), len(lons)
    assert sub.sizes["latitude"] == ny * SUB and sub.sizes["longitude"] == nx * SUB, dict(sub.sizes)
    a = sub.values.reshape(sub.sizes["time"], ny, SUB, nx, SUB)
    land = np.isfinite(a).mean(axis=(2, 4))
    with np.errstate(invalid="ignore"):
        m = np.nanmean(a, axis=(2, 4))
    m[land < MIN_LAND] = np.nan
    return xr.DataArray(m, dims=("time", "latitude", "longitude"),
                        coords={"time": sub.time.values, "latitude": lats, "longitude": lons})


def load_rain_truth(years, cache: str, lats: np.ndarray, lons: np.ndarray) -> xr.Dataset:
    """Daily rain truth for `years` (+ the first 11 days of the next year for Day-10 valid times)."""
    raw_dir = os.path.join(cache, "chirps_raw")
    os.makedirs(raw_dir, exist_ok=True)
    need = sorted(set(years) | {y + 1 for y in years})
    parts = []
    for y in need:
        try:
            path = fetch(y, raw_dir)
        except Exception as e:  # the following year may not be needed or published
            print(f"CHIRPS {y}: {e}")
            continue
        with xr.open_dataset(path) as ds:
            da = ds["precip"].rename({"lat": "latitude", "lon": "longitude"}) if "lat" in ds.dims else ds["precip"]
            da = da.where(da >= 0).load()
        if y not in years:
            da = da.sel(time=slice(f"{y}-01-01", f"{y}-01-11"))
        parts.append(to_wb2_grid(da, lats, lons))
    rain = xr.concat(parts, "time")
    # CHIRPS day d is the 24 h ending at 00 UTC on d+1
    rain = rain.assign_coords(time=pd.DatetimeIndex(rain.time.values).normalize() + pd.Timedelta(days=1))
    return xr.Dataset({C.RAIN: (rain / 1000.0).astype("float32")})
