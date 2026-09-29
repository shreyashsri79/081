"""One command: download (in parallel), train, verify, write the slide-4 headline and maps.

Kaggle (one cell, Internet ON):
    !git clone -q https://github.com/shreyashsri79/081 && cd 081 && pip install -q gcsfs "zarr>=2.18,<3" && python run_all.py

Laptop:
    git clone https://github.com/shreyashsri79/081 && cd 081 && pip install -r requirements.txt && python run_all.py

Re-running skips files already downloaded. Quick test: python run_all.py --max-inits 5 --out test_out
On Kaggle, attach a previous run's output (Add Input -> Your Work) and its cache/ files are reused.
"""

import argparse
import datetime
import glob
import shutil
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import xarray as xr

from blend import config as C
from blend import products as P
from blend import verify as V
from blend.cache import (chirps_path, fc_files, fc_path, load_forecasts, load_truth as load_truth_cache,
                         truth_path, variables_in)
from blend.chirps import load_rain_truth
from blend.harmonise import prepare
from blend.regimes import download_indices, label
from blend.sources import load_forecast, load_truth

VAR_NAMES = {"t2m": C.T2M, "wind": C.WIND, "mslp": C.MSLP, "rain": C.RAIN}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save(ds, path):
    ds.to_netcdf(path + ".tmp")
    os.replace(path + ".tmp", path)  # no half-written files if the session dies


def regimes_path(cache):
    return os.path.join(cache, "regime_indices.csv")


def seed_cache(cache):
    """Copy cache files from an attached Kaggle input (a previous run's output) so they are not re-downloaded."""
    os.makedirs(cache, exist_ok=True)
    for src in glob.glob("/kaggle/input/**/cache/*", recursive=True):
        dst = os.path.join(cache, os.path.basename(src))
        if os.path.isfile(src) and not src.endswith(".tmp") and not os.path.exists(dst):
            shutil.copy(src, dst)
            log(f"reused {os.path.basename(src)} from {os.path.dirname(src)}")


SHORT = {v: k for k, v in VAR_NAMES.items()}
NO_RAIN = {"pangu", "aurora"}


def download(models, years, variables, cache, jobs, max_inits, clim_years):
    """Fetch only what is missing: each (model, year) gets the variables it lacks, in a new file."""
    seed_cache(cache)
    era5_vars = [v for v in variables if v != C.RAIN]   # rain truth comes from CHIRPS
    tasks = []
    missing = [v for v in era5_vars if v not in variables_in(glob.glob(os.path.join(cache, "truth_era5*.nc")))]
    if missing:
        tasks.append(("truth", missing))
    if C.RAIN in variables and not os.path.exists(chirps_path(cache)):
        tasks.append(("chirps", None))
    if not os.path.exists(regimes_path(cache)):
        tasks.append(("regimes", None))
    for m in models:
        want = [v for v in variables if not (v == C.RAIN and m in NO_RAIN)]
        for y in years:
            need = [v for v in want if v not in variables_in(fc_files(cache, m, y))]
            if need:
                tasks.append((m, y, need))
    log(f"download: {len(tasks)} files to fetch, {jobs} in parallel")
    workers = max(4, 32 // jobs)

    def tag(vs):
        return "-".join(SHORT[v] for v in vs)

    def one(task):
        t0 = time.time()
        if task[0] == "truth":
            vs = task[1]
            tr = xr.concat([load_truth(vs, f"{y}-01-01", f"{y + 1}-01-11", workers=workers) for y in years], "time")
            _, first = np.unique(tr.time.values, return_index=True)
            save(tr.isel(time=np.sort(first)), truth_path(cache, tag(vs)))
            return f"ERA5 truth {vs}  days={tr.sizes['time']}  {time.time() - t0:.0f} s"
        if task[0] == "chirps":
            ref = xr.open_dataset(fc_files(cache, models[0], years[0])[0]) if fc_files(cache, models[0], years[0])                 else load_forecast(models[0], era5_vars or [C.T2M], [years[0]], max_inits=1)
            rain = load_rain_truth(years, cache, ref.latitude.values, ref.longitude.values)
            save(rain, chirps_path(cache))
            shutil.rmtree(os.path.join(cache, "chirps_raw"), ignore_errors=True)  # keep the output small
            return f"CHIRPS rain truth  days={rain.sizes['time']}  {time.time() - t0:.0f} s"
        if task[0] == "regimes":
            df = download_indices(f"{clim_years[0]}-01-01", "2023-01-10", workers=32)  # IO bound; biggest task
            df.to_csv(regimes_path(cache) + ".tmp")
            os.replace(regimes_path(cache) + ".tmp", regimes_path(cache))
            return f"regime indices  days={len(df)}  {time.time() - t0:.0f} s"
        m, y, need = task
        ds = load_forecast(m, need, [y], max_inits=max_inits, workers=workers)
        assert ds.sizes["lead"] == 10
        assert max_inits or ds.sizes["init"] >= 350, f"{m} {y}: only {ds.sizes['init']} inits"
        save(ds, fc_path(cache, m, y, tag(need) if fc_files(cache, m, y) else None))
        return f"{m:9s} {y}  {tag(need)}  inits={ds.sizes['init']}  {time.time() - t0:.0f} s"

    with ThreadPoolExecutor(jobs) as pool:
        futures = {pool.submit(one, t): t for t in tasks}
        for f in as_completed(futures):
            log("done " + f.result())


def regime_report(labels, years, art):
    """Regime calendar and day counts for the forecast years, so the labels can be checked by eye."""
    lab = labels[labels.index.year.isin(years)]
    lab.to_csv(f"{art}/regime_calendar.csv")
    counts = lab.groupby(["season", "regime"]).size().unstack(fill_value=0)
    counts.to_csv(f"{art}/regime_counts.csv")
    print("\nRegime days in forecast years (init-day label):\n" + counts.to_string())
    return counts


def train(set_name, models, years, variables, cache, art, clim_years):
    os.makedirs(f"{art}/figures", exist_ok=True)
    mode = "loyo" if len(years) > 1 else "months"
    forecasts, truth = load_forecasts(cache, models, years), load_truth_cache(cache)
    labels = label(pd.read_csv(regimes_path(cache), index_col=0, parse_dates=True), clim_years)
    regime_report(labels, years, art)
    cards, rcards, lines = [], [], []
    for var in variables:
        tag = var.replace("_", "")
        fc, obs = prepare(forecasts, truth, var, labels)
        log(f"train {var}: {dict(fc.sizes)}")
        se, cell, _ = V.run_folds(fc, obs, mode)
        card = V.scorecard(se, var, set_name)
        cards.append(card)
        rcards.append(V.regime_scorecard(se, var, set_name, lead_day=3))
        for ref in ["B0", "B0bc"]:
            lines.append(f"[vs {ref}] " + V.headline(card, var, lead_day=3, ref=ref))
        b3 = card[(card["var"] == var) & (card.lead_day == 3) & (card.rung.isin(["B2", "B3"]))].set_index("rung").rmse
        lines.append(f"[regime] {var} Day-3 RMSE: B2 (cell x lead) {b3['B2']:.3f} -> B3 (+ season + regime) "
                     f"{b3['B3']:.3f} ({100 * (b3['B3'] / b3['B2'] - 1):+.2f} %)")

        p = V.fit(fc, obs)  # final fit on all years -> operational weights and maps
        xr.Dataset({k: p[k] for k in ("w_B2", "w_B3s", "w_B3", "bias")}).to_netcdf(
            f"{art}/weights_{set_name}_{tag}.nc")
        wa, wb = p["w_B3"].sel(lead=3, regime_key="JJAS:active"), p["w_B3"].sel(lead=3, regime_key="JJAS:break")
        P.weight_diff_maps(wa - wb, f"{var} · weight in monsoon ACTIVE minus BREAK spells · Day 3",
                           f"{art}/figures/weights_active_minus_break_{tag}_d3.png")
        seasons = [str(s) for s in np.unique(fc.season.values)]
        seas = "JJAS" if "JJAS" in seasons else seasons[0]
        P.rmse_vs_lead(card, var, [f"m:{m}" for m in models] + ["B0bc", "B1", "B2", "B3"],
                       f"{art}/figures/rmse_vs_lead_{tag}.png")
        P.weight_maps(p["w_B2"].sel(lead=3), f"{var} · B2 weights · Day 3", f"{art}/figures/weights_B2_{tag}_d3.png")
        P.weight_maps(p["w_B3s"].sel(lead=3, season=seas), f"{var} · B3s weights · Day 3 · {seas}",
                      f"{art}/figures/weights_B3s_{tag}_d3_{seas}.png")
        P.dominant_map(p["w_B3"].sel(lead=3, regime_key=f"{seas}:normal"), f"{var} · dominant model · Day 3 · {seas}",
                       f"{art}/figures/dominant_{tag}_d3_{seas}.png")
        P.gain_map(cell, "B3", "B0bc", 3, f"{var} · held-out RMSE change · Day 3",
                   f"{art}/figures/gain_B3_vs_B0bc_{tag}_d3.png")

    card = pd.concat(cards, ignore_index=True)
    card.to_csv(f"{art}/scorecard_{set_name}.csv", index=False)
    rcard = pd.concat(rcards, ignore_index=True)
    rcard.to_csv(f"{art}/scorecard_by_regime_{set_name}.csv", index=False)
    print("\nDay-3 RMSE by init-day regime (B3 vs B2 = value of regime conditioning):")
    print(rcard.round(3).to_string(index=False))
    lines.append(f"Set {set_name}: {', '.join(models)}; {mode} over {years}; 1.5 deg India box; 00 UTC; truth ERA5.")
    open(f"{art}/headline.txt", "w", encoding="utf-8").write("\n".join(lines))
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        commit = "unknown"
    json.dump({"set": set_name, "models": models, "years": years, "variables": variables, "mode": mode,
               "code_commit": commit, "alpha": C.ALPHA, "k_shrink": C.K_SHRINK, "smooth": C.SMOOTH,
               "n_boot": C.N_BOOT, "block_days": C.BLOCK_DAYS, "seed": C.SEED, "truth": C.ERA5,
               "stores": {m: [u for u, _ in C.STORES[m]] for m in models},
               "clim_years": list(clim_years), "regime_boxes": C.REGIME_BOXES,
               "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
              open(f"{art}/manifest.json", "w"), indent=1)
    cols = ["var", "lead_day", "rung", "rmse", "pct_vs_B0", "verdict_vs_B0", "pct_vs_B0bc", "verdict_vs_B0bc"]
    print()
    print(card[card.lead_day.isin([1, 3, 5, 10])][cols].round(3).to_string(index=False))
    print("\n" + "=" * 100 + "\nSLIDE-4 HEADLINE\n" + "\n".join(lines) + "\n" + "=" * 100)
    log(f"outputs in {os.path.abspath(art)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="S1", choices=list(C.SETS))
    ap.add_argument("--vars", nargs="+", default=["t2m", "wind"], choices=list(VAR_NAMES))
    ap.add_argument("--out", default="/kaggle/working" if os.path.isdir("/kaggle/working") else "out")
    ap.add_argument("--jobs", type=int, default=4, help="files downloaded in parallel")
    ap.add_argument("--max-inits", type=int, default=None, help="small number for a quick test")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--clim-years", nargs=2, type=int, default=list(C.CLIM_YEARS),
                    help="regime climatology years; must not include a test year")
    a = ap.parse_args()

    s = C.SETS[a.set]
    variables = [VAR_NAMES[v] for v in a.vars]
    cache, art = os.path.join(a.out, "cache"), os.path.join(a.out, "artifacts", a.set)  # one folder per set
    np.random.seed(C.SEED)
    log(f"set {a.set}: models {s['models']}, years {s['years']}, vars {variables}")
    if not a.skip_download:
        download(s["models"], s["years"], variables, cache, a.jobs, a.max_inits, a.clim_years)
    assert not set(range(a.clim_years[0], a.clim_years[1] + 1)) & set(s["years"]), "climatology overlaps test years"
    train(a.set, s["models"], s["years"], variables, cache, art, a.clim_years)


if __name__ == "__main__":
    main()
