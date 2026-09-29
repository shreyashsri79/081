"""Local cache: one NetCDF file per (model, year) plus one truth file. Few files keep Kaggle outputs tidy."""

import glob
import os

import xarray as xr


def fc_path(cache: str, model: str, year: int) -> str:
    return os.path.join(cache, f"fc_{model}_{year}.nc")


def truth_path(cache: str) -> str:
    return os.path.join(cache, "truth_era5.nc")


def find_cache(default: str = "/kaggle/working/cache") -> str:
    """Locate the cache dir: attached Kaggle input first, then the working dir."""
    hits = sorted(glob.glob("/kaggle/input/**/truth_era5.nc", recursive=True))
    return os.path.dirname(hits[0]) if hits else default


def load_forecasts(cache: str, models, years) -> dict:
    out = {}
    for m in models:
        files = [fc_path(cache, m, y) for y in years if os.path.exists(fc_path(cache, m, y))]
        if files:
            out[m] = xr.concat([xr.load_dataset(f) for f in files], "init").sortby("init")
    return out


def load_truth(cache: str) -> xr.Dataset:
    return xr.load_dataset(truth_path(cache))
