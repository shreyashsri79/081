# PS26081 — Hybrid AI–NWP Multi-Model Forecast Blending System

**Complete workflow documentation and slide-by-slide deck guide.** Written 28 Sep 2026.
Portal deadline: **30 Sep 2026** (idea deck, PDF only). Finale: 36-hour build.

Organisation: Ministry of Earth Sciences (MoES) · Department: National Centre for Medium Range Weather
Forecasting (NCMRWF) · Category: Software · Theme: Miscellaneous · Submissions on 25 Sep: 11 / 500.

**No code for 26081 exists in the repo yet.** This document is the plan, the reasoning behind it, and the deck.

### How to read this document

| If you are… | Read |
|---|---|
| New to weather forecasting | Part A (primer) first — every term used later is defined there |
| Building the models (Mridul) | Parts B, C, D |
| Building the app / deck (Shreyash) | Parts C §C10–C12, E, F |
| Deciding what we can promise | Part B §B3, Part D (the change / difficulty matrix) |
| Presenting | Part F (slides, speaker notes, judge Q&A) |

### Contents

- **Part A — Primer:** concepts, India-specific terms, metrics with formulas
- **Part B — The problem and the data:** statement, deliverables, fixed vs flexible, verified data inventory
- **Part C — The workflow, stage by stage:** 13 stages, each with purpose, inputs, outputs, steps, code, checks
- **Part D — What can change vs what will hurt us:** change-impact matrix and risk register
- **Part E — Team, timeline, and the finale build plan**
- **Part F — The deck, slide by slide:** final text, visuals, speaker notes, judge questions
- **Part G — Checklists and sources**

---

# Part A — Primer

## A1. Core concepts in plain words

| Term | Meaning | Why it matters here |
|---|---|---|
| **NWP** (Numerical Weather Prediction) | A physics model: solves fluid-dynamics and thermodynamics equations on a grid, forward in time, from today's observed state. Examples: ECMWF IFS, NOAA GFS, NCMRWF NCUM. | One of the two families we blend. Physically consistent, expensive, good at rare events it has never "seen". |
| **AI weather model** | A neural network trained on ~40 years of ERA5 to step the atmosphere forward. Examples: GraphCast, Pangu-Weather, FuXi, GenCast, Aurora. | The other family. Often lower RMSE than NWP for 3–10 days, but smoother fields and weaker on extremes. |
| **Hybrid** | Mixing both families. In this PS: the blend itself is the hybrid. | The PS title. |
| **Ensemble** | Many runs of one model from slightly different starting states (e.g. NEPS-G, 23 members; IFS ENS, 51). Spread between members = uncertainty. | GenCast is an AI ensemble; we use its mean and, optionally, its spread. |
| **Deterministic forecast** | One single run (e.g. HRES, GraphCast). | Most of our inputs. |
| **Initialisation time (init)** | When the forecast starts (e.g. 2020-07-01 00 UTC). | The "row" of our data. |
| **Lead time** | How far ahead: Day 1 = 24 h after init, Day 10 = 240 h. | Weights must differ by lead: AI models gain relative to NWP at longer leads. |
| **Valid time** | init + lead: the moment the forecast is about. | Truth is matched on valid time, not init time. |
| **Truth / analysis / reanalysis** | Best estimate of what actually happened. ERA5 is a reanalysis (model + all observations, 1940–present). | We score every forecast against truth. The choice of truth biases results (§C3). |
| **Bias** | Average error: forecast − truth. A model that is always 2 °C too warm has bias +2. | Removed before blending (bias correction). |
| **Bias correction** | Subtract each model's known bias for that place, lead and season. | Cheap and large gain; must be reported separately so the blend is not credited for it. |
| **Blending / multi-model ensemble / superensemble** | A weighted combination of several forecasts: `blend = Σ w_m · forecast_m`. | The whole PS. |
| **Weight map** | A map showing, for each grid cell, how much each model is trusted. | Named deliverable. |
| **Weather regime** | A recurring large-scale pattern: monsoon active, monsoon break, depression, western disturbance, heat wave. | Named condition in the PS. Model skill differs by regime. |
| **Skill** | How good a forecast is, measured against a reference (climatology or another model). | "Improved forecast skill" is outcome #3. |
| **Out-of-sample** | Scored on data the weights never saw. | The only honest skill. |
| **Grid / resolution** | 0.25° ≈ 28 km; 1.5° ≈ 167 km. NCUM runs at 12 km. | Controls data size and what "region" can mean. |

## A2. India-specific terms (judges will use these)

| Term | Meaning |
|---|---|
| **NCMRWF** | National Centre for Medium Range Weather Forecasting, Noida (MoES). Runs India's global models. The PS owner. |
| **NCUM** | NCMRWF Unified Model — India's deterministic global NWP (12 km), based on the UK Met Office Unified Model. |
| **NEPS-G** | NCMRWF Global Ensemble Prediction System — 23 members (1 control + 22 perturbed), 12 km, to 10 days. |
| **IMD** | India Meteorological Department — issues the official forecasts and warnings. |
| **IMD MME** | IMD's operational multi-model ensemble (since 2008): ECMWF, JMA, GFS, UKMO combined with grid-wise weights from past skill for district rainfall. **Our baseline to extend.** |
| **JJAS** | June–September: the southwest monsoon season. |
| **Core Monsoon Zone (CMZ)** | Central India box used to define active/break spells (Rajeevan et al. 2010). |
| **Active / break spell** | CMZ rainfall anomaly above +1 σ (active) or below −1 σ (break) for ≥ 3 consecutive days in July–August. |
| **Monsoon depression** | A low-pressure system (typically from the Bay of Bengal) that brings heavy rain to central India. |
| **Western disturbance (WD)** | Extra-tropical system from the west bringing winter rain/snow to NW India. |
| **IMD rainfall categories (24 h)** | Light 2.5–15.5 mm · Moderate 15.6–64.4 · **Heavy 64.5–115.5** · **Very heavy 115.6–204.4** · **Extremely heavy ≥ 204.5** |
| **IMD heat wave** | Tmax ≥ 40 °C (plains), ≥ 37 °C (coast), ≥ 30 °C (hills), **and** departure from normal ≥ 4.5 °C; or Tmax ≥ 45 °C regardless. |

## A3. Metrics, with formulas

Notation: `f` forecast, `o` observed truth, `N` number of cases, overbar = mean.

**Continuous variables (temperature, wind, pressure, rain amount)**

| Metric | Formula | Good value | Read as |
|---|---|---|---|
| Bias | `mean(f − o)` | 0 | Systematic warm/cold, wet/dry |
| MAE | `mean(|f − o|)` | low | Typical error size |
| **RMSE** | `sqrt(mean((f − o)²))` | low | Error size, punishes big misses; **our headline** |
| ACC (anomaly correlation) | `corr(f − clim, o − clim)` | 1 | Pattern right? (> 0.6 = "useful") |
| **Skill score** | `SS = 1 − RMSE_blend / RMSE_ref` | > 0 | % improvement over a reference (best single model) |

**Yes/no events (heavy rain, heat wave, high wind)** — from the 2×2 contingency table:

|  | Observed yes | Observed no |
|---|---|---|
| **Forecast yes** | H (hits) | F (false alarms) |
| **Forecast no** | M (misses) | C (correct negatives) |

| Metric | Formula | Good value |
|---|---|---|
| POD (probability of detection) | `H / (H + M)` | 1 |
| FAR (false alarm ratio) | `F / (H + F)` | 0 |
| CSI (critical success index) | `H / (H + M + F)` | 1 |
| ETS (equitable threat score) | `(H − Hr) / (H + M + F − Hr)`, `Hr = (H + M)(H + F) / N` | 1 (0 = no better than chance) |
| Frequency bias | `(H + F) / (H + M)` | 1 (> 1 over-forecasts) |

**Spatial / probabilistic**

| Metric | Formula / idea | Why we need it |
|---|---|---|
| **FSS** (fractions skill score) | Compare the *fraction* of cells exceeding a threshold within an n×n window: `FSS = 1 − mean((P_f − P_o)²) / (mean(P_f²) + mean(P_o²))` | Rain that is right but 50 km off scores 0 on CSI; FSS gives partial credit. Judges from NCMRWF use it. |
| Brier score | `mean((p − o)²)` with `p` a probability, `o` ∈ {0,1} | Scores extreme-event probabilities. |
| Brier skill score | `1 − BS / BS_climatology` | > 0 = better than climatology. |
| Reliability diagram | Plot forecast probability vs observed frequency | Shows whether "40 % chance" happens 40 % of the time. |

---

# Part B — The problem and the data

## B1. The problem statement (verbatim)

> Different forecasting systems perform differently depending on region, season, lead time and weather
> situation. Physical NWP models, ensemble forecasts and AI/ML weather models may each have strengths under
> different conditions. Therefore, there is a need for an intelligent blending system that can dynamically
> combine multiple forecasts.
>
> The challenge is to develop a hybrid AI–NWP blending framework that assigns adaptive weights to different
> forecast sources based on historical skill, forecast lead time, region, season and weather regime. The final
> product should provide an optimized forecast for rainfall, temperature, wind and extreme weather indicators.

**Parsing it into requirements**

| ID | Requirement (from the text) | Type |
|---|---|---|
| R1 | Combine **multiple forecast sources**: physical NWP, ensemble, AI/ML | Must |
| R2 | Weights are **adaptive**, not fixed | Must |
| R3 | Weights depend on **historical skill** | Must |
| R4 | … on **lead time** | Must |
| R5 | … on **region** | Must |
| R6 | … on **season** | Must |
| R7 | … on **weather regime** | Must |
| R8 | Output for **rainfall, temperature, wind** | Must |
| R9 | Output for **extreme weather indicators** | Must |
| R10 | Blend **better than individual models** | Must (outcome 3) |
| R11 | **Weight maps** | Must (outcome 2) |
| R12 | **Automated script / dashboard**, routine | Must (outcome 5) |

## B2. Expected outcomes → our deliverables

| # | Expected outcome (PS) | Our deliverable | Evidence we will show | Stage |
|---|---|---|---|---|
| 1 | Dynamically blended forecast | Blended 24 h rain, 2 m temperature, 10 m wind, MSLP, Day 1–10, daily | Maps + NetCDF | C6, C10 |
| 2 | Model weight maps | Per-cell × lead × regime weight maps; "dominant model" map | Animated map | C9 |
| 3 | Improved forecast skill | Blend vs best single model and vs equal mean | Scorecard with 95 % CI | C8 |
| 4 | Extreme weather guidance | Probability of heavy rain, heat wave, high wind | POD/FAR/CSI/FSS, reliability | C7 |
| 5 | Operational workflow | Scheduled daily job + dashboard; NCUM/NEPS-G adapter | Live page, run log | C10–C12 |

## B3. Fixed vs flexible

| Fixed — set by the PS or the template (do not change) | Flexible — our choice |
|---|---|
| Blend multiple sources incl. ≥ 1 physical NWP and ≥ 1 AI model | Which specific models |
| Weights adapt to skill, lead, region, season, regime (R3–R7) | How weights are computed |
| Output covers rain, temperature, wind, extremes | Resolution, domain, lead range |
| Must beat individual models | Which metric headlines the deck |
| Weight maps delivered | How they are drawn |
| Deck: ≤ 6 slides incl. title, template headings unchanged, PDF upload | Visuals, wording, layout inside each slide |

## B4. Data — what actually exists (verified 28 Sep 2026)

Probed the `.zmetadata` of each store in the public WeatherBench2 bucket (`gs://weatherbench2/datasets/`).
No login needed. HTTPS mirror: `https://storage.googleapis.com/weatherbench2/datasets/...`.

| Source | Family | Years | Leads | 24 h rain | T2m / 10 m wind / MSLP | Store used (1.5° dev grid) |
|---|---|---|---|---|---|---|
| **IFS HRES** | Physical NWP | 2016–2022, 00/12 UTC | 0–240 h, 6 h (41) | **yes** | yes | `hres/2016-2022-0012-240x121_equiangular_with_poles_conservative.zarr` |
| **GraphCast** | AI | 2018, 2020, 2022 | 6–240 h (40) | **yes** | yes | `graphcast_v2/{2018,2020,2022}-240x121_equiangular_with_poles_conservative.zarr` |
| **Pangu-Weather** | AI | 2018–2022 | 6–240 h (40) | **no** | yes | `pangu/2018-2022_0012_240x121_equiangular_with_poles_conservative.zarr` |
| **FuXi** | AI | 2020 | to 15 d (60) | **yes** (`…24hr_from_6hr`) | yes | `fuxi/2020-240x121_equiangular_with_poles_conservative.zarr` |
| **GenCast (mean)** | AI ensemble | 2020 | 12 h–15 d (30) | **yes** | yes | `gencast/2020-240x121_equiangular_with_poles_conservative_mean.zarr` |
| **Aurora** | AI | 2022 | 40 | **no** | yes | `aurora/2022-240x121_…` |
| **NeuralGCM** | Hybrid AI–physics | 2020 | 31 | no (P − E only) | pressure levels only | not used |
| **IFS ENS** | Ensemble NWP | 2018–2022 | — | check first | yes | `ifs_ens/…` (optional) |
| **ERA5** | Truth | 1959–2022 | — | yes (units: m) | yes | `era5/1959-2022-6h-240x121_equiangular_with_poles_conservative.zarr` |

Live and other truth sources:

| Source | Use | Access |
|---|---|---|
| **CHIRPS 2.0** daily, 0.05° | Rain truth over land | Open HTTPS (UCSB CHC) |
| IMD gridded rain 0.25° | Better rain truth | Unconfirmed from our network — try from the team's network |
| **NOAA GFS** 0.25° | Live NWP input | AWS open data (`noaa-gfs-bdp-pds`) |
| **ECMWF open data** — IFS 0.25° and **AIFS** | Live NWP + live AI input | AWS open data / `ecmwf-opendata` Python package |
| NCUM, NEPS-G | What NCMRWF cares about | **Not public** — adapter only |

### B4.1 Three consequences that shape everything

1. **Rain can be blended from four sources only: HRES, GraphCast, FuXi, GenCast.** Pangu and Aurora join for
   temperature, wind and pressure only.
2. **2020 is the only year all AI models overlap.** The **HRES + GraphCast + Pangu trio** has 2018, 2020 and 2022
   → true leave-one-year-out (LOYO). The trio carries the headline number; the five-model set is tested inside 2020
   with blocked months.
3. **Common lead range is Day 1–10** at 24 h steps.

### B4.2 Model-set matrix (which models can be blended for what, when)

| Model set | Variables | Years | Validation | Role |
|---|---|---|---|---|
| S1: HRES + GraphCast + Pangu | T2m, wind, MSLP | 2018, 2020, 2022 | LOYO (3 folds) | **Headline number** |
| S2: HRES + GraphCast | rain + T2m + wind | 2018, 2020, 2022 | LOYO | Rain headline |
| S3: HRES + GraphCast + Pangu + FuXi + GenCast | T2m, wind, MSLP | 2020 | Blocked months | Weight maps, "more models help?" |
| S4: HRES + GraphCast + FuXi + GenCast | rain | 2020 | Blocked months | Rain weight maps, extremes |

### B4.3 Data volume (India box 5–40° N, 65–100° E, 00 UTC inits, 10 leads, float32)

| Grid | Cells | Per model × variable × year | S1 total (3 models × 3 vars × 3 yr + truth) |
|---|---|---|---|
| 1.5° | 24 × 24 = 576 | ≈ 8 MB | < 0.3 GB |
| 0.25° | 141 × 141 = 19,881 | ≈ 290 MB | ≈ 3 GB |

Download is the slow part at 0.25° (remote zarr reads). Cache locally once.

---

# Part C — The workflow, stage by stage

```
 ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────┐
 │0 Scope   │─▶│1 Ingest    │─▶│2 Harmon- │─▶│3 Truth    │─▶│4 Regimes     │
 └──────────┘  └────────────┘  │  ise     │  └───────────┘  └──────┬───────┘
                               └──────────┘                        ▼
 ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────┐
 │12 NCUM   │◀─│11 Dashboard│◀─│10 Daily  │◀─│9 Products │◀─│5 Skill memory│
 │  adapter │  │            │  │   run    │  │ + maps    │  │6 Weights     │
 └──────────┘  └────────────┘  └──────────┘  └───────────┘  │7 Extremes    │
                                                            │8 Verify      │
                                                            └──────────────┘
```

Proposed code layout (nothing exists yet):

```
081/
  blend/
    sources.py     # C1  one loader per model, same interface
    harmonise.py   # C2  grid, leads, units, names
    truth.py       # C3  ERA5, CHIRPS
    regimes.py     # C4  season, active/break, depression, WD, heat
    skill.py       # C5  running MSE / bias tables
    weights.py     # C6  ladder B0…B5
    extremes.py    # C7  exceedance probabilities + calibration
    verify.py      # C8  metrics, LOYO, bootstrap
    products.py    # C9  NetCDF, PNG/GeoJSON, scorecard JSON
    daily.py       # C10 operational job
    server.py      # C11 FastAPI
    adapters/ncum.py  # C12
  data/            # gitignored cache
  web/             # copied pattern from 167/web
  notebooks/day1_measure.ipynb
```

Each stage below has: **Purpose · Inputs · Outputs · Steps · Code sketch · Check (done when) · Time · Can change / Hard to change.**

---

## C0. Scope

**Purpose.** Freeze the decisions every later stage depends on, so numbers stay comparable.

| Choice | Default | Why | Changing later costs |
|---|---|---|---|
| Domain | 5–40° N, 65–100° E | Mainland India + both seas | Re-run only |
| Dev grid | 1.5° | Fast; laptop-sized | Re-run only |
| Final grid | 0.25° | Closer to NCUM; better maps | Re-run + more download time |
| Variables | `total_precipitation_24hr`, `2m_temperature`, `10m_wind_speed`, `mean_sea_level_pressure` | R8 + MSLP for regimes | Adding one = small; dropping rain = violates R8 |
| Leads | Day 1–10 (24 h steps) | Common to all models | Re-run only |
| Inits | 00 UTC | All models have it | Re-run only |
| Split | S1/S2 LOYO; S3/S4 blocked months | §B4.1 | **Invalidates every number** |

**Done when:** this table is copied into `081/blend/config.py` and nobody edits it without telling the team.

---

## C1. Ingest

**Purpose.** Get every model's forecasts for the India box onto local disk in one shape.

**Inputs.** WB2 zarr stores (§B4). **Outputs.** `data/cache/{model}.zarr` with dims `(init, lead, lat, lon)`.

**Steps.**
1. Open each store anonymously.
2. Normalise names (`lat/lon` → `latitude/longitude`; `time` → `init`; `prediction_timedelta` → `lead`).
3. Sort latitude ascending, then slice to the India box.
4. Keep 00 UTC inits and leads 1–10 days.
5. Keep only the variables the model has; record the missing ones.
6. Write to local zarr.

**Code sketch.**

```python
import numpy as np, xarray as xr

WB2 = "gs://weatherbench2/datasets"
G = "240x121_equiangular_with_poles_conservative"
STORES = {
    "hres":      [f"{WB2}/hres/2016-2022-0012-{G}.zarr"],
    "graphcast": [f"{WB2}/graphcast_v2/{y}-{G}.zarr" for y in (2018, 2020, 2022)],
    "pangu":     [f"{WB2}/pangu/2018-2022_0012_{G}.zarr"],
    "fuxi":      [f"{WB2}/fuxi/2020-{G}.zarr"],
    "gencast":   [f"{WB2}/gencast/2020-{G}_mean.zarr"],
}
VARS = ["total_precipitation_24hr", "2m_temperature", "10m_wind_speed", "mean_sea_level_pressure"]
LEADS = [np.timedelta64(d, "D") for d in range(1, 11)]

def load(model: str) -> xr.Dataset:
    parts = []
    for url in STORES[model]:
        ds = xr.open_zarr(url, storage_options={"token": "anon"})
        ds = ds.rename({k: v for k, v in {"lat": "latitude", "lon": "longitude"}.items() if k in ds.dims})
        if model == "fuxi" and "total_precipitation_24hr_from_6hr" in ds:
            ds = ds.rename({"total_precipitation_24hr_from_6hr": "total_precipitation_24hr"})
        ds = ds[[v for v in VARS if v in ds]]
        ds = ds.sortby("latitude").sel(latitude=slice(5, 40), longitude=slice(65, 100))
        ds = ds.sel(time=ds.time.dt.hour == 0, prediction_timedelta=LEADS)
        parts.append(ds)
    return xr.concat(parts, "time").rename({"time": "init", "prediction_timedelta": "lead"})

# load("hres").to_zarr("081/data/cache/hres.zarr", mode="w")
```

**Check.** For each model: dims are `(init, lead, latitude, longitude)`; 10 leads; ~365 inits per year; no
all-NaN slices; the list of missing variables matches §B4.

**Time.** 1–2 h at 1.5°. Longer at 0.25°.

**Can change:** grid, box, years — re-run. **Hard:** GraphCast is split into three stores by year; forgetting one
silently shrinks the training set.

---

## C2. Harmonise

**Purpose.** Make models comparable cell by cell.

**Steps.**
1. **Grid.** All WB2 stores at the same `240x121` grid already match. For CHIRPS / live data: conservative
   regrid (`xesmf` or area-weighted block mean) onto the WB2 grid.
2. **Units.** Precipitation m → mm (`× 1000`); keep temperature in K internally, °C only for display.
3. **Accumulation window.** 24 h rain must end at the valid time for every model. Check one known heavy-rain
   day (e.g. Mumbai, a July date in 2020) — all models should peak on the same valid day.
4. **Valid time.** Add a coordinate `valid = init + lead`.
5. **Missing values.** Mask the whole cell/day if any model in the set is missing, so every model is scored on
   exactly the same cases.

**Check.** `(f_model − f_other).mean()` over a month is a few tenths of a unit, not orders of magnitude
(catches unit or accumulation mistakes).

**Hard to change:** the missing-value rule — if models are scored on different days, the comparison is invalid.

---

## C3. Truth

**Purpose.** A single "what actually happened" for every valid time.

| Variable | Truth | Note to state on the deck |
|---|---|---|
| T2m, 10 m wind, MSLP | ERA5 (same WB2 grid) | Standard in WeatherBench2. ERA5 is produced by the IFS system, so it slightly favours HRES. |
| 24 h rain | **CHIRPS 2.0** regridded to our grid (land only) | ERA5 rain is itself a model output — a weak truth for monsoon rain. CHIRPS has no ocean values. |
| 24 h rain (upgrade) | IMD 0.25° gridded rainfall | Use if it downloads; it is what IMD verifies against. |

**Steps.** Build `truth[valid, latitude, longitude]` per variable; then `truth.sel(valid=forecast.valid)` gives an
array aligned with the forecast.

**Check.** Plot truth for one heavy-rain day; the known event is visible in the right place.

**Hard to change:** switching rain truth after numbers are on the deck changes every rain score.

---

## C4. Regime labels

**Purpose.** Satisfy R7: weights conditioned on the weather situation.

| Label | Rule | Source | When it applies |
|---|---|---|---|
| Season | JF / MAM / JJAS / OND | Calendar | Always |
| Monsoon active / break / normal | CMZ area-mean rain standardised anomaly > +1 (active) / < −1 (break), ≥ 3 days | Truth rain (CHIRPS/IMD) | Jul–Aug (extend to JJAS with care) |
| Depression present | MSLP local minimum below a set anomaly over the Bay of Bengal / central India | ERA5 MSLP | JJAS |
| Western disturbance | 500 hPa geopotential trough over NW India (negative anomaly in a box) | ERA5 z500 | Dec–Apr |
| Heat regime | NW / central India T2m anomaly > +1 σ | ERA5 T2m | Mar–Jun |

**Leakage rule.** At forecast time the regime of the valid day is unknown. Two allowed options:

- **Init regime:** the regime on the init day (known). Simple; weaker at long leads.
- **Forecast regime:** apply the same rule to the *models' own* forecast fields for the valid day (majority vote).

Never use the true valid-day regime for weights in a scored forecast.

**Optional upgrade.** k-means (k = 4–6) on ERA5 850 hPa wind + MSLP anomalies over the domain; name the clusters
by looking at their mean maps. Only if the rule-based labels are too coarse.

**Check.** Regime calendar for 2020 JJAS looks plausible against published active/break dates.

**Time.** 2–3 h.

**Can change:** thresholds, number of regimes. **Hard:** dropping regimes entirely (violates R7).

---

## C5. Skill memory

**Purpose.** For every cell × lead × variable × season × regime × model, know the recent error.

**What is stored.**

| Table | Key | Value |
|---|---|---|
| `bias` | model, var, lead, season, cell | mean(f − o) over training data |
| `mse` | model, var, lead, season, regime, cell | mean((f − bias − o)²) over training data |
| `n` | same as `mse` | number of cases (for shrinkage) |

**Smoothing and shrinkage** (regime bins can be tiny):

- Spatial: average `mse` over a 3 × 3 cell neighbourhood.
- Shrink regime toward season: `mse_used = (n · mse_regime + k · mse_season) / (n + k)`, with `k ≈ 20` cases.

**Code sketch.**

```python
err = (fc - truth)                                   # dims: model, init, lead, lat, lon
bias = err.groupby("init.season").mean("init")        # per model, lead, season, cell
err_bc = err.groupby("init.season") - bias
mse = (err_bc ** 2).groupby(regime_label).mean("init")
mse = mse.rolling(latitude=3, longitude=3, center=True, min_periods=1).mean()
```

**Check.** Maps of `mse` look smooth and physically sensible (larger over the Western Ghats in JJAS, over NW
India for temperature in MAM).

---

## C6. Weights — the ladder

**Purpose.** Turn skill into weights. Each rung must beat the one below **out of sample** or it is not shipped.

| Rung | Method | Formula | Satisfies |
|---|---|---|---|
| **B0** | Best single model per variable × lead (chosen on training data) | — | The bar |
| **B1** | Equal mean of bias-corrected models | `blend = mean_m(f_m − bias_m)` | Baseline "MME" |
| **B2** | Inverse-MSE, per cell × lead (static) | `w_m = (1/MSE_m) / Σ_k (1/MSE_k)` | R3, R4, R5 (= IMD MME idea) |
| **B3** | B2 + season + regime | MSE from C5 with regime key | + R6, R7 — **our core claim** |
| **B4** | B3 with online update | `MSE_t = λ·MSE_{t−1} + (1−λ)·e_t²`, λ ≈ 0.95 (≈ 20-day memory) | "Dynamic" (R2) |
| B5 (optional) | Stacking: ridge / gradient boosting predicting truth from model forecasts + lead, season, regime, model spread; weights ≥ 0, Σ = 1 | Constrained least squares | Only if it beats B4 |

**Why inverse-MSE first.** It is transparent (a meteorologist can check it by hand), needs little data, and is
close to optimal when model errors are weakly correlated. Stacking learns correlations but needs more data than
2020 alone provides for S3/S4.

**Weight temperature (optional).** `w_m ∝ (1/MSE_m)^α` with α tuned on training data; α = 0 gives B1, large α
approaches B0.

**Code sketch.**

```python
inv = 1.0 / mse_used                                  # dims: model, var, lead, season, regime, cell
w = inv / inv.sum("model")
blend = ((fc - bias) * w.sel(season=s, regime=r)).sum("model")
```

**Check.** Weights sum to 1 in every cell; no weight is NaN; weight maps are not pure noise.

**Can change:** λ, α, k, smoothing size — all cheap. **Hard:** replacing the ladder with a deep net (Part D).

---

## C7. Extremes

**Purpose.** R9 / outcome 4. Averaging smooths peaks, so a blended rain field *under-forecasts* heavy rain.
Extremes are forecast as **probabilities**, not read from the blended mean.

| Indicator | Threshold | Method |
|---|---|---|
| Heavy rain | ≥ 64.5 mm / 24 h (also 115.6 and 204.5) | Quantile-map each model to truth, then `p = Σ w_m · 1[f_m ≥ thr]` |
| Heat wave | IMD criterion (§A2) | Same on T2m, with the Tmax-proxy caveat below |
| High wind | 10 m wind ≥ 15 m/s (our choice — state it) | Same on 10 m wind |

**Steps.**
1. **Quantile mapping** per model × cell × season: map each model's forecast distribution onto the truth
   distribution. This fixes models that never reach 64.5 mm because they are too smooth.
2. **Weighted exceedance probability** with the C6 weights.
3. **Calibration:** isotonic regression of `p` against observed exceedance on training data → reliable probabilities.
4. **Warning map:** cells with `p ≥` an operating threshold chosen to maximise CSI on training data.

**Caveat to state.** WB2 `2m_temperature` is instantaneous (00/12 UTC), not daily Tmax. Heat-wave guidance uses
it as a proxy with the threshold calibrated against truth at the same hour. At 12 UTC (17:30 IST) it is close to
the daily maximum.

**Verification.** POD, FAR, CSI, ETS, frequency bias, FSS at 1, 3, 5-cell windows; Brier skill score and
reliability diagram for the probabilities.

**Check.** Blend-mean heavy-rain frequency bias < 1 (confirms smoothing); probability product frequency bias near 1.

---

## C8. Verification

**Purpose.** R10. Show honestly whether and where the blend beats every single model.

**Protocol.**

| Set | Split | Folds |
|---|---|---|
| S1, S2 | Leave-one-year-out: train on two of 2018/2020/2022, test on the third | 3 |
| S3, S4 | Blocked months in 2020: train on 11 months, test on the held-out month | 12 |

Never random days: consecutive days are correlated, so random splits leak and inflate skill.

**Scores.**
- Continuous: RMSE, bias, ACC; skill score vs B0 and vs B1; per variable × lead.
- Rain: CSI, ETS, POD, FAR, FSS at 64.5 mm; plus RMSE.
- Probabilities: Brier skill score, reliability.

**Significance.** Paired bootstrap over test days (1,000 resamples, block length 5 days) of
`RMSE_blend − RMSE_B0` → 95 % CI. A gain is claimed only if the CI excludes 0.

**Breakdown.** By region (NW, central, NE, south peninsula, Bay, Arabian Sea), by regime, by lead. This is what
proves the weights earn their keep, and it is what the scorecard shows.

**The day-1 measurement for slide 4** (run before 30 Sep):
S1, T2m and 10 m wind, rungs B0 / B1 / B2, LOYO, 1.5°. Output one line:
*"T2m Day-3 RMSE: best single X K → blend Y K (−Z %, 95 % CI [a, b]), leave-one-year-out 2018/20/22."*

**Check.** The same number comes out twice from a clean run (reproducible).

---

## C9. Products

| Product | Format | Content |
|---|---|---|
| Blended fields | NetCDF + PNG tiles | var × lead × cell |
| **Weight maps** | PNG / GeoJSON | one panel per model per lead; animate over Day 1–10 |
| **Dominant-model map** | GeoJSON (categorical) | which model has the largest weight in each cell |
| Skill scorecard | JSON → table | rows var × lead, columns models + blend; green where blend wins with CI excluding 0 |
| Extreme guidance | PNG / GeoJSON + district CSV | exceedance probability; district roll-up = max / mean over cells in the district |
| "Why this weight" card | JSON per cell | skill history for that cell, season, regime; n cases |

Colour: one fixed categorical colour per model across every chart (HRES, GraphCast, Pangu, FuXi, GenCast), so the
eye learns them once.

---

## C10. Daily operational run

**Purpose.** Outcome 5: routine, automated blending.

```
06:00 IST (cron / GitHub Actions / Modal schedule)
 ├─ fetch  GFS 00 UTC (AWS noaa-gfs-bdp-pds)          → Day 1–10, 4 variables
 ├─ fetch  ECMWF IFS + AIFS 00 UTC (ecmwf-opendata)   → same
 ├─ harmonise to our grid (C2)
 ├─ regime of today from the analysis (C4, init regime)
 ├─ apply stored weights for (cell, lead, season, regime) (C6/B4)
 ├─ extremes (C7)
 ├─ write bundle  runs/YYYY-MM-DD/{fields.nc, tiles/, weights.json, extremes.geojson, meta.json}
 └─ update weights online once truth for past days arrives (B4)
```

**The catch — state it plainly.** The live models are not the models the weights were learned on.

| Live model | Training counterpart | Weight at start |
|---|---|---|
| ECMWF IFS open data | HRES | HRES weights transfer (same system) |
| ECMWF AIFS | none in WB2 | Equal share, then online update |
| NOAA GFS | none in WB2 | Equal share, then online update |
| GraphCast / Pangu live | not openly served daily | Excluded live, or run ourselves on a GPU (optional) |

**Check.** Three consecutive daily runs complete unattended and the dashboard shows the newest date.

**Can change:** schedule, host. **Hard:** promising GraphCast/Pangu live without a GPU to run them.

---

## C11. Dashboard

**Purpose.** Outcome 5 + the demo. Reuse the SatQuery stack (FastAPI + React + MapLibre, Field Atlas design system)
so slot 2 does not split the team.

**Screens.**

| Screen | What the user sees | Why |
|---|---|---|
| Forecast | India map, variable picker, Day 1–10 slider, blended field | Outcome 1 |
| Weights | Same map, model picker → weight map; toggle "dominant model" | Outcome 2 (the visual hook) |
| Skill | Scorecard table + RMSE-vs-lead line chart (blend vs each model) | Outcome 3 |
| Extremes | Probability maps for heavy rain / heat / wind; district list sorted by probability | Outcome 4 |
| Cell inspector | Click a cell → weights, skill history for this season and regime, n cases | Explainability |
| Run log | Last runs, sources fetched, what failed | Operational trust |

**API.**

| Endpoint | Returns |
|---|---|
| `GET /api/runs/latest` | run date, sources, status |
| `GET /api/field?var=&lead=` | blended field tile / GeoJSON |
| `GET /api/weights?var=&lead=&model=` | weight map |
| `GET /api/dominant?var=&lead=` | categorical map |
| `GET /api/scorecard` | skill table |
| `GET /api/extremes?type=&lead=` | probability map + district list |
| `GET /api/cell?lat=&lon=&var=&lead=` | weights + skill history |

---

## C12. NCUM / NEPS-G adapter

**Purpose.** Show NCMRWF how their models slot in.

- `adapters/ncum.py` implements the C1 interface for NCUM GRIB2 / NetCDF (via `cfgrib`).
- `adapters/nepsg.py` reads 23 members → ensemble mean (+ spread as an optional regime/uncertainty feature).
- Tested on GFS GRIB2 (same format family).
- Documented: variable names expected, grid, how to register a new model in one line.

**Say:** "adapter ready; needs NCMRWF data to learn weights". **Never say:** "tested on NCUM".

---

## C13. Known traps

| Trap | Consequence | Guard |
|---|---|---|
| Random-day train/test split | Inflated skill that collapses on new data | Year / block splits only (C8) |
| Rain verified against ERA5 | Rewards models that look like ERA5 | CHIRPS / IMD |
| True valid-day regime used | Leakage | Init or forecast regime (C4) |
| Extremes from the blended mean | Heavy rain under-forecast | Probabilities (C7) |
| T2m is instantaneous, not Tmax | Heat-wave criterion mis-applied | Proxy + calibration, stated |
| Tiny regime bins | Noisy weight maps | Smoothing + shrinkage (C5) |
| Credit taken for bias correction | Misleading claim | Report B1 separately |
| Models scored on different days | Unfair comparison | Common mask (C2) |
| One GraphCast year store missed | Silent smaller training set | Check init counts (C1) |

---

# Part D — What can change vs what will hurt us

## D1. Safe to change (low cost)

| Item | Options | Cost | What else must be updated |
|---|---|---|---|
| Grid resolution | 1.5° ↔ 0.25° | Re-run; more download at 0.25° | Numbers on slide 4 if already frozen |
| Domain box | India / South Asia | Re-run | — |
| λ, α, k, smoothing size | any | Re-run C5–C8 | — |
| High-wind threshold | any stated value | None | Slide text |
| Adding T/wind-only models (Pangu, Aurora) | yes | Loader + config line | Model colour |
| Stacking rung B5 | GBM / ridge / none | Optional | — |
| Regime thresholds, number of regimes (≥ 2) | any | Re-run C4–C8 | Regime legend |
| Colours, layout, dashboard host | any | None | — |
| Project short name, slide wording | any | None | — |

## D2. Risky to change (will cause difficulty)

| Change / promise | Why it hurts | Likely consequence | Do instead |
|---|---|---|---|
| Rainfall weights for Pangu / Aurora / NeuralGCM | No precipitation in WB2 | Cannot deliver; judge catches it | Rain set = HRES, GraphCast, FuXi, GenCast |
| Results on NCUM / NEPS-G | Not public | Promise we cannot keep | Adapter + "needs NCMRWF data" |
| Big headline gain ("20–30 % better") | Honest blend gains are a few % RMSE; judges know | Credibility loss | Measured gain with CI; lead with maps, regimes, extremes |
| Multi-year training for all five models | Only 2020 overlaps | Tiny training set, over-fit weights | S1/S2 for LOYO; S3/S4 within 2020 |
| Deep blending net as the core (U-Net, transformer) | Too little overlapping data; opaque weights; 36 h risk | Does not beat inverse-MSE; cannot explain | Ladder; deep net as "future work" |
| Changing the validation split after numbers exist | All numbers invalid | Re-do everything | Freeze in C0 |
| Dropping regime conditioning | R7 is explicit in the PS | Fails a named requirement | Keep season + active/break at minimum |
| GraphCast / Pangu in the live demo | Not served daily; need a GPU | Demo breaks | Live = IFS, AIFS, GFS; label it |
| District-level skill claims | Models are 0.25° at best | Judges push back | District roll-up of the gridded product |
| Rain verified on ERA5 only | Weak truth | Scientists reject the rain scores | CHIRPS / IMD |
| Switching PS (26079 / 26080) after upload | Idea registered per PS | New deck from scratch | Decide before 30 Sep |
| Claiming "real-time" AI models | Only IFS/AIFS/GFS are open daily | Over-claim | "Daily, from open live sources" |

## D3. Change-impact map (what a change in one stage breaks downstream)

| Changed stage | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 | C10 | C11 | Deck |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C0 grid / box | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ○ | numbers |
| C0 split | | | | | ● | ● | ● | ● | ● | | | **all numbers** |
| C1 add model | ● | ● | | | ● | ● | ● | ● | ● | ○ | ○ | model list |
| C3 rain truth | | | ● | ● | ● | ● | ● | ● | ● | | | rain numbers |
| C4 regimes | | | | ● | ● | ● | ● | ● | ● | ● | ○ | regime text |
| C6 weight method | | | | | | ● | ● | ● | ● | ● | | numbers |
| C11 UI | | | | | | | | | | | ● | screenshots |

● must redo · ○ small update

## D4. Risk register

| # | Risk | Likelihood | Impact | Owner | Mitigation | Early warning |
|---|---|---|---|---|---|---|
| 1 | Blend does not beat best single model | Medium | High | Mridul | Report per-region/regime wins; honest "matches"; B3/B4 | Day-1 run |
| 2 | CHIRPS download/regrid slow or broken | Medium | Medium | Mridul | Start with T2m/wind; rain second | First download attempt |
| 3 | Regime bins too small → noisy maps | High | Medium | Mridul | Shrinkage, fewer regimes | Weight maps look speckled |
| 4 | WB2 remote reads slow at 0.25° | Medium | Medium | Mridul | Cache once; dev at 1.5° | > 30 min per model |
| 5 | Live sources change format / URL | Low | Medium | Shreyash | Pin package versions; fallback to last good run | Daily job fails |
| 6 | Judges ask about NCUM | Certain | Medium | both | Adapter + honest answer (F slide 4) | — |
| 7 | Judges know IMD MME | Certain | High if ignored | both | Cite it as baseline; show the gap | — |
| 8 | Rival teams show slicker UI | High | Medium | Shreyash | Reuse SatQuery design; our edge is measured numbers | Public repos |
| 9 | Team time split with SatQuery | High | High | both | Reuse stack; keep 26081 scope tight | Missed checkpoints |
| 10 | Heat-wave proxy challenged | Medium | Low | Mridul | State the proxy + calibration | — |

---

# Part E — Team, timeline, finale plan

## E1. Before the upload (28–30 Sep)

| When | Who | Task | Output |
|---|---|---|---|
| 28 Sep | Mridul | C1–C3 + C5–C6 (B0–B2) + C8 for S1, T2m and wind, 1.5°, LOYO | The slide-4 line + one weight map PNG |
| 28–29 Sep | Shreyash | Deck (Part F), flow diagram, comparison table | Draft PDF |
| 29 Sep | both | Put the measured line and map into slide 4 / slide 2; re-pull live submission counts | Final PDF |
| 30 Sep | Shreyash | Upload PDF | Confirmation |

If the day-1 run does not beat B0: slide 4 says *"Blend matches the best single model on T2m (Day 3); regime
weights under test"* — never a made-up number.

## E2. Between upload and finale (if shortlisted)

| Week | Mridul (models) | Shreyash (app) |
|---|---|---|
| 1 | Rain: CHIRPS truth, S2/S4; regimes C4 | Backend skeleton, API contract, dashboard shell from 167/web |
| 2 | B3/B4, shrinkage; extremes C7 | Weights + dominant map screens; scorecard |
| 3 | 0.25° run; full verification C8 | Daily job C10 on IFS/AIFS/GFS; run log |
| 4 | Freeze numbers; write verification report | NCUM adapter C12; polish; offline demo bundle |

## E3. The 36-hour finale plan

| Hours | Goal | Done when |
|---|---|---|
| 0–2 | Set up; load cached data; run the frozen pipeline end to end | Scorecard regenerates |
| 2–8 | Integrate any data NCMRWF provides (NCUM/NEPS-G) through the adapter | New model appears in weight maps |
| 8–16 | Re-learn weights with the new model; verify | New scorecard with CI |
| 16–24 | Dashboard polish, cell inspector, extremes screen | All six screens work |
| 24–30 | Daily-run demo on today's live data | Today's date on screen |
| 30–34 | Rehearse demo + Q&A; freeze | Two clean run-throughs |
| 34–36 | Buffer | — |

---

# Part F — The deck, slide by slide

Template rules (from `SIH2026-IDEA-Presentation-Format.pptx`): **≤ 6 slides including the title**; keep the
template's headings unchanged; points, diagrams, infographics — not paragraphs; export and upload **PDF only**.

Judges for this PS are atmospheric scientists at NCMRWF/IMD. They reward: a named baseline, real verification
numbers, honest limits, and knowing the Indian context (monsoon regimes, IMD categories, NCUM).

---

### Slide 1 — Title

| Field | Content |
|---|---|
| Problem Statement ID | 26081 |
| Problem Statement Title | Hybrid AI–NWP Multi-Model Forecast Blending System |
| Theme | Miscellaneous |
| PS Category | Software |
| Team ID | from the portal |
| Team Name | as registered |

**Optional:** a product name under the title (e.g. a short name + tagline "Right model, right place, right regime").

**Visual:** the dominant-model map as a faded background.

**Can change:** product name, tagline, background. **Risky:** any mismatch with the portal (PS ID, theme,
category) can get the entry screened out.

---

### Slide 2 — Proposed Solution (IDEA TITLE)

Template asks for: detailed explanation · how it addresses the problem · innovation and uniqueness.

**Ready-to-paste text**

**THE PROBLEM**
- No forecast is best everywhere: physics models (IFS, NCUM) and AI models (GraphCast, FuXi, GenCast) win in
  different regions, seasons, lead times and monsoon phases.
- Forecasters reconcile five different answers by experience; IMD's multi-model ensemble (2008) blends NWP only,
  with fixed skill weights.

**OUR SOLUTION**
- A blending engine that learns, from past verification, how much to trust each model for **this grid cell, this
  lead time, this season and this weather regime**, and combines them into one forecast.
- Outputs: blended rain, temperature, wind (Day 1–10) · weight maps · skill scorecard vs every model ·
  heavy-rain / heat-wave / high-wind probabilities · a daily automated run with a dashboard.

**INNOVATION**
- **Physics + AI in one blend** — NWP and AI weather models, weighted cell by cell.
- **Regime-aware weights** — active vs break monsoon, depressions, western disturbances, heat spells.
- **Extremes done right** — probabilities, not the smoothed mean that hides heavy rain.
- **Auditable** — click any cell to see the skill history behind its weights.
- **NCUM-ready** — open data today; NCMRWF's models plug in through an adapter.

**Visual:** dominant-model map for Day 3 (from the day-1 run) with a 5-colour legend.

**Speaker notes (≈ 45 s).** "Every morning an Indian forecaster looks at five models that disagree. IMD already
blends physics models with fixed weights. We add AI models and let the weights change with the weather regime —
because a model that is best in an active monsoon is not best in a break. The map shows which model our system
trusts most, cell by cell, on Day 3."

**Can change:** wording, which innovation points, the visual. **Risky:** listing Pangu for rain; saying
"replaces the NCMRWF forecast" (say "assists forecasters"); calling IMD MME "old" or "wrong".

---

### Slide 3 — Technical Approach

Template asks for: technologies · methodology and process (flow charts / images / working prototype).

**Technologies (as a compact grid)**

| Layer | Tools |
|---|---|
| Data | WeatherBench2 (ERA5, IFS HRES, GraphCast, Pangu, FuXi, GenCast) · CHIRPS · NOAA GFS · ECMWF IFS & AIFS open data |
| Processing | Python · xarray · zarr · NumPy · xesmf |
| Blending & ML | Inverse-MSE weighting · online updating · scikit-learn / LightGBM (stacking) · isotonic calibration |
| Verification | RMSE · ACC · CSI · ETS · FSS · Brier · bootstrap CIs |
| App | FastAPI · React · MapLibre · scheduled daily job |

**Methodology (flow chart, left → right)**

`Model forecasts (NWP + AI)` → `Harmonise (grid, lead, units)` → `Truth (ERA5, CHIRPS)` →
`Regime detection (season, active/break, depression, WD)` → `Skill memory (cell × lead × season × regime)` →
`Adaptive weights` → `Blended forecast + extreme probabilities` → `Verification (leave-one-year-out)` →
`Daily run → dashboard`

**Side box — the weighting ladder:** best single model → equal mean → skill weights (IMD-MME style) → + season
& regime → + online update. *Each step ships only if it beats the previous one on unseen years.*

**Visual:** the flow chart; small inset of the dashboard (weights screen).

**Speaker notes (≈ 45 s).** "We start simple on purpose. Every rung of the ladder must beat the one below on a
year the weights never saw. That keeps every weight explainable to a forecaster, and it means our numbers are
real, not tuned."

**Can change:** library names, diagram style. **Risky:** drawing a deep neural network as the core; omitting
verification from the flow (judges look for it).

---

### Slide 4 — Feasibility and Viability

Template asks for: feasibility · potential challenges and risks · strategies.

**FEASIBILITY**
- All inputs are public today: WeatherBench2, CHIRPS, NOAA GFS, ECMWF open data. No login.
- Runs on a laptop at 1.5°; 0.25° on free Kaggle/Colab. No deep training required.
- **MEASURED TODAY:** *[from the day-1 run — e.g. "2 m temperature, Day 3: best single model X K → blend Y K
  RMSE (−Z %, 95 % CI [a, b]); leave-one-year-out 2018 / 2020 / 2022, HRES + GraphCast + Pangu"]*

**CHALLENGES → STRATEGIES**

| Challenge | Strategy |
|---|---|
| NCUM / NEPS-G not public | Adapter built to the same interface; tested on GFS GRIB2 |
| AI models overlap only in 2020 | 3-model set for multi-year tests; 5-model set within 2020 |
| Blending smooths heavy rain | Separate calibrated exceedance probabilities |
| Live models ≠ training models | Online weight update from an equal start |
| Rain truth quality | CHIRPS / IMD gridded, not reanalysis |

**VIABILITY**
- Technical: open-source stack, every capability measured.
- Economic: zero licence cost; runs on existing NCMRWF hardware.
- Operational: fits beside the current MME workflow; one daily job.

**Speaker notes (≈ 40 s).** Read the measured line exactly. Then: "We cannot access NCUM, so we built the
adapter and tested it on GFS, which uses the same format."

**Likely judge questions (and answers)**

| Question | Answer |
|---|---|
| Why not use NCUM? | Not public. Adapter ready; give us 1–2 seasons of NCUM output and the weights learn in minutes. |
| Is the gain significant? | Bootstrap 95 % CI over test days, blocked by 5 days; we claim only where the CI excludes 0. |
| How is this different from IMD MME? | AI models included; weights change with season and regime and update daily; extremes as calibrated probabilities. |
| Why verify rain on CHIRPS, not ERA5? | ERA5 rain is model output; CHIRPS uses gauges + satellite. IMD gridded preferred when available. |
| Doesn't ERA5 favour HRES? | Slightly, for T2m/wind; we state it. Rain uses independent truth. |
| Why not a deep network? | Only one year where all AI models overlap — too little to train one honestly. Inverse-MSE is near-optimal here and explainable. |

**Can change:** table rows, wording. **Risky:** replacing the measured line with a target; rounding it up; hiding
a "no gain" result.

---

### Slide 5 — Impact and Benefits

Template asks for: impact on target audience · benefits (social, economic, environmental, etc.).

**WHO BENEFITS**
- NCMRWF / IMD forecasters — one best-estimate forecast, with the reason for each weight.
- State disaster management authorities — earlier, calibrated heavy-rain and heat-wave signals.
- Agro-met advisory units (Gramin Krishi Mausam Sewa) — better rain and temperature inputs for advisories.
- Power-grid planners — temperature (demand) and wind (generation) forecasts.
- Researchers — a live Indian scorecard of AI vs physics models.

**BENEFITS**
- **Social:** better-targeted warnings for heavy rain and heat waves.
- **Economic:** more value from forecasts already produced; no licence cost.
- **Environmental:** better wind and temperature forecasts support renewable-energy scheduling.
- **Operational / governance:** every weight traceable to measured skill — auditable for official use.

**Comparison table**

| Capability | Single model | IMD MME (2008) | Ours |
|---|---|---|---|
| Uses AI weather models | ◐ | ✗ | ✓ |
| Weights by region + lead | ✗ | ✓ | ✓ |
| Weights by season + weather regime | ✗ | ✗ | ✓ |
| Updates weights daily | ✗ | ✗ | ✓ |
| Extremes as calibrated probabilities | ✗ | ✗ | ✓ |
| Weight maps shown to forecasters | ✗ | ✗ | ✓ |

**Speaker notes (≈ 30 s).** Use the table; point at the regime row.

**Can change:** audiences, benefit wording. **Risky:** lives-saved or ₹ figures without a source (add one real,
cited number or none).

---

### Slide 6 — Research and References

**References**
1. SIH 2026 PS26081, MoES / NCMRWF — official problem statement.
2. Rasp et al., "WeatherBench 2: A benchmark for the next generation of data-driven global weather models," JAMES, 2024.
3. Lam et al., "Learning skillful medium-range global weather forecasting" (GraphCast), Science, 2023.
4. Bi et al., "Accurate medium-range global weather forecasting with 3D neural networks" (Pangu-Weather), Nature, 2023.
5. Chen et al., "FuXi: a cascade machine learning forecasting system for 15-day global weather forecast," npj Clim. Atmos. Sci., 2023.
6. Price et al., "Probabilistic weather forecasting with machine learning" (GenCast), Nature, 2025.
7. Roy Bhowmik & Durai — IMD multi-model ensemble for district rainfall, J. Earth Syst. Sci. / Meteorol. Atmos. Phys.
8. Krishnamurti et al., "Improved weather and seasonal climate forecasts from multimodel superensemble," Science, 1999.
9. Rajeevan, Gadgil & Bhate, "Active and break spells of the Indian summer monsoon," J. Earth Syst. Sci., 2010.
10. Funk et al., CHIRPS, Scientific Data, 2015 · Hersbach et al., ERA5, QJRMS, 2020.
11. Roberts & Lean, "Scale-selective verification of rainfall accumulations" (FSS), Mon. Wea. Rev., 2008.

**Data links box:** WeatherBench2 (`gs://weatherbench2`) · CHIRPS (UCSB CHC) · NOAA GFS (AWS) · ECMWF open data.

**Project links box:** GitHub · demo video · prototype (fill before upload).

**Can change:** order; add papers. **Risky:** a wrong year or venue — NCMRWF judges know these papers. Check each
before upload.

---

# Part G — Checklists and sources

## G1. Before upload (30 Sep)

- [ ] Day-1 measured line on slide 4 (or the honest "matches best model" line)
- [ ] Weight / dominant-model map from real data on slide 2
- [ ] No rainfall claims for Pangu / Aurora / NeuralGCM
- [ ] IMD MME cited as the baseline and shown in the comparison table
- [ ] Heat-wave text says T2m is a proxy for Tmax
- [ ] ≤ 6 slides, template headings intact, exported to PDF
- [ ] Every reference checked
- [ ] Live submission count re-pulled on 29 / 30 Sep

## G2. Before the finale

- [ ] Split frozen; all numbers reproducible from one command
- [ ] Rain (CHIRPS) and regimes (B3/B4) verified with CIs
- [ ] Extremes: reliability diagram + CSI/FSS
- [ ] Daily job ran three days unattended
- [ ] NCUM adapter documented and tested on GFS GRIB2
- [ ] Offline demo bundle (no venue Wi-Fi needed)
- [ ] Someone can explain FSS, ETS and active/break spells without notes

## G3. Sources used for this document

| Source | What it gave |
|---|---|
| `extra/reference/sih_2026_problem_statements.json` | Official statement text |
| `SLOT2_CANDIDATES.md` (root, 25 Sep) | Why 26081; first design and risks; submission counts |
| `extra/problem-statements/shortlist_ranked.md` | 26079 / 26080 / 26081 share ~80 % of the data pipeline |
| `extra/templates-and-examples/SIH2026-IDEA-Presentation-Format.pptx` | 6-slide structure and rules |
| WeatherBench2 bucket `.zmetadata` probe, 28 Sep | Variables, years, leads per model (§B4) |
| [Roy Bhowmik & Durai, J. Earth Syst. Sci.](https://link.springer.com/article/10.1007/s12040-011-0013-5) · [Meteorol. Atmos. Phys. 2014](https://link.springer.com/article/10.1007/s00703-014-0334-4) | IMD MME design |
| Public GitHub repos for PS 26081 ([AtmosArbiter](https://github.com/Abhi-engg/AtmosArbiter), [AtmosFusion](https://github.com/Aayush-207/NPW-forecast-blending-system)) | What rivals pitch: deep architectures, stated targets, no measured results |
