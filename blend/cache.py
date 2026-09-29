"""Local cache of small NetCDF files.

Forecasts: fc_{model}_{year}[_{tag}].nc, where each file may hold a different subset of variables
(a later run that adds rain writes fc_hres_2020_rain.nc next to the older file). Loaders merge them.
Truth: truth_era5[_{tag}].nc for ERA5 variables, truth_chirps.nc for rain.
"""

import glob
import os

import xarray as xr


def fc_path(cache: str, model: str, year: int, tag: str | None = None) -> str:
    return os.path.join(cache, f"fc_{model}_{year}{'_' + tag if tag else ''}.nc")


def truth_path(cache: str, tag: str | None = None) -> str:
    return os.path.join(cache, f"truth_era5{'_' + tag if tag else ''}.nc")


def chirps_path(cache: str) -> str:
    return os.path.join(cache, "truth_chirps.nc")


def find_cache(default: str = "/kaggle/working/cache") -> str:
    """Locate the cache dir: attached Kaggle input first, then the working dir."""
    hits = sorted(glob.glob("/kaggle/input/**/truth_era5*.nc", recursive=True))
    return os.path.dirname(hits[0]) if hits else default


def _files(cache, stem):
    return sorted(f for f in glob.glob(os.path.join(cache, stem + "*.nc")) if not f.endswith(".tmp"))


def fc_files(cache, model, year):
    return [f for f in _files(cache, f"fc_{model}_{year}")
            if os.path.basename(f)[len(f"fc_{model}_{year}"):][:1] in ("", ".", "_")]


def variables_in(files) -> set:
    out = set()
    for f in files:
        with xr.open_dataset(f) as ds:
            out |= set(ds.data_vars)
    return out


def _merge(files):
    return xr.merge([xr.load_dataset(f) for f in files], join="inner", compat="override")


def load_forecasts(cache: str, models, years) -> dict:
    out = {}
    for m in models:
        per_year = [_merge(fc_files(cache, m, y)) for y in years if fc_files(cache, m, y)]
        if per_year:
            out[m] = xr.concat(per_year, "init", join="inner").sortby("init")
    return out


def load_truth(cache: str) -> xr.Dataset:
    """ERA5 truth, with rain replaced by CHIRPS when truth_chirps.nc exists."""
    tr = xr.merge([xr.load_dataset(f) for f in _files(cache, "truth_era5")], join="outer", compat="override")
    if os.path.exists(chirps_path(cache)):
        rain = xr.load_dataset(chirps_path(cache))
        tr = xr.merge([tr.drop_vars([v for v in rain.data_vars if v in tr]), rain], join="outer")
    return tr
