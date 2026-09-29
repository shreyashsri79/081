"""Hindcast run bundles (BACKEND_BUILD_PLAN.md T4-T6): real forecasts, out-of-sample weights, errors and
interim extreme probabilities for one init date, written in display units for blend/server.py.

    python -m blend.export --cache out/cache --art out/artifacts --out bundles --auto
    python -m blend.export --cache out/cache --art out/artifacts --out bundles --dates 2020-07-15 2022-04-28

Uses only the existing blend/ science functions; nothing here changes how weights or scores are computed.
"""

import argparse
import datetime
import os
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import bundle as B
from . import config as C
from . import verify as V
from .cache import fc_path, load_forecasts, load_truth
from .harmonise import prepare
from .regimes import all_keys, label
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


# ------------------------------------------------------------- run bundles (plan T6)

EXTREMES = {"rain64": ("rain", 64.5), "rain115": ("rain", 115.6), "rain204": ("rain", 204.5), "wind15": ("wind", 15.0)}
EXTREME_METHOD = "weighted vote of bias-corrected members (uncalibrated)"
UI_ORDER = ["rain", "t2m", "wind", "mslp"]
MODEL_ORDER = ["hres", "graphcast", "pangu", "fuxi", "gencast", "ifs", "aifs", "gfs"]
REGIME_TEXT = {"normal": "Normal", "active": "Monsoon active", "break": "Monsoon break", "depression": "Depression",
               "western_disturbance": "Western disturbance", "heat": "Heat"}
HEAT_NOTE = ("Heat-wave guidance unavailable: forecasts are 00 UTC (05:30 IST); the heat rule needs an afternoon "
             "(12 UTC) value.")
UV_NOTE = "Wind particles unavailable: u/v components are not in the cache."


class Context:
    """Loads each model set and the truth once per export, shared by every run and scorecard."""

    def __init__(self, cache: str, art: str | None):
        self.cache, self.art = cache, art
        self._fc, self._prep = {}, {}
        self.truth = load_truth(cache)
        self.labels = label(pd.read_csv(os.path.join(cache, "regime_indices.csv"), index_col=0, parse_dates=True),
                            C.CLIM_YEARS)

    def prepared(self, set_name: str, ui: str):
        """(fc, obs) for one set and variable, or None if no model of the set has the variable."""
        key = (set_name, ui)
        if key not in self._prep:
            if set_name not in self._fc:
                s = C.SETS[set_name]
                self._fc[set_name] = load_forecasts(self.cache, s["models"], s["years"])
            fcs = {m: ds for m, ds in self._fc[set_name].items() if VAR_IDS[ui] in ds}
            self._prep[key] = prepare(fcs, self.truth, VAR_IDS[ui], self.labels) if fcs else None
        return self._prep[key]

    def card(self, set_name: str) -> pd.DataFrame | None:
        p = os.path.join(self.art, f"scorecard_{set_name}.csv") if self.art else None
        return pd.read_csv(p) if p and os.path.exists(p) else None

    def rung(self, set_name: str, ui: str) -> tuple[str, str]:
        card = self.card(set_name)
        if card is None or VAR_IDS[ui] not in set(card["var"]):
            return "B2", f"scorecard_{set_name}.csv missing for {ui}: shipped B2 (cell x lead) by default"
        return choose_rung(card, VAR_IDS[ui])


def _grid(fc: xr.DataArray) -> dict:
    lat, lon = fc.latitude.values, fc.longitude.values
    assert np.all(np.diff(lat) > 0), "latitude must ascend (row 0 = south)"
    step = float(np.round(lat[1] - lat[0], 6))
    for axis in (lat, lon):
        assert np.allclose(np.diff(axis), step), "grid spacing must be uniform"
    return {"lat0": float(lat[0]), "lon0": float(lon[0]), "step": step, "ny": int(len(lat)), "nx": int(len(lon))}


def _flat(da: xr.DataArray, dims) -> np.ndarray:
    a = da.transpose(*dims).values
    return a.reshape(*a.shape[:-2], -1).astype(np.float32)


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def build_run(ctx: Context, date, out_root: Path) -> Path:
    """One hindcast bundle for init `date`: out-of-sample weights, blend, members, errors, interim extremes."""
    date = pd.Timestamp(date).normalize()
    run_id = f"hindcast-{date:%Y%m%d}"
    steps, notes, arrays = [], [], {}
    models_by_var, rungs, reasons, folds, sets_used, n_season, n_regime = {}, {}, {}, {}, {}, {}, {}
    grid = season = key = None
    sets = sets_for(date.year, ctx.cache)

    for ui in UI_ORDER:
        t0 = time.perf_counter()
        set_name = sets[ui]
        prep = ctx.prepared(set_name, ui)
        if prep is None:
            notes.append(f"{ui}: no model of {set_name} has this variable in the cache.")
            steps.append({"name": f"{ui}: load {set_name}", "status": "skipped", "seconds": 0.0, "note": "not cached"})
            continue
        fc, obs = prep
        if not (fc.init.values.astype("datetime64[ns]") == np.datetime64(date, "ns")).any():
            notes.append(f"{ui}: {date.date()} is not a common init of {', '.join(map(str, fc.model.values))}.")
            steps.append({"name": f"{ui}: load {set_name}", "status": "skipped", "seconds": 0.0, "note": "date missing"})
            continue
        mode = mode_of(set_name)
        p = fit_for_date(fc, obs, date, mode)
        rung, why = ctx.rung(set_name, ui)
        steps.append({"name": f"fit {ui} on {set_name}, fold {p['fold']} held out", "status": "ok",
                      "seconds": round(time.perf_counter() - t0, 2)})

        t0 = time.perf_counter()
        fcd = fc.sel(init=date)
        season, key = str(fcd.season.values), str(fcd.regime_key.values)
        # weights and the MSE table behind them, at this date's season / regime key
        if rung == "B3":
            w, mse = p["w_B3"].sel(regime_key=key), p["mse_B3"].sel(regime_key=key)
        elif rung == "B3s":
            w, mse = p["w_B3s"].sel(season=season), p["mse_B3s"].sel(season=season)
        elif rung == "B2":
            w, mse = p["w_B2"], p["mse_B2"]
        else:  # B1: equal mean of the bias-corrected members
            w, mse = xr.ones_like(p["w_B2"]) / fc.sizes["model"], p["mse_B2"]
        bias = p["bias"].sel(season=season)
        fc_bc = fcd - bias
        blended = (fc_bc * w).sum("model", skipna=False)
        dims4, dims3 = ("model", "lead", "latitude", "longitude"), ("lead", "latitude", "longitude")
        f = diff_scale(ui)
        arrays[f"fc_{ui}"] = _flat(to_display(ui, fcd), dims4)
        arrays[f"blend_{ui}"] = _flat(to_display(ui, blended), dims3)
        arrays[f"w_{ui}"] = _flat(w.transpose(*dims4), dims4)
        arrays[f"mse_{ui}"] = _flat(mse * f * f, dims4)
        arrays[f"bias_{ui}"] = _flat(bias * f, dims4)
        arrays[f"obs_{ui}"] = _flat(to_display(ui, obs.sel(init=date)), dims3)
        # interim extremes: weighted vote of bias-corrected members, NaN where any member is missing
        members = to_display(ui, fc_bc)
        for ex, (var, thr) in EXTREMES.items():
            if var == ui:
                vote = (members >= thr).astype(float).where(members.notnull())
                arrays[f"p_{ex}"] = _flat((vote * w).sum("model", skipna=False).clip(0, 1), dims3)

        g = _grid(fc)
        assert grid is None or g == grid, "all variables must share one grid"
        grid = g
        models_by_var[ui] = [str(m) for m in fc.model.values]
        rungs[ui], reasons[ui], sets_used[ui] = rung, why, set_name
        folds[ui] = f"year {p['fold']}" if mode == "loyo" else f"month {p['fold'][1:]} ±{int(C.LEAD_DAYS.max())} days"
        n_season[ui] = p["n_season"].get(season, 0)
        n_regime[ui] = p.get("n_regime", {}).get(key, 0)
        steps.append({"name": f"blend {ui} ({rung}) + extremes", "status": "ok",
                      "seconds": round(time.perf_counter() - t0, 2)})

    if not models_by_var:
        raise ValueError(f"{date.date()}: no variable could be built")
    vars_ = [v for v in UI_ORDER if v in models_by_var]
    regime = str(ctx.labels["regime"].get(date, "normal")) if date in ctx.labels.index else "normal"
    season = C.SEASON_OF_MONTH[date.month]
    label_text = "Monsoon normal" if (regime == "normal" and season == "JJAS") else REGIME_TEXT[regime]
    notes = [
        "Rain truth: ERA5 reanalysis. CHIRPS verification is planned; ERA5 favours ERA5-like models.",
        "Weights for this date are fitted without its " + "; ".join(sorted({f for f in folds.values()})) +
        " (out-of-sample).",
        "Rung per variable: " + ", ".join(f"{v} {rungs[v]}" for v in vars_) + ".",
        f"Grid {grid['step']}° (~{round(grid['step'] * 111)} km); values are cell averages.",
        HEAT_NOTE,
        UV_NOTE,
    ] + notes
    meta = {
        "id": run_id, "kind": "hindcast", "init": f"{date:%Y-%m-%d}T00:00Z",
        "status": "ok" if len(vars_) == len(UI_ORDER) else "partial",
        "models": [m for m in MODEL_ORDER if any(m in ms for ms in models_by_var.values())],
        "grid": grid, "leads": [int(x) for x in C.LEAD_DAYS], "vars": vars_, "modelsByVar": models_by_var,
        "regime": {"season": season, "label": label_text, "basis": "init"},
        "rung": rungs.get("t2m", rungs[vars_[0]]),
        "steps": steps, "provenance": "measured", "notes": notes,
        "_x": {"sets": sets_used, "folds": folds, "rungs": rungs, "rungReason": reasons, "regimeKey": key,
               "nSeason": n_season, "nRegime": n_regime, "k": C.K_SHRINK,
               "thresholds": {k: v[1] for k, v in EXTREMES.items()}, "extremeMethod": EXTREME_METHOD,
               "unavailable": {"heat": HEAT_NOTE, **{ex: f"{var} not built for this run."
                                                     for ex, (var, _) in EXTREMES.items() if var not in vars_}},
               "codeCommit": _commit(),
               "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
    }
    t0 = time.perf_counter()
    path = B.write_run(out_root, meta, arrays)
    meta["steps"].append({"name": "write bundle", "status": "ok", "seconds": round(time.perf_counter() - t0, 2)})
    B.write_meta(out_root, meta)
    return path


def build_scorecards(ctx: Context, set_names, out_root: Path) -> None:
    """scorecards/<SET>.json for every set a run uses, with the regional breakdown at Day 3."""
    for set_name in sorted(set(set_names)):
        card = ctx.card(set_name)
        if card is None:
            continue
        rungs, regions = {}, []
        for ui in UI_ORDER:
            if VAR_IDS[ui] not in set(card["var"]) or VAR_IDS[ui] not in C.SETS[set_name]["vars"]:
                continue
            rungs[ui] = ctx.rung(set_name, ui)[0]
            prep = ctx.prepared(set_name, ui)
            if prep is not None:
                regions += region_scores(*prep, mode_of(set_name), rungs[ui], ui)
        B.write_scorecard(out_root, set_name, scorecard_json(set_name, card, rungs, regions))


def auto_dates(ctx: Context, cap: int = 12) -> list[pd.Timestamp]:
    """First init of each regime (≥ 3 days that year) per forecast year in the cache, plus 2020-07-15."""
    have = {}
    for y in C.SETS["S1"]["years"]:
        files = [fc_path(ctx.cache, m, y) for m in C.SETS["S1"]["models"]]
        if all(os.path.exists(f) for f in files):
            inits = None
            for f in files:
                with xr.open_dataset(f) as ds:
                    t = set(pd.DatetimeIndex(ds.init.values).normalize())
                inits = t if inits is None else inits & t
            have[y] = inits
    picks = []
    if pd.Timestamp("2020-07-15") in have.get(2020, set()):
        picks.append(pd.Timestamp("2020-07-15"))
    lab = ctx.labels
    for y, inits in sorted(have.items()):
        ly = lab[lab.index.year == y]
        for reg, n in ly.regime.value_counts().items():
            if n < 3:
                continue
            days = sorted(d for d in ly.index[ly.regime == reg] if d in inits)
            if days and days[0] not in picks:
                picks.append(days[0])
    return picks[:cap]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write hindcast run bundles for blend/server.py")
    ap.add_argument("--cache", required=True, help="run_all.py cache/ directory")
    ap.add_argument("--art", default=None, help="run_all.py artifacts/ directory (scorecards)")
    ap.add_argument("--out", default="bundles")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dates", nargs="+", help="init dates, YYYY-MM-DD")
    g.add_argument("--auto", action="store_true", help="one date per regime and year, plus 2020-07-15")
    a = ap.parse_args(argv)

    ctx = Context(a.cache, a.art)
    out = Path(a.out)
    dates = auto_dates(ctx) if a.auto else [pd.Timestamp(d) for d in a.dates]
    used = set()
    for d in dates:
        try:
            path = build_run(ctx, d, out)
            used |= set(B.read_meta(out, path.name)["_x"]["sets"].values())
            print(f"wrote {path}")
        except (KeyError, ValueError) as e:
            print(f"skip {pd.Timestamp(d).date()}: {e}")
    build_scorecards(ctx, used, out)
    idx = B.write_index(out)
    print(f"{len(idx['runs'])} runs in {out / 'index.json'}")


if __name__ == "__main__":
    main()
