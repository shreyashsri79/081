"""One command: download (in parallel), train, verify, write the slide-4 headline and maps.

Kaggle (one cell, Internet ON):
    !git clone -q https://github.com/shreyashsri79/081 && cd 081 && pip install -q gcsfs "zarr>=2.18,<3" && python run_all.py

Laptop:
    git clone https://github.com/shreyashsri79/081 && cd 081 && pip install -r requirements.txt && python run_all.py

Re-running skips files already downloaded. Quick test: python run_all.py --max-inits 5 --out test_out
"""

import argparse
import datetime
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
from blend.cache import fc_path, load_forecasts, load_truth as load_truth_cache, truth_path
from blend.harmonise import prepare
from blend.sources import load_forecast, load_truth

VAR_NAMES = {"t2m": C.T2M, "wind": C.WIND, "mslp": C.MSLP, "rain": C.RAIN}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save(ds, path):
    ds.to_netcdf(path + ".tmp")
    os.replace(path + ".tmp", path)  # no half-written files if the session dies


def download(models, years, variables, cache, jobs, max_inits):
    os.makedirs(cache, exist_ok=True)
    tasks = [("truth", None)] + [(m, y) for m in models for y in years]
    tasks = [t for t in tasks if not os.path.exists(truth_path(cache) if t[0] == "truth" else fc_path(cache, *t))]
    log(f"download: {len(tasks)} files to fetch, {jobs} in parallel")
    workers = max(4, 32 // jobs)

    def one(task):
        t0 = time.time()
        if task[0] == "truth":
            tr = xr.concat([load_truth(variables, f"{y}-01-01", f"{y + 1}-01-11", workers=workers) for y in years], "time")
            _, first = np.unique(tr.time.values, return_index=True)
            save(tr.isel(time=np.sort(first)), truth_path(cache))
            return f"truth  days={tr.sizes['time']}  {time.time() - t0:.0f} s"
        m, y = task
        ds = load_forecast(m, variables, [y], max_inits=max_inits, workers=workers)
        assert ds.sizes["lead"] == 10
        assert max_inits or ds.sizes["init"] >= 350, f"{m} {y}: only {ds.sizes['init']} inits"
        save(ds, fc_path(cache, m, y))
        return f"{m:9s} {y}  inits={ds.sizes['init']}  {time.time() - t0:.0f} s"

    with ThreadPoolExecutor(jobs) as pool:
        futures = {pool.submit(one, t): t for t in tasks}
        for f in as_completed(futures):
            log("done " + f.result())


def train(set_name, models, years, variables, cache, art):
    os.makedirs(f"{art}/figures", exist_ok=True)
    mode = "loyo" if len(years) > 1 else "months"
    forecasts, truth = load_forecasts(cache, models, years), load_truth_cache(cache)
    cards, lines = [], []
    for var in variables:
        tag = var.replace("_", "")
        fc, obs = prepare(forecasts, truth, var)
        log(f"train {var}: {dict(fc.sizes)}")
        se, cell, _ = V.run_folds(fc, obs, mode)
        card = V.scorecard(se, var, set_name)
        cards.append(card)
        for ref in ["B0", "B0bc"]:
            lines.append(f"[vs {ref}] " + V.headline(card, var, lead_day=3, ref=ref))

        p = V.fit(fc, obs)  # final fit on all years -> operational weights and maps
        xr.Dataset({"w_B2": p["w_B2"], "w_B3s": p["w_B3s"], "bias": p["bias"]}).to_netcdf(
            f"{art}/weights_{set_name}_{tag}.nc")
        seasons = [str(s) for s in p["w_B3s"].season.values]
        seas = "JJAS" if "JJAS" in seasons else seasons[0]
        P.rmse_vs_lead(card, var, [f"m:{m}" for m in models] + ["B0bc", "B1", "B2", "B3s"],
                       f"{art}/figures/rmse_vs_lead_{tag}.png")
        P.weight_maps(p["w_B2"].sel(lead=3), f"{var} · B2 weights · Day 3", f"{art}/figures/weights_B2_{tag}_d3.png")
        P.weight_maps(p["w_B3s"].sel(lead=3, season=seas), f"{var} · B3s weights · Day 3 · {seas}",
                      f"{art}/figures/weights_B3s_{tag}_d3_{seas}.png")
        P.dominant_map(p["w_B3s"].sel(lead=3, season=seas), f"{var} · dominant model · Day 3 · {seas}",
                       f"{art}/figures/dominant_{tag}_d3_{seas}.png")
        P.gain_map(cell, "B3s", "B0bc", 3, f"{var} · held-out RMSE change · Day 3",
                   f"{art}/figures/gain_B3s_vs_B0bc_{tag}_d3.png")

    card = pd.concat(cards, ignore_index=True)
    card.to_csv(f"{art}/scorecard_{set_name}.csv", index=False)
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
               "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
              open(f"{art}/manifest.json", "w"), indent=1)
    cols = ["var", "lead_day", "rung", "rmse", "pct_vs_B0", "verdict_vs_B0", "pct_vs_B0bc", "verdict_vs_B0bc"]
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
    a = ap.parse_args()

    s = C.SETS[a.set]
    variables = [VAR_NAMES[v] for v in a.vars]
    cache, art = os.path.join(a.out, "cache"), os.path.join(a.out, "artifacts")
    np.random.seed(C.SEED)
    log(f"set {a.set}: models {s['models']}, years {s['years']}, vars {variables}")
    if not a.skip_download:
        download(s["models"], s["years"], variables, cache, a.jobs, a.max_inits)
    train(a.set, s["models"], s["years"], variables, cache, art)


if __name__ == "__main__":
    main()
