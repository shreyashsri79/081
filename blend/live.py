"""C10 Daily live run: today's ECMWF IFS + AIFS open-data forecasts, blended with weights learned in training.

    python -m blend.live build-model --art path/to/artifacts     # once, after a Kaggle training run
    python -m blend.live run --bundles bundles                   # every day, after ~09 UTC

build-model reads artifacts/S1 (t2m, wind, mslp) and artifacts/S2 (rain) and writes models/live_model.nc: for each
variable, the training error covariance between models, and each model's bias per season.

run downloads the latest 00 UTC IFS and AIFS forecasts (Day 1-10), averages them onto the same 1.5° cells as
training, and blends them. The live models are not the training models, so each borrows the learned skill of its
closest training counterpart (PROXY): IFS is the same system as HRES; AIFS, like GraphCast, is an ECMWF-analysis-
initialised AI model trained on ERA5. Weights are re-solved (minimum variance, B2c) on that pair's covariance.
Bias correction is applied to IFS only (HRES bias); AIFS has no bias history yet. Every bundle says so in its notes.
"""

import argparse
import datetime
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import bundle as B
from . import config as C
from .export import diff_scale, to_display
from .weights import min_variance

LIVE_MODELS = {"ifs": "ifs", "aifs": "aifs-single"}            # our id -> ecmwf-opendata model name
PROXY = {"ifs": "hres", "aifs": "graphcast"}
BIAS_FROM_PROXY = {"ifs"}                                       # AIFS: no bias correction until it has history
VAR_IDS = {"t2m": C.T2M, "wind": C.WIND, "mslp": C.MSLP, "rain": C.RAIN}
SET_OF = {"t2m": "S1", "wind": "S1", "mslp": "S1", "rain": "S2"}
UNITS_DISPLAY = {"t2m": "K", "wind": "m/s", "mslp": "Pa", "rain": "mm"}
LAT = np.arange(6.0, 39.01, 1.5)                                # training grid cells inside the India box
LON = np.arange(66.0, 99.01, 1.5)
MODEL_FILE = Path(__file__).resolve().parent.parent / "models" / "live_model.nc"
KEEP_LIVE = 7                                                   # live bundles kept in the repo


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------ build-model

def build_model(art: str, out: Path = MODEL_FILE) -> Path:
    parts = {}
    for vid, wb2 in VAR_IDS.items():
        f = Path(art) / SET_OF[vid] / f"weights_{SET_OF[vid]}_{wb2.replace('_', '')}.nc"
        if not f.exists():
            log(f"skip {vid}: {f} not found")
            continue
        ds = xr.load_dataset(f)
        if "cov_all" not in ds:
            raise SystemExit(f"{f} has no cov_all: re-run training with the current code (run_all.py)")
        parts[f"cov_{vid}"] = ds["cov_all"].rename(m1=f"m1_{vid}", m2=f"m2_{vid}")
        parts[f"bias_{vid}"] = ds["bias"].rename(model=f"model_{vid}")
    if not parts:
        raise SystemExit("no weights files found under " + art)
    out.parent.mkdir(parents=True, exist_ok=True)
    model = xr.Dataset(parts)
    model.attrs.update({"source": str(art), "created": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    model.to_netcdf(out)
    log(f"wrote {out} with {sorted(v.split('_')[1] for v in parts if v.startswith('cov'))}")
    return out


# ------------------------------------------------------------------ download + regrid

def _conservative_matrix(src: np.ndarray, centres: np.ndarray) -> np.ndarray:
    """Weights that average 0.25° point values over 1.5° cells (edges at centre ± 0.75°, half weight at edges)."""
    W = np.zeros((len(centres), len(src)))
    for i, c in enumerate(centres):
        d = np.abs(src - c)
        w = np.where(d < 0.75 - 1e-6, 1.0, np.where(np.abs(d - 0.75) < 1e-6, 0.5, 0.0))
        W[i] = w / w.sum()
    return W


def to_training_grid(da: xr.DataArray) -> xr.DataArray:
    """(…, latitude, longitude) at 0.25° -> the 1.5° training cells."""
    da = da.sortby("latitude").sel(latitude=slice(LAT[0] - 0.8, LAT[-1] + 0.8),
                                   longitude=slice(LON[0] - 0.8, LON[-1] + 0.8))
    Wy = _conservative_matrix(da.latitude.values, LAT)
    Wx = _conservative_matrix(da.longitude.values, LON)
    out = np.einsum("ia,...ab,jb->...ij", Wy, da.values, Wx)
    dims = da.dims[:-2] + ("latitude", "longitude")
    coords = {d: da[d] for d in da.dims[:-2]} | {"latitude": LAT, "longitude": LON}
    return xr.DataArray(out, dims=dims, coords=coords)


def latest_init(model: str) -> datetime.datetime:
    from ecmwf.opendata import Client
    return Client(source="ecmwf", model=LIVE_MODELS[model]).latest(time=0, step=240, param="2t")


def fetch(model: str, init: datetime.datetime, workdir: Path) -> Path:
    from ecmwf.opendata import Client
    path = workdir / f"{model}_{init:%Y%m%d}.grib2"
    if not path.exists():
        Client(source="ecmwf", model=LIVE_MODELS[model]).retrieve(
            date=init, time=0, step=[24 * d for d in range(0, 11)], param=["2t", "10u", "10v", "msl", "tp"],
            target=str(path) + ".tmp")
        os.replace(str(path) + ".tmp", path)
    return path


def read(path: Path) -> xr.Dataset:
    """GRIB -> WB2 names on the training grid, dims (lead, latitude, longitude). Rain in metres, like WB2."""
    def one(short):
        ds = xr.open_dataset(path, engine="cfgrib",
                             backend_kwargs={"filter_by_keys": {"shortName": short}, "indexpath": ""})
        da = ds[list(ds.data_vars)[0]]
        hours = (da.step.values / np.timedelta64(1, "h")).astype(int)
        return da.assign_coords(step=hours).rename(step="hours")

    leads = [24 * d for d in C.LEAD_DAYS]
    t2m, u, v, msl, tp = (one(s) for s in ("2t", "10u", "10v", "msl", "tp"))
    tp_m = tp / 1000.0 if tp.attrs.get("units", "m") != "m" else tp        # AIFS: kg m-2 (= mm)
    rain = tp_m.sel(hours=leads).values - tp_m.sel(hours=[h - 24 for h in leads]).values  # 24 h ending at the lead
    rain = xr.DataArray(np.maximum(rain, 0), dims=("hours", "latitude", "longitude"),
                        coords={"hours": leads, "latitude": tp.latitude, "longitude": tp.longitude})
    fields = {C.T2M: t2m.sel(hours=leads), C.MSLP: msl.sel(hours=leads), C.RAIN: rain,
              C.WIND: np.hypot(u.sel(hours=leads), v.sel(hours=leads)),
              "u10": u.sel(hours=leads), "v10": v.sel(hours=leads)}
    out = xr.Dataset({k: to_training_grid(f.drop_vars([c for c in f.coords if c not in f.dims])) for k, f in fields.items()})
    return out.rename(hours="lead").assign_coords(lead=C.LEAD_DAYS)


# ------------------------------------------------------------------ blend + bundle

def blend_var(vid, fcs: dict, model: xr.Dataset, season: str):
    """fcs: {live model: DataArray (lead, lat, lon) in display units}. Returns arrays for the bundle."""
    live = list(fcs)
    proxies = [PROXY[m] for m in live]
    cov = model[f"cov_{vid}"].rename({f"m1_{vid}": "m1", f"m2_{vid}": "m2"}).sel(m1=proxies, m2=proxies)
    cov = cov.assign_coords(m1=live, m2=live)
    w = min_variance(cov).transpose("model", "lead", "latitude", "longitude")
    # rain truth (CHIRPS) is land only, so sea cells have no learned skill: equal weights there
    w = w.fillna(1.0 / len(live))
    bias = model[f"bias_{vid}"].rename({f"model_{vid}": "model"}).sel(season=season, model=proxies)
    bias = bias.assign_coords(model=live).transpose("model", "lead", "latitude", "longitude")
    bias = bias.where(xr.DataArray([m in BIAS_FROM_PROXY for m in live], dims="model", coords={"model": live}), 0.0)
    fc = xr.concat([fcs[m] for m in live], pd.Index(live, name="model")).transpose("model", "lead", "latitude", "longitude")
    fc_bc = fc - bias.values
    if vid == "rain":
        fc_bc = fc_bc.clip(min=0)
    blended = (fc_bc * w.values).sum("model")
    mse = np.stack([cov.sel(m1=m, m2=m).values for m in live])
    n = len(LAT) * len(LON)
    flat = lambda a: np.asarray(a).reshape(np.asarray(a).shape[:-2] + (n,))
    k = diff_scale(vid)   # same display units as the hindcast bundles (°C, hPa)
    return {f"fc_{vid}": flat(to_display(vid, fc.values)), f"blend_{vid}": flat(to_display(vid, blended.values)),
            f"w_{vid}": flat(w.values), f"mse_{vid}": flat(mse * k * k), f"bias_{vid}": flat(bias.values * k)}, w


def run(bundles: str, init: datetime.datetime | None = None, workdir: str = "live_work", model_file: Path = MODEL_FILE):
    t_start = time.time()
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    model = xr.load_dataset(model_file)
    steps, notes, data = [], [], {}
    init = init or min(latest_init(m) for m in LIVE_MODELS)   # the newest init every model has finished
    log(f"init {init:%Y-%m-%d} 00 UTC")
    for m in LIVE_MODELS:
        t0 = time.time()
        try:
            data[m] = read(fetch(m, init, work))
            steps.append({"name": f"fetch {m} 00 UTC Day 1-10", "status": "ok", "seconds": round(time.time() - t0, 2)})
        except Exception as e:  # one model down should not stop the run
            steps.append({"name": f"fetch {m}", "status": "failed", "seconds": round(time.time() - t0, 2),
                          "note": repr(e)[:200]})
            log(f"{m} failed: {e!r}")
    if not data:
        raise SystemExit("no live model could be fetched")

    season = C.SEASON_OF_MONTH[init.month]
    arrays, models_by_var, vars_done = {}, {}, []
    t0 = time.time()
    for vid, wb2 in VAR_IDS.items():
        if f"cov_{vid}" not in model:
            continue
        fcs = {}
        for m, ds in data.items():
            f = ds[wb2] * (1000.0 if vid == "rain" else 1.0)          # display units, as in the hindcast bundles
            fcs[m] = f
        a, w = blend_var(vid, fcs, model, season)
        arrays.update(a)
        models_by_var[vid] = list(fcs)
        vars_done.append(vid)
        if vid == "wind":   # blended wind components for the particle layer
            uv = {c: sum(data[m][c] * w.sel(model=m).values for m in fcs) for c in ("u10", "v10")}
            arrays["u10"] = uv["u10"].values.reshape(len(C.LEAD_DAYS), -1)
            arrays["v10"] = uv["v10"].values.reshape(len(C.LEAD_DAYS), -1)
    steps.append({"name": "blend with stored weights (B2c on proxy covariance)", "status": "ok",
                  "seconds": round(time.time() - t0, 2)})

    notes += [
        "Live run: today's ECMWF IFS and AIFS open-data forecasts, 00 UTC, averaged onto the 1.5° training grid.",
        "Weights borrow learned skill from training counterparts: IFS <- HRES, AIFS <- GraphCast (both 2018-2022). "
        "They are re-solved as minimum-variance weights for this pair.",
        "Bias correction: IFS uses the HRES seasonal bias; AIFS is not bias-corrected (no history yet).",
        "No truth yet for these valid dates, so this run has no scores. Skill figures come from the hindcast scorecards.",
        "Rain weights over the sea are equal (rain truth is land only, so there is no learned skill there).",
        "Extreme probabilities are not produced live yet (they need each live model's own climatology).",
        "Regime: season only; the live regime label needs observed rain for the last 3 days.",
    ]
    failed = [s for s in steps if s["status"] == "failed"]
    run_id = f"live-{init:%Y%m%d}"
    meta = {
        "id": run_id, "kind": "live", "init": f"{init:%Y-%m-%d}T00:00Z",
        "status": "partial" if failed else "ok", "models": list(data),
        "grid": {"lat0": float(LAT[0]), "lon0": float(LON[0]), "step": 1.5, "ny": len(LAT), "nx": len(LON)},
        "leads": [int(x) for x in C.LEAD_DAYS], "vars": vars_done, "modelsByVar": models_by_var,
        "regime": {"season": season, "label": f"{season} (season only)", "basis": "init"},
        "rung": "B2c", "steps": steps, "provenance": "measured", "notes": notes,
        "extremes": [],
        "_x": {"sets": {v: SET_OF[v] for v in vars_done}, "proxy": PROXY, "k": float(C.K_SHRINK),
               "nSeason": {}, "nRegime": {}, "extremeCalibrated": False, "extremeMethod": None,
               "modelFile": model.attrs.get("source", ""), "created": datetime.datetime.now(
                   datetime.timezone.utc).isoformat(timespec="seconds")},
    }
    B.write_run(Path(bundles), meta, arrays)
    meta["steps"].append({"name": "write bundle", "status": "ok", "seconds": round(time.time() - t_start, 2)})
    B.write_meta(Path(bundles), meta)
    prune(Path(bundles))
    B.write_index(Path(bundles))
    log(f"wrote {bundles}/runs/{run_id} ({', '.join(vars_done)}; models {', '.join(data)})")
    return run_id


def prune(root: Path, keep: int = KEEP_LIVE):
    import shutil
    live = sorted(r for r in B.list_runs(root) if r.startswith("live-"))
    for r in live[:-keep]:
        shutil.rmtree(root / "runs" / r)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-model")
    b.add_argument("--art", required=True, help="artifacts dir holding S1/ and S2/ from run_all.py")
    r = sub.add_parser("run")
    r.add_argument("--bundles", default="bundles")
    r.add_argument("--date", help="init date YYYY-MM-DD (default: latest complete 00 UTC run)")
    r.add_argument("--work", default="live_work")
    a = ap.parse_args(argv)
    if a.cmd == "build-model":
        build_model(a.art)
    else:
        init = datetime.datetime.strptime(a.date, "%Y-%m-%d") if a.date else None
        run(a.bundles, init, a.work)


if __name__ == "__main__":
    main()
