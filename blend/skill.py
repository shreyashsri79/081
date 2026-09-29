"""C5 Skill memory: bias and error tables per model x lead x cell (x season), fitted on training inits only."""

import xarray as xr

from . import config as C


def fit_bias(fc: xr.DataArray, obs: xr.DataArray) -> xr.DataArray:
    """mean(f - o) per season. Dims (season, model, lead, latitude, longitude)."""
    return (fc - obs).groupby("season").mean("init")


def apply_bias(fc: xr.DataArray, bias: xr.DataArray) -> xr.DataArray:
    return fc - bias.sel(season=fc.season).drop_vars("season")


def smooth(da: xr.DataArray, size: int = C.SMOOTH) -> xr.DataArray:
    if size <= 1:
        return da
    return da.rolling(latitude=size, longitude=size, center=True, min_periods=1).mean()


def fit_mse(fc_bc: xr.DataArray, obs: xr.DataArray, by_season: bool, k: float = C.K_SHRINK,
            size: int = C.SMOOTH) -> xr.DataArray:
    """Mean squared error of bias-corrected forecasts.

    by_season=False: one table per (model, lead, cell)            -> rung B2
    by_season=True : per season, shrunk toward the all-season MSE -> rung B3 (season part)
        MSE_used = (n * MSE_season + k * MSE_all) / (n + k)
    Both are smoothed over a size x size cell window.
    """
    se = (fc_bc - obs) ** 2
    mse_all = se.mean("init")
    if not by_season:
        return smooth(mse_all, size)
    g = se.groupby("season")
    mse_s, n_s = g.mean("init"), g.count("init")
    return smooth((n_s * mse_s + k * mse_all) / (n_s + k), size)
