"""Hindcast run bundles (BACKEND_BUILD_PLAN.md T4-T6): real forecasts, out-of-sample weights, errors and
interim extreme probabilities for one init date, written in display units for blend/server.py.

    python -m blend.export --cache out/cache --art out/artifacts --out bundles --auto
    python -m blend.export --cache out/cache --art out/artifacts --out bundles --dates 2020-07-15 2022-04-28

Uses only the existing blend/ science functions; nothing here changes how weights or scores are computed.
"""

import os

import numpy as np
import pandas as pd
import xarray as xr

from . import config as C
from . import verify as V
from .cache import fc_path, load_forecasts, load_truth
from .harmonise import prepare
from .regimes import all_keys
from .skill import apply_bias, fit_mse

# UI variable id -> WB2 name
VAR_IDS = {"rain": C.RAIN, "t2m": C.T2M, "wind": C.WIND, "mslp": C.MSLP}
UI_OF = {v: k for k, v in VAR_IDS.items()}

# set per UI variable (plan §5.2)
SETS_2020 = {"t2m": "S3", "wind": "S3", "mslp": "S3", "rain": "S4"}
SETS_LOYO = {"t2m": "S1", "wind": "S1", "mslp": "S1", "rain": "S2"}


def mode_of(set_name: str) -> str:
    """Validation mode exactly as run_all.train() picks it."""
    return "loyo" if len(C.SETS[set_name]["years"]) > 1 else "months"


def sets_for(year: int, cache: str) -> dict[str, str]:
    """{ui var: set}. 2020 uses the five-model sets S3/S4 when every one of their cache files exists,
    otherwise (and for 2018 / 2022) the three-year sets S1/S2."""
    if year not in C.SETS["S1"]["years"]:
        raise ValueError(f"{year}: no model set covers this year (S1/S2 years: {C.SETS['S1']['years']})")
    if year == 2020:
        need = {m for s in ("S3", "S4") for m in C.SETS[s]["models"]}
        if all(os.path.exists(fc_path(cache, m, 2020)) for m in need):
            return dict(SETS_2020)
    return dict(SETS_LOYO)


def fold_for(init: xr.DataArray, date, mode: str) -> tuple[str, np.ndarray, np.ndarray]:
    """The verify.make_folds fold whose test inits contain `date`."""
    d = np.datetime64(pd.Timestamp(date).normalize(), "ns")
    pos = np.flatnonzero(init.values.astype("datetime64[ns]") == d)
    if not len(pos):
        raise KeyError(f"{pd.Timestamp(date).date()} is not an init in this data")
    for name, train, test in V.make_folds(init, mode):
        if test[pos[0]]:
            return name, np.asarray(train), np.asarray(test)
    raise KeyError(f"no fold holds {pd.Timestamp(date).date()} out")


def fit_for_date(fc: xr.DataArray, obs: xr.DataArray, date, mode: str) -> dict:
    """verify.fit on the training inits of the fold that holds `date` out, plus the MSE tables behind the
    weights and the training case counts (for the cell inspector).

    The MSE tables repeat the fit_mse calls verify.fit makes internally, because fit returns weights only."""
    name, train, _ = fold_for(fc.init, date, mode)
    tr = np.flatnonzero(train)
    if not len(tr):
        raise ValueError(f"fold {name}: no training inits")
    fc_tr, obs_tr = fc.isel(init=tr), obs.isel(init=tr)
    p = V.fit(fc_tr, obs_tr)
    fc_bc = apply_bias(fc_tr, p["bias"])
    p["mse_B2"] = fit_mse(fc_bc, obs_tr, "all")
    p["mse_B3s"] = fit_mse(fc_bc, obs_tr, "season")
    if "regime_key" in fc.coords:
        p["mse_B3"] = fit_mse(fc_bc, obs_tr, "regime", keys=all_keys())
        p["n_regime"] = {str(k): int(v) for k, v in pd.Series(fc_tr.regime_key.values).value_counts().items()}
    p["n_season"] = {str(k): int(v) for k, v in pd.Series(fc_tr.season.values).value_counts().items()}
    p["fold"] = name
    p["n_train"] = int(len(tr))
    return p


# ------------------------------------------------------------------ units (plan §3.3)

def to_display(var_ui: str, x):
    """Values: K -> °C, Pa -> hPa. Rain is already mm after harmonise.prepare."""
    if var_ui == "t2m":
        return x - 273.15
    if var_ui == "mslp":
        return x / 100.0
    return x


def diff_scale(var_ui: str) -> float:
    """Factor for differences, biases and RMSE (MSE uses its square)."""
    return 0.01 if var_ui == "mslp" else 1.0


# ------------------------------------------------------------ scorecards (plan T5)

RUNG_ORDER = ["B3", "B3s", "B2", "B1"]


def choose_rung(card: pd.DataFrame, var_name: str) -> tuple[str, str]:
    """The blend rung to ship for one variable (plan §5.3), from that set's scorecard CSV rows.

    Eligible: not 'worse' than B0bc on at least 6 of the 10 leads. Ship the first eligible candidate whose mean
    RMSE over leads is no higher than the next available candidate's; otherwise B1."""
    c = card[card["var"] == var_name]
    have = [r for r in RUNG_ORDER if r in set(c.rung)]
    mean = {r: float(c[c.rung == r].rmse.mean()) for r in have}
    for i, r in enumerate(have):
        rows = c[c.rung == r]
        ok = int((rows["verdict_vs_B0bc"] != "worse").sum())
        if ok < 6:
            continue
        nxt = have[i + 1] if i + 1 < len(have) else None
        if nxt is None or mean[r] <= mean[nxt]:
            vs = f"; mean RMSE {mean[r]:.4g} vs {nxt} {mean[nxt]:.4g}" if nxt else ""
            return r, f"{r}: not worse than B0bc on {ok}/{len(rows)} leads{vs}"
    return "B1", "no higher rung qualified; equal mean of bias-corrected models"


def validation_text(set_name: str) -> str:
    years = C.SETS[set_name]["years"]
    if mode_of(set_name) == "loyo":
        return f"Leave-one-year-out {' / '.join(map(str, years))} ({set_name})"
    return f"Blocked months within {years[0]} ({set_name})"


def scorecard_json(set_name: str, card: pd.DataFrame, rungs: dict[str, str], regions: list[dict]) -> dict:
    """Scorecard-shaped dict (contract ScoreRow / regions) from artifacts/scorecard_<SET>.csv rows."""
    rows = []
    for var_name in dict.fromkeys(card["var"]):
        ui = UI_OF.get(var_name)
        if ui is None or ui not in rungs:
            continue
        f = diff_scale(ui)
        c = card[card["var"] == var_name]
        for lead in sorted(set(c.lead_day)):
            at = c[c.lead_day == lead].set_index("rung")
            models = [r[2:] for r in at.index if r.startswith("m:")]
            if not models or rungs[ui] not in at.index or "B1" not in at.index:
                continue
            rmse = {m: float(at.loc[f"m:{m}", "rmse"]) * f for m in models}
            ship = at.loc[rungs[ui]]
            rows.append({
                "var": ui, "lead": int(lead),
                "rmse": {**rmse, "b1": float(at.loc["B1", "rmse"]) * f, "blend": float(ship.rmse) * f},
                "best": min(rmse, key=rmse.get),
                "delta": float(ship["d_vs_B0"]) * f,
                "ci": [float(ship["lo_vs_B0"]) * f, float(ship["hi_vs_B0"]) * f],
            })
    regs = [{**r, "delta": r["delta"] * diff_scale(r["var"]), "ci": [x * diff_scale(r["var"]) for x in r["ci"]]}
            for r in regions]
    return {"validation": validation_text(set_name), "rows": rows, "regions": regs}


def region_scores(fc: xr.DataArray, obs: xr.DataArray, mode: str, rung: str, var_ui: str, lead: int = 3) -> list[dict]:
    """Held-out RMSE difference (shipped rung − B0) per region at one lead, with the paired block-bootstrap CI.

    Same folds, fit and predict as verify.run_folds; errors are averaged inside each region mask (cos-latitude
    weighted), then compared day by day. A region with fewer than MIN_CELLS cells is left out, never padded."""
    from .geo import india_mask
    from .regions import MIN_CELLS, REGIONS, region_mask

    lat, lon = fc.latitude.values, fc.longitude.values
    india = india_mask(lat, lon)
    masks = {n: region_mask(lat, lon, n, india) for n in REGIONS}
    masks = {n: xr.DataArray(m, dims=("latitude", "longitude"), coords={"latitude": lat, "longitude": lon})
             for n, m in masks.items() if m.sum() >= MIN_CELLS}
    if not masks:
        return []
    per = {n: {"rung": [], "B0": []} for n in masks}
    wts = np.cos(np.deg2rad(obs.latitude))
    for _, train, test in V.make_folds(fc.init, mode):
        tr, te = np.flatnonzero(train), np.flatnonzero(test)
        if not len(tr) or not len(te):
            continue
        p = V.fit(fc.isel(init=tr), obs.isel(init=tr))
        preds = V.predict(fc.isel(init=te), p)
        o = obs.isel(init=te).sel(lead=lead)
        for n, m in masks.items():
            for key, r in (("rung", rung), ("B0", "B0")):
                se = ((preds[r].sel(lead=lead) - o) ** 2).where(m).weighted(wts).mean(["latitude", "longitude"])
                per[n][key].append(se.to_series())
    out = []
    for n, d in per.items():
        a = pd.concat(d["rung"]).sort_index().values
        b = pd.concat(d["B0"]).sort_index().values
        if np.isfinite(a).sum() < C.BLOCK_DAYS + 1:
            continue
        delta, lo, hi = V.block_bootstrap(a, b)
        out.append({"var": var_ui, "name": n, "delta": delta, "ci": [lo, hi]})
    return out
