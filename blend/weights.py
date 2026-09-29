"""C6 Weights: inverse-MSE weights and the blend."""

import numpy as np
import xarray as xr

from . import config as C


def inverse_mse(mse: xr.DataArray, alpha: float = C.ALPHA) -> xr.DataArray:
    """w_m = (1/MSE_m)^alpha / sum_j (1/MSE_j)^alpha. alpha=0 gives the equal mean."""
    inv = mse ** (-alpha)
    return inv / inv.sum("model")


def min_variance(cov: xr.DataArray, shrink: float = 0.1) -> xr.DataArray:
    """Weights w >= 0, sum 1, minimising w' S w for each cell (rung B2c / B3c).

    S is the error covariance between models, shrunk 10 % toward its diagonal for stability. With
    uncorrelated errors this equals inverse-MSE; with correlated errors it stops double-counting
    models that make the same mistakes. Solved exactly for small M by an active-set loop."""
    c = cov.transpose(..., "m1", "m2")
    other = c.dims[:-2]
    arr = np.asarray(c.values, dtype="float64")
    M = arr.shape[-1]
    S = arr.reshape(-1, M, M).copy()
    eye = np.eye(M)
    ok = np.isfinite(S).all((1, 2))
    S[~ok] = eye
    diag = np.einsum("nii->ni", S)
    S = (1 - shrink) * S + shrink * diag[:, :, None] * eye
    S[diag.max(1) <= 1e-12] = eye   # no error at all (e.g. always-dry cell): equal weights
    S += 1e-9 * (diag.mean(1)[:, None, None] + 1e-12) * eye
    active = np.ones((S.shape[0], M), bool)
    for _ in range(M):
        Sa = np.where(active[:, :, None] & active[:, None, :], S, eye)
        x = np.where(active, np.linalg.solve(Sa, active[..., None].astype(float))[..., 0], 0.0)
        w = x / x.sum(1, keepdims=True)
        neg = (w < 0) & active
        if not neg.any():
            break
        rows = np.flatnonzero(neg.any(1))
        active[rows, np.where(neg, w, np.inf)[rows].argmin(1)] = False
    w = np.clip(w, 0, None)
    w = w / w.sum(1, keepdims=True)
    w[~ok] = np.nan
    out = xr.DataArray(w.reshape(arr.shape[:-2] + (M,)), dims=other + ("model",),
                       coords={**{d: c[d] for d in other if d in c.coords}, "model": c.m1.values})
    return out.transpose("model", ...)


def blend(fc_bc: xr.DataArray, w: xr.DataArray) -> xr.DataArray:
    """sum_m w_m * f~_m. Weights with a season or regime_key axis are matched to each init's value."""
    for key in ("season", "regime_key"):
        if key in w.dims:
            w = w.sel({key: fc_bc[key]}).drop_vars(key)
    return (fc_bc * w).sum("model", skipna=False)


def dominant_model(w: xr.DataArray) -> xr.DataArray:
    """Name of the model with the largest weight in each cell."""
    return w.idxmax("model")
