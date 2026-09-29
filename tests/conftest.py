"""Tiny, offline stand-ins for the Kaggle cache (plan §7.2). No test ever touches the network.

Forecast = truth(valid) + model bias + noise, with GraphCast the most accurate, HRES next, Pangu worst.
Files use the exact names and WB2 units that blend/cache.py and run_all.py produce (rain in metres,
temperature in K, pressure in Pa).
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from blend import config as C
from blend.cache import fc_path, truth_path

LAT = np.array([6.0, 7.5, 9.0, 10.5, 12.0])
LON = np.array([72.0, 73.5, 75.0, 76.5, 78.0])
YEARS = [2018, 2020, 2022]
MODELS = ["hres", "graphcast", "pangu"]
NOISE = {"hres": 1.0, "graphcast": 0.6, "pangu": 1.4, "fuxi": 0.9, "gencast": 0.8}
BIAS = {"hres": 0.3, "graphcast": -0.2, "pangu": 0.5, "fuxi": 0.1, "gencast": -0.1}


def _dates(year, months=(7,), days=30):
    out = []
    for m in months:
        out += list(pd.date_range(f"{year}-{m:02d}-01", periods=days, freq="D"))
    return pd.DatetimeIndex(out)


def make_truth(years, months=(7,), days=30, seed=C.SEED) -> xr.Dataset:
    """ERA5 stand-in: 00 UTC daily from the first init to the last init + 10 days."""
    rng = np.random.default_rng(seed)
    t = pd.DatetimeIndex(sorted(set().union(*[
        pd.date_range(d, periods=11, freq="D") for y in years for d in _dates(y, months, days)])))
    shape = (len(t), len(LAT), len(LON))
    base = rng.normal(size=shape)
    return xr.Dataset(
        {
            C.T2M: (("time", "latitude", "longitude"), 300.0 + 2.0 * base),
            C.WIND: (("time", "latitude", "longitude"), 6.0 + np.abs(base)),
            C.MSLP: (("time", "latitude", "longitude"), 100800.0 + 300.0 * base),
            C.RAIN: (("time", "latitude", "longitude"), np.abs(base) * 0.01),  # metres
        },
        coords={"time": t, "latitude": LAT, "longitude": LON},
    )


def make_forecast(truth: xr.Dataset, model: str, year: int, months=(7,), days=30, seed=C.SEED) -> xr.Dataset:
    rng = np.random.default_rng(seed + 1000 * list(NOISE).index(model) + year)  # fixed per model-year
    inits = _dates(year, months, days)
    lead = np.arange(1, 11)
    out = {}
    for var in [C.T2M, C.WIND, C.MSLP, C.RAIN]:
        if model == "pangu" and var == C.RAIN:
            continue  # Pangu has no precipitation, as in WB2
        scale = {C.T2M: 1.0, C.WIND: 0.5, C.MSLP: 100.0, C.RAIN: 0.002}[var]
        valid = inits.values[:, None] + (lead * np.timedelta64(1, "D"))[None, :]
        tr = truth[var].sel(time=xr.DataArray(valid, dims=("init", "lead"))).values
        noise = rng.normal(size=tr.shape) * NOISE[model] * scale * (1 + lead[None, :, None, None] / 10)
        val = tr + BIAS[model] * scale + noise
        if var == C.RAIN:
            val = np.maximum(val, 0)
        out[var] = (("init", "lead", "latitude", "longitude"), val)
    ds = xr.Dataset(out, coords={"init": inits, "lead": lead, "latitude": LAT, "longitude": LON})
    ds.attrs["model"] = model
    return ds


def make_regime_indices(seed=C.SEED) -> pd.DataFrame:
    """regime_indices.csv stand-in covering the climatology years and the forecast years."""
    rng = np.random.default_rng(seed)
    d = pd.date_range("2003-01-01", "2023-01-10", freq="D")
    df = pd.DataFrame({
        "cmz_rain": rng.gamma(2.0, 3.0, len(d)),
        "nw_rain": rng.gamma(1.0, 1.0, len(d)),
        "heat_t2m": 300 + rng.normal(0, 2, len(d)),
        "bay_mslp_min": 100000 + rng.normal(0, 200, len(d)),
    }, index=d)
    df.index.name = "date"
    return df


def write_cache(cache, models=MODELS, years=YEARS, months=(7,), days=30):
    cache.mkdir(parents=True, exist_ok=True)
    truth = make_truth(years, months, days)
    truth.to_netcdf(truth_path(str(cache)))
    for m in models:
        for y in years:
            make_forecast(truth, m, y, months, days).to_netcdf(fc_path(str(cache), m, y))
    make_regime_indices().to_csv(cache / "regime_indices.csv")
    return cache


@pytest.fixture
def fake_cache(tmp_path):
    return write_cache(tmp_path / "cache")
