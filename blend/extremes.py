"""C7 Extremes: probability of an extreme event, from weighted model votes, calibrated.

Averaging smooths peaks, so extremes are not read from the blended mean. For each event:
  1. Truth threshold per cell: a fixed value (e.g. 64.5 mm) or a training-period percentile (e.g. p95).
  2. Each model gets its own threshold at the same climatological frequency (quantile mapping at one
     point): a smooth model that never reaches 64.5 mm still votes when it is at its own 'rare' level.
  3. p_raw = sum_m w_m * vote_m, with the blend weights (B2c).
  4. Calibration: observed frequency per p_raw bin on training data, forced monotone.
Scored on held-out folds against: the best single model's vote, the blended mean, and climatology.
"""

import numpy as np
import pandas as pd
import xarray as xr

from . import config as C
from . import verify as V

# (name, kind, value): kind 'abs' = fixed threshold in display units; 'q' = per-cell training percentile
EVENTS = {
    # A 1.5° cell is a ~167 km area mean, so IMD point thresholds (64.5 mm) almost never occur;
    # per-cell percentiles keep enough events to score. Switch to IMD values on the 0.25° grid.
    C.RAIN: [("p95", "q", 0.95), ("p99", "q", 0.99), ("25mm", "abs", 25.0)],
    C.T2M: [("p95", "q", 0.95), ("p99", "q", 0.99)],
    C.WIND: [("p95", "q", 0.95), ("p99", "q", 0.99)],
    C.MSLP: [],
}
BINS = np.linspace(0, 1, 11)


def truth_threshold(obs, kind, value):
    if kind == "abs":
        return xr.full_like(obs.isel(init=0, lead=0, drop=True), value, dtype=float)
    return obs.quantile(value, dim=["init", "lead"]).drop_vars("quantile")


def model_thresholds(fc, base_rate):
    """Per (model, lead, cell): the forecast value exceeded as often as the truth exceeds its threshold."""
    a = np.sort(fc.transpose("init", ...).values, axis=0)          # NaN sorts last
    n = np.isfinite(a).sum(0)
    br = np.broadcast_to(base_rate.values, n.shape)
    idx = np.clip(np.ceil((1 - br) * n).astype(int) - 1, 0, np.maximum(n - 1, 0))
    tau = np.take_along_axis(a, idx[None], axis=0)[0]
    tau = np.where((br <= 0) | (n == 0), np.inf, tau)                # never observed: never vote
    return xr.DataArray(tau, dims=fc.transpose("init", ...).dims[1:],
                        coords={d: fc[d] for d in fc.dims if d != "init"})


def fit_calibration(p_raw, event):
    """Observed frequency per p_raw bin per lead, monotone. Returns (lead, bin) table."""
    b = np.clip(np.digitize(p_raw, BINS[1:-1]), 0, len(BINS) - 2)
    ok = np.isfinite(p_raw) & np.isfinite(event)
    table = np.zeros((p_raw.shape[1], len(BINS) - 1))
    for li in range(p_raw.shape[1]):
        bb, ee = b[:, li][ok[:, li]], event[:, li][ok[:, li]]
        cnt = np.bincount(bb, minlength=len(BINS) - 1)
        hit = np.bincount(bb, weights=ee, minlength=len(BINS) - 1)
        centre = (BINS[:-1] + BINS[1:]) / 2
        freq = np.where(cnt >= 20, hit / np.maximum(cnt, 1), centre)
        table[li] = np.maximum.accumulate(freq)
    return table


def apply_calibration(p_raw, table):
    """p_raw dims (init, lead, lat, lon); table dims (lead, bin)."""
    b = np.clip(np.digitize(np.nan_to_num(p_raw), BINS[1:-1]), 0, len(BINS) - 2)
    out = table[np.arange(p_raw.shape[1])[None, :, None, None], b]
    return np.where(np.isfinite(p_raw), out, np.nan)


def contingency(fcst_yes, obs_yes):
    ok = np.isfinite(obs_yes) & np.isfinite(fcst_yes)
    f, o = fcst_yes[ok].astype(bool), obs_yes[ok].astype(bool)
    H, F, M = np.sum(f & o), np.sum(f & ~o), np.sum(~f & o)
    N = ok.sum()
    Hr = (H + M) * (H + F) / max(N, 1)
    return {"POD": H / max(H + M, 1), "FAR": F / max(H + F, 1), "CSI": H / max(H + M + F, 1),
            "ETS": (H - Hr) / max(H + M + F - Hr, 1e-9), "freq_bias": (H + F) / max(H + M, 1), "n_events": int(H + M)}


def _events_for_fold(fc_tr, obs_tr, fc_te, obs_te, p, kind, value):
    thr = truth_threshold(obs_tr, kind, value)
    base = (obs_tr >= thr).where(obs_tr.notnull()).mean(["init", "lead"])
    tau = model_thresholds(fc_tr, base)
    w = p["w_B2c"]

    def prob(fc):
        votes = (fc >= tau).where(fc.notnull())
        return (votes * w).sum("model", skipna=False).transpose("init", "lead", ...), votes

    p_tr, _ = prob(fc_tr)
    ev_tr = (obs_tr >= thr).where(obs_tr.notnull()).transpose("init", "lead", ...)
    table = fit_calibration(p_tr.values, ev_tr.values)
    p_cal_tr = apply_calibration(p_tr.values, table)
    # operating probability: maximise CSI on training
    grid = np.arange(0.05, 0.96, 0.05)
    p_star = grid[np.argmax([contingency(p_cal_tr >= g, ev_tr.values)["CSI"] for g in grid])]

    p_te, votes_te = prob(fc_te)
    p_cal = apply_calibration(p_te.values, table)
    ev = (obs_te >= thr).where(obs_te.notnull()).transpose("init", "lead", ...).values
    clim = np.broadcast_to(base.values, ev.shape[2:])[None, None]
    best = p["best_raw"]
    best_vote = votes_te.sel(model=best).drop_vars("model").transpose("init", "lead", ...).values
    blend_mean = V.predict(fc_te, p)["B2c"].transpose("init", "lead", ...)
    mean_yes = (blend_mean >= thr).where(blend_mean.notnull()).values
    return {"p": p_cal, "ev": ev, "clim": np.broadcast_to(clim, ev.shape), "best": best_vote,
            "mean": mean_yes, "p_star": p_star, "init": fc_te.init.values}


def run(fc, obs, mode, var, set_name):
    """Held-out verification of every event for `var`. Returns (table, fold outputs per event)."""
    rows, keep = [], {}
    events = EVENTS.get(var, [])
    parts = {name: [] for name, _, _ in events}
    for fold, train, test in V.make_folds(fc.init, mode):
        tr, te = np.flatnonzero(train), np.flatnonzero(test)
        p = V.fit(fc.isel(init=tr), obs.isel(init=tr))   # one fit per fold, shared by all events
        for name, kind, value in events:
            parts[name].append(_events_for_fold(fc.isel(init=tr), obs.isel(init=tr), fc.isel(init=te),
                                                obs.isel(init=te), p, kind, value))
    for name, _, _ in events:
        parts_n = parts[name]
        cat = {k: np.concatenate([d[k] for d in parts_n], 0) for k in ("p", "ev", "clim", "best", "mean")}
        p_star = float(np.median([d["p_star"] for d in parts_n]))
        keep[name] = {**cat, "init": np.concatenate([d["init"] for d in parts_n]), "p_star": p_star}
        for li, lead in enumerate(fc.lead.values):
            sl = {k: v[:, li] for k, v in cat.items()}
            ok = np.isfinite(sl["ev"]) & np.isfinite(sl["p"])
            bs = np.mean((sl["p"][ok] - sl["ev"][ok]) ** 2)
            bs_clim = np.mean((sl["clim"][ok] - sl["ev"][ok]) ** 2)
            bs_best = np.mean((sl["best"][ok] - sl["ev"][ok]) ** 2)
            base = {"set": set_name, "var": var, "event": name, "lead_day": int(lead),
                    "base_rate": float(np.mean(sl["ev"][ok])), "BS": bs, "BSS_vs_clim": 1 - bs / bs_clim if bs_clim > 0 else np.nan,
                    "BSS_vs_best_model": 1 - bs / bs_best if bs_best > 0 else np.nan, "p_star": p_star}
            for method, yes in (("prob>=p*", sl["p"] >= p_star), ("best_model", sl["best"]),
                                ("blend_mean", sl["mean"])):
                rows.append({**base, "method": method, **contingency(np.where(np.isfinite(sl["p"]), yes, np.nan),
                                                                      sl["ev"])})
    return pd.DataFrame(rows), keep


def reliability(p, ev, bins=BINS):
    ok = np.isfinite(p) & np.isfinite(ev)
    b = np.clip(np.digitize(p[ok], bins[1:-1]), 0, len(bins) - 2)
    cnt = np.bincount(b, minlength=len(bins) - 1)
    return (np.bincount(b, weights=p[ok], minlength=len(bins) - 1) / np.maximum(cnt, 1),
            np.bincount(b, weights=ev[ok], minlength=len(bins) - 1) / np.maximum(cnt, 1), cnt)
