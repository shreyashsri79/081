"""C2 Harmonise: same grid, units, cases and valid time for every model."""

import numpy as np
import pandas as pd
import xarray as xr

from . import config as C


def to_display_units(ds: xr.Dataset) -> xr.Dataset:
    """Precipitation m -> mm. Temperature stays in K.

    WB2 stores carry no units on precipitation, and FuXi's `total_precipitation_24hr_from_6hr` is already
    in mm while the others are in m. A 24 h total averaged over a year and the whole domain is a few mm,
    i.e. ~0.003 m, so a mean above 0.05 can only be mm."""
    if C.RAIN in ds:
        already_mm = float(ds[C.RAIN].mean(skipna=True)) > 0.05
        ds = ds.assign({C.RAIN: ds[C.RAIN] * (1.0 if already_mm else 1000.0)})
    return ds


def stack_models(forecasts: dict, var: str) -> xr.DataArray:
    """{model: Dataset} -> DataArray (model, init, lead, latitude, longitude) on the inits all models share."""
    arrays = [ds[var].expand_dims(model=[m]) for m, ds in forecasts.items() if var in ds]
    return xr.concat(arrays, "model", join="inner")


def align_truth(fc: xr.DataArray, truth: xr.DataArray) -> xr.DataArray:
    """Truth at valid = init + lead, dims (init, lead, latitude, longitude)."""
    lead = xr.DataArray(pd.to_timedelta(fc.lead.values, unit="D"), dims="lead", coords={"lead": fc.lead})
    valid = (fc.init + lead).transpose("init", "lead")
    # reindex first so valid times past the end of the truth archive become NaN instead of a KeyError
    obs = truth.reindex(time=np.unique(valid.values)).sel(time=valid)
    return obs.drop_vars("time").assign_coords(valid=valid)


def common_mask(fc: xr.DataArray, obs: xr.DataArray):
    """Drop a cell/case if any model or the truth is missing, so every model is scored on the same cases."""
    ok = fc.notnull().all("model") & obs.notnull()
    return fc.where(ok), obs.where(ok), ok


def prepare(forecasts: dict, truth: xr.Dataset, var: str, regime_labels: pd.DataFrame | None = None):
    """Everything C2 does for one variable. Returns (fc, obs) ready for training.

    Adds coords along init: `season`, and `regime_key` ('SEASON:regime' of the init day) if labels are given."""
    fc = stack_models({m: to_display_units(ds) for m, ds in forecasts.items()}, var)
    tr = to_display_units(truth)[var]
    obs = align_truth(fc, tr)
    fc, obs, _ = common_mask(fc, obs)
    coords = {"season": ("init", [C.SEASON_OF_MONTH[m] for m in pd.DatetimeIndex(fc.init.values).month])}
    if regime_labels is not None:
        from .regimes import regime_keys
        coords["regime_key"] = ("init", regime_keys(fc.init.values, regime_labels))
    return fc.assign_coords(coords), obs.assign_coords(coords)
