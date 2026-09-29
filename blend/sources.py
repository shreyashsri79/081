"""C1 Ingest: one loader per source, one output shape.

Every forecast loader returns an xr.Dataset with dims (init, lead, latitude, longitude):
latitude ascending, lead as integer days 1..10, 00 UTC inits only, WB2 variable names,
precipitation still in metres (harmonise.py converts). Variables a model lacks are absent.
"""

import dask
import numpy as np
import pandas as pd
import xarray as xr

from . import config as C


def open_store(url: str) -> xr.Dataset:
    return xr.open_zarr(url, storage_options={"token": "anon"})


def _box(ds: xr.Dataset) -> xr.Dataset:
    ds = ds.rename({k: v for k, v in {"lat": "latitude", "lon": "longitude"}.items() if k in ds.dims})
    ds = ds.sortby("latitude")
    return ds.sel(latitude=slice(*C.LAT), longitude=slice(*C.LON))


def _load(ds: xr.Dataset, workers: int) -> xr.Dataset:
    # WB2 chunks are one init x 8 leads x the whole globe, so reads are many small GCS requests;
    # a wide thread pool is what makes ingest fast.
    with dask.config.set(scheduler="threads", num_workers=workers):
        ds = ds.load()
    # WB2 stores carry boolean/dict attributes that NetCDF cannot hold; keep plain string/number ones
    ds.attrs = {}
    for v in ds.variables:
        ds[v].encoding = {}
        ds[v].attrs = {k: a for k, a in ds[v].attrs.items()
                       if isinstance(a, (str, int, float)) and not isinstance(a, bool)}
    return ds


def _lead_index(lead: xr.DataArray) -> np.ndarray:
    """Positions of Day 1..10 in the lead axis. Recent xarray versions leave WB2 leads as integer
    hours instead of decoding them to timedelta64, so handle both."""
    v = lead.values
    hours = v / np.timedelta64(1, "h") if np.issubdtype(v.dtype, np.timedelta64) else v.astype(float)
    pos = {h: i for i, h in enumerate(hours)}
    missing = [24 * d for d in C.LEAD_DAYS if 24 * d not in pos]
    if missing:
        raise KeyError(f"leads missing (hours): {missing}")
    return np.array([pos[24 * d] for d in C.LEAD_DAYS])


def load_forecast(model: str, variables, years, max_inits: int | None = None, workers: int = 32) -> xr.Dataset:
    """Forecasts of `model` for `years`, India box, 00 UTC inits, Day 1-10."""
    parts = []
    for url, store_years in C.STORES[model]:
        use_years = sorted(set(years) & set(store_years))
        if not use_years:
            continue
        ds = open_store(url)
        if model == "fuxi" and "total_precipitation_24hr_from_6hr" in ds:
            ds = ds.rename({"total_precipitation_24hr_from_6hr": C.RAIN})
        if C.WIND in variables and C.WIND not in ds and "10m_u_component_of_wind" in ds:
            ds[C.WIND] = np.hypot(ds["10m_u_component_of_wind"], ds["10m_v_component_of_wind"])
        keep = [v for v in variables if v in ds]
        if not keep:
            continue
        ds = _box(ds[keep])
        t = pd.DatetimeIndex(ds.time.values)
        idx = np.flatnonzero((t.hour == C.INIT_HOUR) & t.year.isin(use_years))
        if max_inits:
            idx = idx[:max_inits]
        ds = ds.isel(time=idx).isel(prediction_timedelta=_lead_index(ds.prediction_timedelta))
        ds = ds.rename({"time": "init", "prediction_timedelta": "lead"})
        ds = ds.assign_coords(lead=C.LEAD_DAYS)
        ds = ds.drop_vars([c for c in ds.coords if c not in ("init", "lead", "latitude", "longitude")])
        parts.append(_load(ds.transpose("init", "lead", "latitude", "longitude"), workers))
    if not parts:
        raise ValueError(f"{model}: none of {variables} available for {years}")
    out = xr.concat(parts, "init").sortby("init")
    _, first = np.unique(out.init.values, return_index=True)
    out = out.isel(init=np.sort(first))
    out.attrs["model"] = model
    return out


def load_truth(variables, start: str, end: str, workers: int = 32) -> xr.Dataset:
    """ERA5 at 00 UTC for [start, end], India box. Dims (time, latitude, longitude)."""
    ds = open_store(C.ERA5)
    ds = _box(ds[[v for v in variables if v in ds]]).sel(time=slice(start, end))
    ds = ds.isel(time=np.flatnonzero(pd.DatetimeIndex(ds.time.values).hour == C.INIT_HOUR))
    ds = ds.drop_vars([c for c in ds.coords if c not in ("time", "latitude", "longitude")])
    return _load(ds.transpose("time", "latitude", "longitude"), workers)
