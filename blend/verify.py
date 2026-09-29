"""C8 Verification: held-out folds, the ladder B0..B3s, block-bootstrap confidence intervals.

Rungs built here (MVP, spec §5.6):
  <model>  raw single model
  B0       best raw single model per lead, chosen on the training folds   (the bar)
  B0bc     best bias-corrected single model per lead, chosen on training (fair bar after bias correction)
  B1       equal mean of bias-corrected models
  B2       inverse-MSE weights per cell x lead
  B3s      B2 + season (shrunk toward B2)             -- regime axis is added in B3 proper
"""

import numpy as np
import pandas as pd
import xarray as xr

from . import config as C
from .skill import apply_bias, fit_bias, fit_mse
from .weights import blend, inverse_mse

BLENDS = ["B1", "B2", "B3s"]


def lat_weights(da: xr.DataArray) -> xr.DataArray:
    return np.cos(np.deg2rad(da.latitude))


def domain_se(pred: xr.DataArray, obs: xr.DataArray) -> xr.DataArray:
    """Latitude-weighted domain-mean squared error per (init, lead)."""
    return ((pred - obs) ** 2).weighted(lat_weights(obs)).mean(["latitude", "longitude"])


def make_folds(init: xr.DataArray, mode: str, gap_days: int = int(C.LEAD_DAYS.max())):
    """[(name, train_mask, test_mask)] over inits. mode = 'loyo' or 'months'.

    For 'months', training inits within gap_days of the test month are dropped: their Day-10 valid
    times would otherwise fall inside the test month and leak its truth into training."""
    t = pd.DatetimeIndex(init.values)
    folds = []
    if mode == "loyo":
        for y in sorted(set(t.year)):
            test = t.year == y
            folds.append((str(y), ~test, test))
    elif mode == "months":
        for m in sorted(set(t.month)):
            test = t.month == m
            lo, hi = t[test].min() - pd.Timedelta(days=gap_days), t[test].max() + pd.Timedelta(days=gap_days)
            train = ~((t >= lo) & (t <= hi))
            folds.append((f"m{m:02d}", train, test))
    else:
        raise ValueError(mode)
    return folds


def fit(fc: xr.DataArray, obs: xr.DataArray, alpha: float = C.ALPHA, k: float = C.K_SHRINK, size: int = C.SMOOTH):
    """Fit every table on the given (training) inits."""
    bias = fit_bias(fc, obs)
    fc_bc = apply_bias(fc, bias)
    mse2 = fit_mse(fc_bc, obs, by_season=False, k=k, size=size)
    mse3 = fit_mse(fc_bc, obs, by_season=True, k=k, size=size)
    raw_rmse = np.sqrt(domain_se(fc, obs).mean("init"))           # (model, lead)
    bc_rmse = np.sqrt(domain_se(fc_bc, obs).mean("init"))
    return {
        "bias": bias,
        "w_B2": inverse_mse(mse2, alpha),
        "w_B3s": inverse_mse(mse3, alpha),
        "best_raw": raw_rmse.idxmin("model"),                     # (lead,) model name
        "best_bc": bc_rmse.idxmin("model"),
    }


def predict(fc: xr.DataArray, p: dict) -> dict:
    """All rung predictions for the given inits, each (init, lead, latitude, longitude)."""
    fc_bc = apply_bias(fc, p["bias"])
    out = {f"m:{m}": fc.sel(model=m, drop=True) for m in fc.model.values}
    out["B0"] = fc.sel(model=p["best_raw"]).drop_vars("model")
    out["B0bc"] = fc_bc.sel(model=p["best_bc"]).drop_vars("model")
    out["B1"] = fc_bc.mean("model", skipna=False)
    out["B2"] = blend(fc_bc, p["w_B2"])
    out["B3s"] = blend(fc_bc, p["w_B3s"])
    return out


def run_folds(fc: xr.DataArray, obs: xr.DataArray, mode: str, **fit_kw):
    """Fit on each training fold, predict the held-out fold.

    Returns
      se     : DataArray (rung, init, lead)  domain-mean squared error on held-out inits
      cell   : DataArray (rung, lead, latitude, longitude)  held-out MSE per cell
      chosen : list of per-fold B0 choices, for the report
    """
    se_parts, cell_sum, cell_n, chosen = [], None, None, []
    for name, train, test in make_folds(fc.init, mode):
        p = fit(fc.isel(init=np.flatnonzero(train)), obs.isel(init=np.flatnonzero(train)), **fit_kw)
        f_te, o_te = fc.isel(init=np.flatnonzero(test)), obs.isel(init=np.flatnonzero(test))
        preds = predict(f_te, p)
        rungs = list(preds)
        stack = xr.concat([preds[r] for r in rungs], pd.Index(rungs, name="rung"))
        se_parts.append(domain_se(stack, o_te))
        sq = (stack - o_te) ** 2
        s, n = sq.sum("init"), sq.count("init")
        cell_sum = s if cell_sum is None else cell_sum + s
        cell_n = n if cell_n is None else cell_n + n
        chosen.append({"fold": name, "B0": p["best_raw"].to_series().to_dict(),
                       "B0bc": p["best_bc"].to_series().to_dict()})
    se = xr.concat(se_parts, "init").sortby("init")
    return se, cell_sum / cell_n, chosen


def block_bootstrap(se_a: np.ndarray, se_b: np.ndarray, n_boot: int = C.N_BOOT,
                    block: int = C.BLOCK_DAYS, seed: int = C.SEED):
    """Paired moving-block bootstrap of RMSE_a - RMSE_b over days. Returns (diff, lo, hi)."""
    ok = np.isfinite(se_a) & np.isfinite(se_b)
    a, b = se_a[ok], se_b[ok]
    n = len(a)
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)).reshape(n_boot, -1)[:, :n]
    d = np.sqrt(a[idx].mean(1)) - np.sqrt(b[idx].mean(1))
    return float(np.sqrt(a.mean()) - np.sqrt(b.mean())), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def scorecard(se: xr.DataArray, var: str, set_name: str, refs=("B0", "B0bc"), **boot_kw) -> pd.DataFrame:
    """One row per (lead, rung): RMSE, and for each blend rung the gain vs each reference with 95 % CI."""
    rows = []
    for lead in se.lead.values:
        s = se.sel(lead=lead)
        for rung in s.rung.values:
            a = s.sel(rung=rung).values
            row = {"set": set_name, "var": var, "lead_day": int(lead), "rung": str(rung),
                   "rmse": float(np.sqrt(np.nanmean(a))), "n_days": int(np.isfinite(a).sum())}
            if rung in BLENDS:
                for ref in refs:
                    b = s.sel(rung=ref).values
                    d, lo, hi = block_bootstrap(a, b, **boot_kw)
                    rmse_ref = float(np.sqrt(np.nanmean(b)))
                    row.update({f"d_vs_{ref}": d, f"lo_vs_{ref}": lo, f"hi_vs_{ref}": hi,
                                f"pct_vs_{ref}": 100 * d / rmse_ref,
                                f"verdict_vs_{ref}": "beats" if hi < 0 else ("worse" if lo > 0 else "matches")})
            rows.append(row)
    return pd.DataFrame(rows)


def headline(card: pd.DataFrame, var: str, lead_day: int = 3, ref: str = "B0") -> str:
    """The one slide-4 sentence, built only from measured numbers."""
    c = card[(card["var"] == var) & (card.lead_day == lead_day)]
    base = c[c.rung == ref].iloc[0]
    blends = c[c.rung.isin(BLENDS)].sort_values("rmse")
    best = blends.iloc[0]
    unit = C.UNITS.get(var, "")
    verdict = best[f"verdict_vs_{ref}"]
    label = "best single model" if ref == "B0" else "best bias-corrected single model"
    return (f"{var} Day-{lead_day} RMSE: {label} {base.rmse:.3f} {unit} -> blend ({best.rung}) "
            f"{best.rmse:.3f} {unit} ({best[f'pct_vs_{ref}']:+.1f} %, 95 % CI "
            f"[{best[f'lo_vs_{ref}']:+.3f}, {best[f'hi_vs_{ref}']:+.3f}] {unit}; {verdict}), "
            f"held-out folds, n = {int(best.n_days)} days.")
