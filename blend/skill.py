"""C5 Skill memory: bias and error tables per model x lead x cell (x season x regime), fitted on training inits only."""

import xarray as xr

from . import config as C


def fit_bias(fc: xr.DataArray, obs: xr.DataArray) -> xr.DataArray:
    """mean(f - o) per season. Dims (season, model, lead, latitude, longitude). A season with no
    training cases gets zero bias."""
    return (fc - obs).groupby("season").mean("init").reindex(season=C.SEASONS).fillna(0.0)


def apply_bias(fc: xr.DataArray, bias: xr.DataArray) -> xr.DataArray:
    out = fc - bias.sel(season=fc.season).drop_vars("season")
    return out.clip(min=0) if fc.name == C.RAIN else out   # additive correction must not make rain negative


def smooth(da: xr.DataArray, size: int = C.SMOOTH) -> xr.DataArray:
    if size <= 1:
        return da
    return da.rolling(latitude=size, longitude=size, center=True, min_periods=1).mean()


def _shrink(mse_child, n_child, mse_parent, k):
    """(n * MSE_child + k * MSE_parent) / (n + k); a bin with no cases falls back to its parent."""
    return (n_child * mse_child.fillna(0) + k * mse_parent) / (n_child + k)


def fit_mse(fc_bc: xr.DataArray, obs: xr.DataArray, level: str, k: float = C.K_SHRINK,
            size: int = C.SMOOTH, keys=None) -> xr.DataArray:
    """Mean squared error of (bias-corrected) forecasts, then smoothed over size x size cells.
    See fit_table for the levels."""
    return fit_table((fc_bc - obs) ** 2, level, k, size, keys)


def fit_cov(fc_bc: xr.DataArray, obs: xr.DataArray, level: str, k: float = C.K_SHRINK,
            size: int = C.SMOOTH, keys=None) -> xr.DataArray:
    """Error second-moment matrix mean(e_i * e_j) between models, dims (m1, m2, ...).
    The AI models share ERA5 training data, so their errors are correlated; inverse-MSE ignores that."""
    e = fc_bc - obs
    return fit_table(e.rename(model="m1") * e.rename(model="m2"), level, k, size, keys)


def fit_table(se: xr.DataArray, level: str, k: float = C.K_SHRINK, size: int = C.SMOOTH, keys=None) -> xr.DataArray:
    """Average `se` (any per-init quantity) over training inits at one level, with shrinkage and smoothing.

    level='all'    : per (model, lead, cell)                                   -> rung B2
    level='season' : per season, shrunk toward 'all'                           -> rung B3s
    level='regime' : per 'SEASON:regime' key, shrunk toward its season, which
                     is shrunk toward 'all'. `keys` lists every key to return,
                     so keys unseen in training fall back to the season table.  -> rung B3
    """
    mse_all = se.mean("init")
    if level == "all":
        return smooth(mse_all, size)
    g = se.groupby("season")
    mse_s = _shrink(g.mean("init").reindex(season=C.SEASONS), g.count("init").reindex(season=C.SEASONS, fill_value=0),
                    mse_all, k)
    if level == "season":
        return smooth(mse_s, size)
    g = se.groupby("regime_key")
    mse_r, n_r = g.mean("init"), g.count("init")
    keys = list(keys) if keys is not None else list(mse_r.regime_key.values)
    mse_r, n_r = mse_r.reindex(regime_key=keys), n_r.reindex(regime_key=keys, fill_value=0)
    parent = mse_s.sel(season=[kk.split(":")[0] for kk in keys]).rename(season="regime_key")
    parent = parent.assign_coords(regime_key=keys)
    return smooth(_shrink(mse_r, n_r, parent, k), size)
