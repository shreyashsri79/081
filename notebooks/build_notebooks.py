"""Generate the Kaggle notebooks from the cell sources below. Run: python notebooks/build_notebooks.py"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

SETUP = r'''# ── Setup (same in every notebook) ─────────────────────────────────────────────
# Kaggle: right panel → Settings → Internet ON.
import subprocess, sys, os
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "gcsfs", "zarr>=2.18,<3"], check=True)

REPO = "/kaggle/working/repo"
BRANCH = "main"
if not os.path.exists(REPO):
    subprocess.run(["git", "clone", "-q", "--depth", "1", "-b", BRANCH,
                    "https://github.com/shreyashsri79/081", REPO], check=True)
else:
    subprocess.run(["git", "-C", REPO, "pull", "-q"], check=True)
sys.path.insert(0, REPO)
COMMIT = subprocess.check_output(["git", "-C", REPO, "rev-parse", "--short", "HEAD"]).decode().strip()
print("code commit:", COMMIT)

import numpy as np, pandas as pd, xarray as xr
from blend import config as C
np.random.seed(C.SEED)
print("xarray", xr.__version__)'''


def nb(cells):
    return {
        "cells": [
            {"cell_type": kind, "metadata": {}, "source": src.strip("\n").splitlines(keepends=True),
             **({"outputs": [], "execution_count": None} if kind == "code" else {})}
            for kind, src in cells
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }


PROBE = [
    ("markdown", """# 00 · Probe the data stores
Checks every WeatherBench2 store the model uses: variables, leads, and how many 00 UTC inits per year.
Runs in ~5 min. **Settings: Internet ON, Accelerator None.** If a line says MISSING, stop and tell the team."""),
    ("code", SETUP),
    ("code", r'''from blend.sources import open_store, _lead_index

for model, stores in C.STORES.items():
    for url, years in stores:
        try:
            ds = open_store(url)
        except Exception as e:
            print(f"MISSING {model}: {url}\n   {e}")
            continue
        t = pd.DatetimeIndex(ds.time.values)
        per_year = pd.Series(t[t.hour == 0].year).value_counts().sort_index()
        per_year = {y: int(n) for y, n in per_year.items() if y in years}
        have = [v for v in C.VARS if v in ds] + (["(fuxi rain)"] if "total_precipitation_24hr_from_6hr" in ds else [])
        try:
            _lead_index(ds.prediction_timedelta); ok = "yes"
        except KeyError as e:
            ok = f"NO — {e}"
        print(f"{model:9s} {url.split('/')[-2]}/{url.split('/')[-1][:30]}")
        print(f"   vars: {have}")
        print(f"   00 UTC inits per year: {per_year}")
        print(f"   Day 1-10 leads present: {ok}")'''),
    ("code", r'''era5 = open_store(C.ERA5)
print("ERA5", str(era5.time.values[0])[:10], "->", str(era5.time.values[-1])[:10])
print("vars:", [v for v in C.VARS if v in era5])'''),
]

INGEST = [
    ("markdown", """# 01 · Ingest forecasts and truth
Downloads the chosen models, years and variables for the India box (5–40° N, 65–100° E), 00 UTC inits,
Day 1–10, and ERA5 truth. Writes small NetCDF files to `/kaggle/working/cache/`.

**Settings: Internet ON, Accelerator None.** Then **Save Version → Save & Run All (Commit)**.
Re-running skips files that already exist, so a timed-out session can simply be run again."""),
    ("code", SETUP),
    ("code", r'''# ── What to download ──────────────────────────────────────────────────────────
SET = "S1"                                   # S1 = HRES + GraphCast + Pangu, 2018/2020/2022
VARIABLES = [C.T2M, C.WIND]                  # add C.MSLP later; rain needs S2 + CHIRPS
MAX_INITS = None                             # e.g. 5 for a quick test run
CACHE = "/kaggle/working/cache"
os.makedirs(CACHE, exist_ok=True)
MODELS, YEARS = C.SETS[SET]["models"], C.SETS[SET]["years"]
print(MODELS, YEARS, VARIABLES)'''),
    ("code", r'''import time
from blend.sources import load_forecast
from blend.cache import fc_path

for model in MODELS:
    for year in YEARS:
        path = fc_path(CACHE, model, year)
        if os.path.exists(path):
            print("skip", path); continue
        t0 = time.time()
        ds = load_forecast(model, VARIABLES, [year], max_inits=MAX_INITS)
        ds.to_netcdf(path + ".tmp"); os.replace(path + ".tmp", path)   # no half-written files on timeout
        print(f"{model:9s} {year}  inits={ds.sizes['init']:3d}  vars={list(ds.data_vars)}  "
              f"{os.path.getsize(path)/1e6:6.1f} MB  {time.time()-t0:5.0f} s")
        # guard (spec trap): a missing year store silently shrinks the training set
        assert ds.sizes["lead"] == 10
        assert MAX_INITS or ds.sizes["init"] >= 350, f"{model} {year}: only {ds.sizes['init']} inits"'''),
    ("code", r'''from blend.sources import load_truth
from blend.cache import truth_path

path = truth_path(CACHE)
if not os.path.exists(path):
    t0 = time.time()
    # truth must cover every valid time: init year plus Day-10 into the next January
    parts = [load_truth(VARIABLES, f"{y}-01-01", f"{y+1}-01-11") for y in YEARS]
    tr = xr.concat(parts, "time")
    _, first = np.unique(tr.time.values, return_index=True)
    tr = tr.isel(time=np.sort(first))
    tr.to_netcdf(path + ".tmp"); os.replace(path + ".tmp", path)
    print(f"truth {dict(tr.sizes)}  {os.path.getsize(path)/1e6:.1f} MB  {time.time()-t0:.0f} s")
print(sorted(os.listdir(CACHE)))'''),
    ("code", r'''# Sanity check (spec C2): model-minus-model monthly mean is tenths of a unit, not orders of magnitude
from blend.cache import load_forecasts, load_truth as load_truth_cache
f = load_forecasts(CACHE, MODELS, YEARS[:1])
tr = load_truth_cache(CACHE)
for v in VARIABLES:
    a = {m: float(ds[v].isel(lead=2).mean()) for m, ds in f.items()}
    print(v, "Day-3 mean by model:", {m: round(x, 2) for m, x in a.items()}, " truth:", round(float(tr[v].mean()), 2))'''),
]

TRAIN = [
    ("markdown", """# 03 · Train and verify (B0 → B1 → B2 → B3s)
Fits the blending tables on training years and scores the held-out year (leave-one-year-out),
with a 95 % block-bootstrap confidence interval. Writes the scorecard, the slide-4 headline, weight maps
and the operational weights to `/kaggle/working/artifacts/`.

**Settings: Accelerator None. Internet ON (to clone the code).**
**Input:** right panel → *Add Input* → *Your Work* → the **01 ingest** notebook (its output holds `cache/`)."""),
    ("code", SETUP),
    ("code", r'''from blend.cache import find_cache, load_forecasts, load_truth
from blend.harmonise import prepare
from blend import verify as V
from blend import products as P
from blend.weights import dominant_model

SET = "S1"
VARIABLES = [C.T2M, C.WIND]
MODE = "loyo" if len(C.SETS[SET]["years"]) > 1 else "months"
CACHE = find_cache()
ART = "/kaggle/working/artifacts"
os.makedirs(f"{ART}/figures", exist_ok=True)
print("cache:", CACHE, sorted(os.listdir(CACHE)))

MODELS, YEARS = C.SETS[SET]["models"], C.SETS[SET]["years"]
forecasts = load_forecasts(CACHE, MODELS, YEARS)
truth = load_truth(CACHE)
print({m: dict(ds.sizes) for m, ds in forecasts.items()})'''),
    ("code", r'''cards, cells, choices = [], {}, {}
for var in VARIABLES:
    fc, obs = prepare(forecasts, truth, var)
    print(f"{var}: fc {dict(fc.sizes)}  cases with truth: {int(obs.notnull().any(['latitude','longitude']).sum())}")
    se, cell, chosen = V.run_folds(fc, obs, MODE)
    cards.append(V.scorecard(se, var, SET))
    cells[var], choices[var] = cell, chosen

card = pd.concat(cards, ignore_index=True)
card.to_csv(f"{ART}/scorecard_{SET}.csv", index=False)
cols = ["var", "lead_day", "rung", "rmse", "pct_vs_B0", "verdict_vs_B0", "pct_vs_B0bc", "verdict_vs_B0bc"]
card[card.lead_day.isin([1, 3, 5, 10])][cols].round(3)'''),
    ("code", r'''# ── The slide-4 lines: measured numbers only ──────────────────────────────────
lines = []
for var in VARIABLES:
    for ref in ["B0", "B0bc"]:
        lines.append(f"[vs {ref}] " + V.headline(card, var, lead_day=3, ref=ref))
lines.append(f"Set {SET}: {', '.join(MODELS)}; {MODE} over {YEARS}; 1.5° India box; 00 UTC; truth ERA5.")
open(f"{ART}/headline.txt", "w").write("\n".join(lines))
print("\n".join(lines))
print("\nB0 choices per fold:", choices)'''),
    ("code", r'''# ── Final fit on all years → operational weights + maps ─────────────────────
weights = {}
for var in VARIABLES:
    fc, obs = prepare(forecasts, truth, var)
    p = V.fit(fc, obs)
    weights[var] = xr.Dataset({"w_B2": p["w_B2"], "w_B3s": p["w_B3s"], "bias": p["bias"]})
    tag = var.replace("_", "")
    seasons = [str(x) for x in p["w_B3s"].season.values]
    SEAS = "JJAS" if "JJAS" in seasons else seasons[0]
    P.rmse_vs_lead(card, var, [f"m:{m}" for m in MODELS] + ["B0bc", "B1", "B2", "B3s"],
                   f"{ART}/figures/rmse_vs_lead_{tag}.png")
    P.weight_maps(p["w_B2"].sel(lead=3), f"{var} · B2 weights · Day 3", f"{ART}/figures/weights_B2_{tag}_d3.png")
    P.weight_maps(p["w_B3s"].sel(lead=3, season=SEAS), f"{var} · B3s weights · Day 3 · {SEAS}",
                  f"{ART}/figures/weights_B3s_{tag}_d3_{SEAS}.png")
    P.dominant_map(p["w_B3s"].sel(lead=3, season=SEAS), f"{var} · dominant model · Day 3 · {SEAS}",
                   f"{ART}/figures/dominant_{tag}_d3_{SEAS}.png")
    P.gain_map(cells[var], "B3s", "B0bc", 3, f"{var} · held-out RMSE change · Day 3",
               f"{ART}/figures/gain_B3s_vs_B0bc_{tag}_d3.png")
    ds = weights[var]
    ds.to_netcdf(f"{ART}/weights_{SET}_{tag}.nc")

import json, datetime
json.dump({"set": SET, "models": MODELS, "years": YEARS, "variables": VARIABLES, "mode": MODE,
           "code_commit": COMMIT, "alpha": C.ALPHA, "k_shrink": C.K_SHRINK, "smooth": C.SMOOTH,
           "n_boot": C.N_BOOT, "block_days": C.BLOCK_DAYS, "seed": C.SEED,
           "stores": {m: [u for u, _ in C.STORES[m]] for m in MODELS}, "truth": C.ERA5,
           "created_utc": datetime.datetime.utcnow().isoformat(timespec="seconds")},
          open(f"{ART}/manifest.json", "w"), indent=1)
print(sorted(os.listdir(ART)), sorted(os.listdir(f"{ART}/figures")))'''),
    ("code", r'''from IPython.display import Image, display
for f in sorted(os.listdir(f"{ART}/figures")):
    print(f); display(Image(f"{ART}/figures/{f}", width=700))'''),
]

for name, cells in [("00_probe", PROBE), ("01_ingest", INGEST), ("03_train_verify", TRAIN)]:
    with open(os.path.join(HERE, f"{name}.ipynb"), "w", encoding="utf-8") as fh:
        json.dump(nb(cells), fh, indent=1, ensure_ascii=False)
    print("wrote", name)
