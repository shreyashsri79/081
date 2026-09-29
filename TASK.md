# PS26081 — Task status

Updated 30 Sep 2026. Stage numbers (C0–C13) follow `MODEL_SPEC_81.md` / `WORKFLOW_AND_DECK_81.md`.
Legend: ✅ done · 🟡 code done, Kaggle result pending · 🔶 partly done · ❌ not started.

## Overall progress (rough estimate)

| Part | Progress | Note |
|---|---|---|
| Core model (data, truth, skill tables, weights, verification) | ~85 % | Measured on real data, 3 held-out years; per-region table in the scorecards |
| Weather regimes | ~80 % | Built and measured on hindcasts; gives no extra gain. Live runs now carry the same label (`blend/live_regime.py`) |
| Extreme-event guidance | ~90 % | Hindcast p95 / p99 / 25 mm events calibrated and measured. Live IMD heat wave and severe heat wave on 12 UTC T2m (`blend/heatwave.py`, uncalibrated). Hindcast heat wave needs a 12 UTC ingest on Kaggle |
| Products (maps, scorecards, files for the dashboard) | ~80 % | Figures, bundles, GeoJSON and state CSV from the API, NetCDF from `python -m blend.deliver`. No district table: a 1.5° cell is larger than most districts |
| Operational daily run (live IFS / AIFS / GFS) | ~95 % | `blend/live.py` daily at 09:30 UTC: B4 online weights, verification against the analysis, calibrated extremes, heat wave, regime label, optional NCUM / NEPS-G. Missing: ERA5T truth instead of the IFS analysis |
| Dashboard | ~85 % | `web/` connected to `blend/server.py` over real hindcast and live bundles; downloads on the Run log |
| NCUM / NEPS-G adapter | ~80 % | `blend/adapters.py`, tested on generated GRIB2 in NCMRWF-like layouts. Needs real NCMRWF files to confirm field names and to learn weights |
| **Whole project** | **~85 %** | Remaining work is mostly Kaggle runs (0.25°, forecast-day regime, heat-wave hindcast) and NCMRWF data |

## Measured results so far (held-out years 2018 / 2020 / 2022, 1,095 days, 1.5° India)

| Variable, Day 3 | Best single model | Best blend | Change | vs bias-corrected best model |
|---|---|---|---|---|
| Temperature (2 m) | GraphCast 0.903 K | B2c 0.860 K | **−4.8 %** (CI excludes 0) | −7.0 % |
| Wind (10 m) | GraphCast 0.668 m/s | B2c 0.603 m/s | **−9.7 %** | −4.3 % |
| Rain (24 h, CHIRPS truth) | GraphCast 5.424 mm | B2c 5.204 mm | **−4.0 %** | +0.3 % (bias-corrected GraphCast slightly better at Day 3; blend better at Day 10, −1.5 %) |

Extremes, Day 3, held-out (probability product):

| Event | Brier skill vs climatology | CSI: ours / best model / blend mean |
|---|---|---|
| Temperature p95 | +0.50 | 0.526 / 0.509 / 0.510 |
| Wind p95 | +0.48 | 0.495 / 0.486 / 0.502 |
| Rain p95 | +0.17 | 0.271 / 0.274 / 0.252 |
| Rain p99 | +0.08 | 0.156 / 0.165 / 0.138 |
| Rain ≥ 25 mm | +0.12 | 0.250 / 0.254 / 0.227 |

Findings:
- The gain grows with lead time (temperature −15 % at Day 10).
- Covariance-aware weights (B2c) beat inverse-MSE (B2), because GraphCast and Pangu make similar errors.
- Bias correction helps the blend by 2–4.6 %.
- Regime-conditioned weights (B3, B3c) change the weights (±0.1 over central India between monsoon active and break) but do not lower RMSE (±0.1 %).

## Stage-by-stage status

| Stage | Status | What exists | What is missing |
|---|---|---|---|
| C0 Scope | ✅ | `blend/config.py` frozen scope, sets S1–S4 | — |
| C1 Ingest | ✅ | WB2 loader for HRES, GraphCast, Pangu, FuXi, GenCast; parallel download; cache reuse between Kaggle runs | 0.25° stores not probed |
| C2 Harmonise | ✅ | Units, valid time, common mask | — |
| C3 Truth | 🔶 | ERA5 (T2m, wind); CHIRPS rain on the 1.5° grid, day alignment checked | IMD gridded rain |
| C4 Regimes | 🔶 | Init-day labels: active, break, depression, western disturbance, heat; climatology 2003–2017. Live runs: same rules and climatology (`models/live_regime.nc`), proxies from yesterday's live run and today's IFS analysis | Forecast-day regime (models' own fields); z500-based WD; k-means option |
| C5 Skill memory | ✅ | Bias, MSE, error covariance; shrinkage; 3×3 smoothing | — |
| C6 Weight ladder | 🔶 | B0, B0bc, B1, B2, B2raw, B3s, B3, **B2c**, B3c; **B4** online update in the live run | B5 stacking; tuning of α / k (fixed at 1 / 20) |
| C7 Extremes | ✅ | p95 / p99 / 25 mm events, per-model thresholds, weighted votes, calibration, Brier / CSI, case maps. Live: IMD heat wave + severe heat wave (`blend/heatwave.py`: 12 UTC T2m, ERA5 12 UTC normals, hills / coast / plains, 2 consecutive days) | Heat-wave hindcast and calibration (12 UTC ingest on Kaggle); IMD rain thresholds on 0.25° |
| C8 Verification | ✅ | Leave-one-year-out, blocked months, block-bootstrap CI, per-regime table, per-region table (`blend/regions.py`), gain maps | — |
| C9 Products | ✅ | Weight maps, dominant-model map, gain map, RMSE-vs-lead, deck figures, weights NetCDF; `blend/deliver.py`: GeoJSON (`/api/export/geojson`), state table CSV (`/api/export/csv`), run NetCDF (`python -m blend.deliver`). "Why this weight" = `/api/cell` | District table (not meaningful at 1.5°) |
| C10 Daily run | ✅ | `blend/live.py` + `.github/workflows/live-run.yml`: newest 00 UTC IFS, AIFS, GFS -> 1.5° -> B2c prior (IFS<-HRES, AIFS<-GraphCast, GFS<-HRES x1.5) + online B4 (centred error covariance vs IFS analysis, ~20-day memory) -> calibrated extremes + heat wave -> regime label -> `bundles/runs/live-YYYYMMDD`; `bundles/live_verification.json` | ERA5T truth instead of the IFS analysis |
| C11 Dashboard / API | ✅ | `web/` dashboard wired to `blend/server.py` (FastAPI) over measured hindcast bundles (S1–S4) and daily live bundles; downloads on the Run log | — |
| C12 NCUM adapter | 🔶 | `blend/adapters.py`: GRIB2 by shortName or WMO parameter numbers, any file layout, rain from totals or buckets, NEPS-G members averaged; `python -m blend.live run --ncum DIR --nepsg DIR` | Real NCMRWF files; weights learn from their verified days (B4) |
| Extra sets | ✅ | S3 (5 models, 2020) and S4 (rain, 4 models) measured (README table) | — |
| MSLP variable | ✅ | Measured: −6.2 % at Day 3 (README table) | — |
| 0.25° grid | ❌ | — | Probe stores, re-run (larger download) |

## Remaining work, in priority order

Done since 29 Sep: B4 online update, MSLP run, S3 / S4 results, per-region table, measured dashboard bundles,
live IMD heat wave, live regime label, NCUM / NEPS-G adapter, GeoJSON / CSV / NetCDF products.

| # | Task | Where | Why |
|---|---|---|---|
| 1 | Forecast-day regime for long leads | Kaggle | Last chance for a regime gain |
| 2 | Heat-wave hindcast: ingest 12 UTC T2m, score and calibrate the IMD rule | Kaggle (`sources.py` change, agree with the model owner) | Turns the live heat wave into a measured, calibrated product |
| 3 | 0.25° run | Kaggle, 3 h + download | Finer maps, IMD rain thresholds |
| 4 | α / k tuning by inner cross-validation; B5 stacking | Kaggle | Optional polish |
| 5 | NCUM / NEPS-G on real files | Needs NCMRWF data | Confirms field names; weights learn from verified days |
| 6 | ERA5T as live truth instead of the IFS analysis | Live run, 5-day delay | Removes the IFS-favouring truth |

## How to run (Kaggle, one cell, Internet ON)

```
!rm -rf 081 && git clone -q https://github.com/shreyashsri79/081 && cd 081 && pip install -q gcsfs "zarr>=2.18,<3" && python run_all.py && python run_all.py --set S2 --vars rain
```

Attach the previous run's output (Add Input → Your Work) to reuse downloaded data. Outputs: `/kaggle/working/artifacts/<set>/`.
