"""Frozen scope for PS26081 (MODEL_SPEC_81.md §4.1). Change only with the team's agreement:
changing the split, grid or domain invalidates every number already reported."""

import numpy as np
import pandas as pd

WB2 = "gs://weatherbench2/datasets"
GRID = "240x121_equiangular_with_poles_conservative"  # 1.5° dev grid

# Each model: list of (store url, years that store is trusted for).
# GraphCast year stores overlap (each starts on 1 Dec of the previous year), so every
# store is filtered to its own year to avoid duplicate inits.
STORES = {
    "hres": [(f"{WB2}/hres/2016-2022-0012-{GRID}.zarr", range(2016, 2023))],
    "graphcast": [(f"{WB2}/graphcast_v2/{y}-{GRID}.zarr", [y]) for y in (2018, 2020, 2022)],
    "pangu": [(f"{WB2}/pangu/2018-2022_0012_{GRID}.zarr", range(2018, 2023))],
    "fuxi": [(f"{WB2}/fuxi/2020-{GRID}.zarr", [2020])],
    "gencast": [(f"{WB2}/gencast/2020-{GRID}_mean.zarr", [2020])],
}

# The "1959-2022" ERA5 store ends on 31 Dec 2021; this one runs to 10 Jan 2023,
# which covers 2022 plus the Day-10 valid times of late-December inits.
ERA5 = f"{WB2}/era5/1959-2023_01_10-6h-{GRID}.zarr"

LAT = (5.0, 40.0)
LON = (65.0, 100.0)
INIT_HOUR = 0
LEAD_DAYS = np.arange(1, 11)
LEADS = pd.to_timedelta(LEAD_DAYS, unit="D")

T2M = "2m_temperature"
WIND = "10m_wind_speed"
MSLP = "mean_sea_level_pressure"
RAIN = "total_precipitation_24hr"
VARS = [RAIN, T2M, WIND, MSLP]
UNITS = {T2M: "K", WIND: "m/s", MSLP: "Pa", RAIN: "mm"}

# Model sets (spec §4.3)
SETS = {
    "S1": {"models": ["hres", "graphcast", "pangu"], "vars": [T2M, WIND, MSLP], "years": [2018, 2020, 2022]},
    "S2": {"models": ["hres", "graphcast"], "vars": [RAIN, T2M, WIND], "years": [2018, 2020, 2022]},
    "S3": {"models": ["hres", "graphcast", "pangu", "fuxi", "gencast"], "vars": [T2M, WIND, MSLP], "years": [2020]},
    "S4": {"models": ["hres", "graphcast", "fuxi", "gencast"], "vars": [RAIN], "years": [2020]},
}

# IMD seasons
SEASON_OF_MONTH = {1: "JF", 2: "JF", 3: "MAM", 4: "MAM", 5: "MAM",
                   6: "JJAS", 7: "JJAS", 8: "JJAS", 9: "JJAS", 10: "OND", 11: "OND", 12: "OND"}
SEASONS = ["JF", "MAM", "JJAS", "OND"]

# Weather regimes (spec §5.4). Climatology years contain no test year, so anomalies never see test data.
CLIM_YEARS = (2003, 2017)
REGIME_BOXES = {                      # (lat0, lat1, lon0, lon1)
    "cmz": (18, 28, 65, 88),          # Core Monsoon Zone (Rajeevan et al. 2010): active / break
    "nw": (28, 37, 70, 80),           # NW India rain in Dec-Apr: western disturbance proxy
    "heat": (20, 30, 70, 85),         # NW + central India afternoon T2m: heat regime
    "bay": (15, 26, 78, 92),          # Bay of Bengal / central India MSLP minimum: depression
}
REGIMES = ["normal", "active", "break", "depression", "western_disturbance", "heat"]

# Hyperparameters (spec §12)
ALPHA = 1.0          # weight temperature: w ∝ (1/MSE)^ALPHA
K_SHRINK = 20        # shrinkage of a sparse bin toward its parent, in cases
SMOOTH = 3           # spatial smoothing window, cells
N_BOOT = 1000
BLOCK_DAYS = 5
SEED = 26081
