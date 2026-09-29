# PS26081 — Task status

Updated 29 Sep 2026. Stage numbers (C0–C13) follow `MODEL_SPEC_81.md` / `WORKFLOW_AND_DECK_81.md`.
Legend: ✅ done and run on Kaggle · 🟡 code done, Kaggle result pending · 🔶 partly done · ❌ not started.

## Overall progress (rough estimate)

| Part | Progress | Note |
|---|---|---|
| Core model (data, truth, skill tables, weights, verification) | ~85 % | Measured on real data, 3 held-out years |
| Weather regimes | ~70 % | Built and measured; gives no extra gain yet |
| Extreme-event guidance | ~60 % | Code done; Kaggle run pending; IMD heat-wave rule missing |
| Products (maps, scorecards, files for the dashboard) | ~40 % | Figures done; forecast fields / GeoJSON / API files not exported |
| Operational daily run (live IFS / AIFS / GFS) | 0 % | Biggest gap for PS outcome 5 |
| Dashboard | ~30 % | Teammate's `web/` frontend exists; not connected to model outputs |
| NCUM / NEPS-G adapter | 0 % | |
| **Whole project** | **~55 %** | |

## Measured results so far (held-out years 2018 / 2020 / 2022, 1,095 days, 1.5° India)

| Variable, Day 3 | Best single model | Best blend | Change | vs bias-corrected best model |
|---|---|---|---|---|
| Temperature (2 m) | GraphCast 0.903 K | B2c 0.860 K | **−4.8 %** (CI excludes 0) | −7.0 % |
| Wind (10 m) | GraphCast 0.668 m/s | B2c 0.603 m/s | **−9.7 %** | −4.3 % |
| Rain (24 h, CHIRPS truth) | GraphCast 5.424 mm | B2c 5.204 mm | **−4.0 %** | +0.3 % (bias-corrected GraphCast slightly better at Day 3; blend better at Day 10, −1.5 %) |

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
| C4 Regimes | 🔶 | Init-day labels: active, break, depression, western disturbance, heat; climatology 2003–2017 | Forecast-day regime (models' own fields); z500-based WD; k-means option |
| C5 Skill memory | ✅ | Bias, MSE, error covariance; shrinkage; 3×3 smoothing | — |
| C6 Weight ladder | 🔶 | B0, B0bc, B1, B2, B2raw, B3s, B3, **B2c**, B3c | **B4 daily online update**; B5 stacking; tuning of α / k (fixed at 1 / 20) |
| C7 Extremes | 🟡 | p95 / p99 / 25 mm events, per-model thresholds, weighted votes, calibration, Brier / CSI, case maps | Kaggle result; IMD heat-wave rule (needs a 12 UTC / Tmax field); IMD rain thresholds on 0.25° |
| C8 Verification | 🔶 | Leave-one-year-out, blocked months, block-bootstrap CI, per-regime table, gain maps | Per-region table (NW, central, NE, south, Bay, Arabian Sea) |
| C9 Products | 🔶 | Weight maps, dominant-model map, gain map, RMSE-vs-lead, deck figures, weights NetCDF | Blended forecast fields NetCDF, GeoJSON tiles, district CSV, "why this weight" JSON |
| C10 Daily run | ❌ | — | Fetch ECMWF IFS + AIFS and GFS 00 UTC, harmonise, apply weights, write `runs/YYYY-MM-DD/` |
| C11 Dashboard / API | 🔶 | Teammate's frontend MVP in `web/` | `server.py` (FastAPI endpoints); wiring to real outputs |
| C12 NCUM adapter | ❌ | — | `adapters/ncum.py`, `adapters/nepsg.py` on GRIB2 |
| Extra sets | 🟡 | S3 (5 models, 2020) and S4 (rain, 4 models) running on Kaggle | Results |
| MSLP variable | ❌ | Code supports it | One Kaggle run: `python run_all.py --vars mslp` |
| 0.25° grid | ❌ | — | Probe stores, re-run (larger download) |

## Remaining work, in priority order

| # | Task | Est. time | Why |
|---|---|---|---|
| 1 | Read S3 / S4 results (running now) | — | Do more models help? |
| 2 | Kaggle run with extremes (S1 + S2) | 15 min | PS outcome 4 |
| 3 | Export products for the dashboard: blended fields, weights, extremes as NetCDF + JSON / GeoJSON | 2 h | Connects model to the frontend |
| 4 | Daily operational run on live IFS / AIFS / GFS (C10) | 4–6 h | PS outcome 5, biggest gap |
| 5 | B4 online weight update | 2 h | "Dynamic" weights; used by the daily run |
| 6 | FastAPI `server.py` + connect `web/` | 3 h | Demo |
| 7 | MSLP run | 10 min | Completes variable list |
| 8 | Per-region verification table | 1 h | Judges ask "where does it work?" |
| 9 | Forecast-day regime for long leads | 2 h | Last chance for a regime gain |
| 10 | IMD heat-wave rule (12 UTC T2m) | 2 h | Named extreme in the PS |
| 11 | NCUM / NEPS-G adapter | 2 h | NCMRWF's own models |
| 12 | 0.25° run | 3 h + download | Finer maps, IMD thresholds |
| 13 | α / k tuning by inner cross-validation; B5 stacking | 2 h | Optional polish |

## How to run (Kaggle, one cell, Internet ON)

```
!rm -rf 081 && git clone -q https://github.com/shreyashsri79/081 && cd 081 && pip install -q gcsfs "zarr>=2.18,<3" && python run_all.py && python run_all.py --set S2 --vars rain
```

Attach the previous run's output (Add Input → Your Work) to reuse downloaded data. Outputs: `/kaggle/working/artifacts/<set>/`.
