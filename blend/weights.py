"""C6 Weights: inverse-MSE weights and the blend."""

import xarray as xr

from . import config as C


def inverse_mse(mse: xr.DataArray, alpha: float = C.ALPHA) -> xr.DataArray:
    """w_m = (1/MSE_m)^alpha / sum_j (1/MSE_j)^alpha. alpha=0 gives the equal mean."""
    inv = mse ** (-alpha)
    return inv / inv.sum("model")


def blend(fc_bc: xr.DataArray, w: xr.DataArray) -> xr.DataArray:
    """sum_m w_m * f~_m. Weights with a season axis are matched to each init's season."""
    if "season" in w.dims:
        w = w.sel(season=fc_bc.season).drop_vars("season")
    return (fc_bc * w).sum("model", skipna=False)


def dominant_model(w: xr.DataArray) -> xr.DataArray:
    """Name of the model with the largest weight in each cell."""
    return w.idxmax("model")
