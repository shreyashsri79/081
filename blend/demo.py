"""Demo bundles until the real model output arrives: generated inputs, real pipeline.

    python -m blend.demo --out bundles            # ~3 min; writes demo cache + artifacts under --work, bundles to --out

Writes a cache in exactly the layout run_all.py produces (per-variable fc_* files, ERA5 truth, CHIRPS-style land-only
rain, regime indices), scores it with the real verify pipeline (scorecard_<SET>.csv per set folder), then exports
with `blend.export --demo`. Every number is generated, so every bundle says provenance "synthetic" and carries a
DEMO note; the dashboard labels it. The weather is shaped to look like India (monsoon onset and withdrawal, active /
break spells, Bay lows moving north-west, the Thar heat low, orographic rain) so the screens can be judged as they
will look with real data.
"""

import argparse
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import config as C
from .cache import chirps_path, fc_path, truth_path

LAT = np.arange(6.0, 39.01, 1.5)      # the WB2 1.5° cells inside the India box
LON = np.arange(66.0, 99.01, 1.5)
YEARS = [2018, 2020, 2022]
CLIM = list(range(C.CLIM_YEARS[0], C.CLIM_YEARS[1] + 1))
MONTHS = (4, 5, 6, 7, 8, 9)
MODELS_BY_YEAR = {2018: ["hres", "graphcast", "pangu"], 2020: ["hres", "graphcast", "pangu", "fuxi", "gencast"],
                  2022: ["hres", "graphcast", "pangu"]}
U10, V10 = "10m_u_component_of_wind", "10m_v_component_of_wind"
DEMO_DATES = ["2020-07-15", "2020-06-08", "2020-08-20", "2020-05-12", "2018-07-20", "2022-05-02"]

LA, LO = np.meshgrid(LAT, LON, indexing="ij")


def g(cx, cy, sx, sy):
    return np.exp(-(((LO - cx) / sx) ** 2) - ((LA - cy) / sy) ** 2)


def sig(x):
    return 1 / (1 + np.exp(-x))


ELEV = np.where(LO > 73.5, sig((LA - (35.6 - (LO - 73) * 0.33)) * 2.2), 0.0)            # plateau / high Himalaya
GHATS = np.exp(-(((LO - (73.3 + (LA - 8) * 0.13)) / 1.0) ** 2)) * sig((LA - 8) * 2) * sig((21 - LA) * 2)
ORO = np.clip(GHATS + np.exp(-(((LA - (33.5 - (LO - 73) * 0.33)) / 1.3) ** 2)) * ((LO > 74) & (LO < 96))
              + g(92.5, 25, 2, 1.5), 0, 1)


def land_mask():
    """India from the SoI outline plus the neighbours' land (north of 22.5° N, Myanmar, Sri Lanka): CHIRPS covers land."""
    from .geo import india_mask
    india = india_mask(LAT, LON)
    other = (LA > 22.5) | ((LO > 92.5) & (LA > 15)) | ((LO > 79.6) & (LO < 82) & (LA > 5.9) & (LA < 9.9))
    return india | other


SEA = ~land_mask()


def smooth_noise(rng, n, rho=0.7, passes=2):
    """AR(1) in time, box-smoothed in space: weather-like anomalies, unit variance."""
    e = rng.normal(size=(n, len(LAT), len(LON)))
    for _ in range(passes):
        p = np.pad(e, ((0, 0), (1, 1), (1, 1)), mode="edge")
        e = sum(p[:, a:a + len(LAT), b:b + len(LON)] for a in range(3) for b in range(3)) / 9
    for t in range(1, n):
        e[t] = rho * e[t - 1] + np.sqrt(1 - rho ** 2) * e[t]
    return e / e.std()


def days_for(years):
    d = []
    for y in years:
        d += list(pd.date_range(f"{y}-{MONTHS[0]:02d}-01", f"{y}-{MONTHS[-1]:02d}-30", freq="D"))
        d += list(pd.date_range(f"{y}-10-01", periods=11, freq="D"))   # Day-10 truth of late-September inits
    return pd.DatetimeIndex(d)


def truth(days: pd.DatetimeIndex, seed: int) -> dict[str, np.ndarray]:
    """Daily 00 UTC truth fields in WB2 units: rain (m), T2m (K), wind (m/s), MSLP (Pa), u, v."""
    rng = np.random.default_rng(seed)
    n = len(days)
    doy = days.dayofyear.values
    mon = sig((doy - 158) / 6) * sig((272 - doy) / 7)             # monsoon strength: onset ~7 Jun, withdrawal ~29 Sep
    heat = np.exp(-(((doy - 138) / 25) ** 2))                       # pre-monsoon heat, peak mid-May
    spell = smooth_noise(rng, n, rho=0.93, passes=0).mean((1, 2))   # active / break swings of the whole monsoon
    spell = spell / spell.std()
    n1, n2, n3 = smooth_noise(rng, n), smooth_noise(rng, n), smooth_noise(rng, n)
    out = {k: np.zeros((n, len(LAT), len(LON))) for k in (C.RAIN, C.T2M, C.MSLP, U10, V10)}
    # Bay of Bengal lows: born every ~9 days in JJAS, drift north-west for a week
    lows = np.zeros((n, len(LAT), len(LON)))
    lowc = [[] for _ in range(n)]
    for t0 in range(0, n, 9):
        if mon[t0] < 0.5 or rng.random() < 0.25:
            continue
        depth = 0.6 + 0.8 * rng.random()
        for age in range(7):
            t = t0 + age
            if t >= n:
                break
            cx, cy = 88.5 - 1.1 * age, 19.5 + 0.45 * age
            lows[t] += depth * g(cx, cy, 2.6, 2.3)
            lowc[t].append((cx, cy, depth))
    for t in range(n):
        m = mon[t] * (1 + 0.35 * spell[t])
        rain = (m * (110 * GHATS + 75 * g(91.5, 25.5, 2.6, 1.6)
                     + 26 * np.exp(-(((LA - (22 + (LO - 80) * 0.05)) / 2.3) ** 2)) * sig((LO - 74) * 1.5) * sig((89 - LO) * 1.5)
                     + 14 * g(69, 14, 4, 5) + 10 * g(86, 8, 9, 3))
                + 70 * lows[t]
                + (1 - mon[t]) * heat[t] * (35 * g(91.5, 26, 2.5, 1.8) + 18 * g(76.5, 9.5, 1.5, 2)))
        rain *= (1 - 0.85 * ELEV) * np.where((LO < 74) & (LA > 24), 0.2, 1.0)
        rain = np.maximum(0, rain * np.exp(0.6 * n1[t]) - 2)
        out[C.RAIN][t] = rain / 1000.0
        sea_t = np.where(SEA, 28.6, 26 + 11 * heat[t] * g(72.5, 26.5, 6, 4.5) + 6 * heat[t] * g(79, 24, 6, 4)
                         + 3 * (1 - mon[t]) - 0.06 * np.minimum(rain, 60) - 26 * ELEV)
        out[C.T2M][t] = 273.15 + sea_t + 1.3 * n2[t]
        out[C.MSLP][t] = 100 * (1007.5 + (22 - LA) * 0.22 - (5 + 6 * heat[t]) * g(70, 29, 6, 5) - 5 * lows[t] + 1.1 * n3[t])
        # wind: SW monsoon, westerlies in the north, NW pre-monsoon flow, cyclonic turning round the lows
        south = sig((26 - LA) * 0.6)
        dx = mon[t] * 0.75 * south + (1 - mon[t]) * 0.8 * sig((LA - 18) * 0.5) + 0.9 * sig((LA - 29) * 0.8)
        dy = mon[t] * 0.65 * south - (1 - mon[t]) * 0.55 * sig((LA - 18) * 0.5)
        for cx, cy, depth in lowc[t] + [(70, 29, 0.6 + 0.8 * heat[t])]:
            w = depth * g(cx, cy, 3.2, 3.2)
            dx += -(LA - cy) / 3.2 * w * 1.6
            dy += (LO - cx) / 3.2 * w * 1.6
        nrm = np.hypot(dx, dy) + 1e-6
        speed = np.maximum(0.5, 3.5 + (4 + 9 * m) * g(66.5, 13, 6, 5) + 5 * lows[t] + 1.8 * SEA - 1.5 * ELEV + 1.2 * n1[t])
        out[U10][t], out[V10][t] = speed * dx / nrm, speed * dy / nrm
    out[C.WIND] = np.hypot(out[U10], out[V10])
    return out


# model personalities: (Day-1 error scale, growth per day, extra error share common to the AI models).
# Every model also shares COMMON of its error with all others: real models miss the same unpredictable weather,
# which is why measured blend gains are ~5-10 % (TASK.md), not the 30 % independent errors would give.
COMMON = 0.8
SKILL = {"hres": (1.0, 0.30, 0.0), "graphcast": (0.84, 0.29, 0.5), "pangu": (0.95, 0.31, 0.5),
         "fuxi": (1.02, 0.24, 0.5), "gencast": (1.08, 0.20, 0.5)}
BIAS = {"hres": {C.RAIN: 1.2, C.T2M: -0.4, C.WIND: 0.2, C.MSLP: 30},
        "graphcast": {C.RAIN: -2.1, C.T2M: 0.3, C.WIND: -0.3, C.MSLP: -20},
        "pangu": {C.RAIN: 0.0, C.T2M: 0.6, C.WIND: -0.5, C.MSLP: 40},
        "fuxi": {C.RAIN: -2.8, C.T2M: 0.2, C.WIND: -0.4, C.MSLP: -10},
        "gencast": {C.RAIN: -3.4, C.T2M: -0.1, C.WIND: -0.6, C.MSLP: 0}}
ERR = {C.RAIN: 6.0, C.T2M: 1.25, C.WIND: 1.3, C.MSLP: 105.0, U10: 1.3, V10: 1.3}


def where_good(model):
    """Relative error by place: HRES is better on orography, GraphCast on the plains, Pangu at sea."""
    return {"hres": 1.12 - 0.38 * ORO, "graphcast": 0.92 + 0.34 * ORO - 0.1 * SEA,
            "pangu": 1.0 - 0.22 * SEA + 0.1 * ORO, "fuxi": 1.0 + 0.12 * ORO - 0.12 * g(80, 22, 6, 5),
            "gencast": 0.95 + 0.25 * ORO}[model]


def forecasts(tr: dict, days: pd.DatetimeIndex, year: int, models, seed: int) -> dict[str, xr.Dataset]:
    inits = pd.DatetimeIndex([d for d in days if d.year == year and d.month in MONTHS])
    pos = {d: i for i, d in enumerate(days)}
    leads = C.LEAD_DAYS
    out = {}
    shape = (len(inits), len(leads), len(LAT), len(LON))
    common = {v: smooth_noise(np.random.default_rng(seed + 3), len(inits) * len(leads)).reshape(shape) for v in ERR}
    shared = {v: smooth_noise(np.random.default_rng(seed + 7), len(inits) * len(leads)).reshape(shape) for v in ERR}
    for mi, m in enumerate(models):
        rng = np.random.default_rng(seed + 100 * (mi + 1))
        a, b, share = SKILL[m]
        place = where_good(m)
        data = {}
        for v in ERR:
            if v == C.RAIN and m == "pangu":
                continue   # no precipitation, as in WeatherBench 2
            own = smooth_noise(rng, len(inits) * len(leads)).reshape(len(inits), len(leads), len(LAT), len(LON))
            own = np.sqrt(share) * shared[v] + np.sqrt(1 - share) * own if share else own
            noise = np.sqrt(COMMON) * common[v] + np.sqrt(1 - COMMON) * own
            valid = np.array([[pos[d + pd.Timedelta(days=int(L))] for L in leads] for d in inits])
            base = tr[v][valid]                                           # (init, lead, lat, lon)
            scale = ERR[v] * (a + b * (leads - 1))[None, :, None, None] * place
            if v == C.RAIN:
                scale = scale * (0.35 + base * 1000 / 30) / 1000          # rain errors grow with the rain
            f = base + BIAS[m].get(v, 0) / (1000 if v == C.RAIN else 1) + scale * noise
            if v == C.RAIN:
                smooth = {"hres": 1.0, "graphcast": 0.85, "fuxi": 0.8, "gencast": 0.72}[m]   # AI models damp peaks
                f = np.maximum(0, base.mean() + (f - base.mean()) * smooth)
            data[v] = (("init", "lead", "latitude", "longitude"), f.astype(np.float32))
        data[C.WIND] = (("init", "lead", "latitude", "longitude"),
                        np.hypot(data[U10][1], data[V10][1]).astype(np.float32))
        out[m] = xr.Dataset(data, coords={"init": inits, "lead": leads, "latitude": LAT, "longitude": LON})
    return out


def write_cache(cache: Path) -> Path:
    """Demo cache in run_all.py's layout, rain in its own tagged file as a later rain download would write it."""
    cache.mkdir(parents=True, exist_ok=True)
    all_years = CLIM + YEARS
    days = days_for(all_years)
    tr = truth(days, C.SEED)
    t = xr.Dataset({v: (("time", "latitude", "longitude"), tr[v].astype(np.float32)) for v in (C.T2M, C.WIND, C.MSLP)},
                   coords={"time": days, "latitude": LAT, "longitude": LON})
    keep = np.isin(days.year, YEARS)
    t.isel(time=np.flatnonzero(keep)).to_netcdf(truth_path(str(cache), "t2m-wind-mslp"))
    rain = np.where(SEA[None], np.nan, tr[C.RAIN])       # CHIRPS: land only
    xr.Dataset({C.RAIN: (("time", "latitude", "longitude"), rain[keep].astype(np.float32))},
               coords={"time": days[keep], "latitude": LAT, "longitude": LON}).to_netcdf(chirps_path(str(cache)))

    # regime indices from the demo truth itself, so labels match the weather on the maps
    B = C.REGIME_BOXES

    def box(v, key, how="mean"):
        la0, la1, lo0, lo1 = B[key]
        m = (LA >= la0) & (LA <= la1) & (LO >= lo0) & (LO <= lo1)
        x = tr[v][:, m]
        return x.min(1) if how == "min" else (x * np.cos(np.deg2rad(LA[m]))).sum(1) / np.cos(np.deg2rad(LA[m])).sum()

    idx = pd.DataFrame({"cmz_rain": box(C.RAIN, "cmz") * 1000, "nw_rain": box(C.RAIN, "nw") * 1000,
                        "heat_t2m": box(C.T2M, "heat"), "bay_mslp_min": box(C.MSLP, "bay", "min")}, index=days)
    idx = idx[~idx.index.duplicated()]
    idx.index.name = "date"
    idx.to_csv(cache / "regime_indices.csv")

    for y in YEARS:
        fcs = forecasts(tr, days, y, MODELS_BY_YEAR[y], C.SEED + y)
        for m, ds in fcs.items():
            no_rain = ds.drop_vars([C.RAIN], errors="ignore")
            no_rain.to_netcdf(fc_path(str(cache), m, y))
            if C.RAIN in ds:
                ds[[C.RAIN]].to_netcdf(fc_path(str(cache), m, y, "rain"))
    return cache


def write_scorecards(cache: Path, art_root: Path, sets=("S1", "S2", "S3", "S4"), n_boot: int = C.N_BOOT) -> Path:
    """artifacts/<SET>/scorecard_<SET>.csv with the real verify pipeline, as run_all.train writes them."""
    from . import verify as V
    from .cache import load_forecasts, load_truth
    from .harmonise import prepare
    from .regimes import label

    labels = label(pd.read_csv(cache / "regime_indices.csv", index_col=0, parse_dates=True), C.CLIM_YEARS)
    tr = load_truth(str(cache))
    for s in sets:
        spec = C.SETS[s]
        fcs = load_forecasts(str(cache), spec["models"], spec["years"])
        mode = "loyo" if len(spec["years"]) > 1 else "months"
        cards = []
        for var in spec["vars"]:
            have = {m: ds for m, ds in fcs.items() if var in ds}
            if len(have) < 2:
                continue
            fc, obs = prepare(have, tr, var, labels)
            se, _, _ = V.run_folds(fc, obs, mode)
            cards.append(V.scorecard(se, var, s, n_boot=n_boot))
        (art_root / s).mkdir(parents=True, exist_ok=True)
        pd.concat(cards, ignore_index=True).to_csv(art_root / s / f"scorecard_{s}.csv", index=False)
    return art_root


def main(argv=None):
    ap = argparse.ArgumentParser(description="Demo bundles: generated inputs through the real pipeline")
    ap.add_argument("--out", default="bundles")
    ap.add_argument("--work", default="demo_work", help="scratch for the demo cache and artifacts (not committed)")
    ap.add_argument("--dates", nargs="+", default=DEMO_DATES)
    ap.add_argument("--n-boot", type=int, default=300)
    a = ap.parse_args(argv)
    from . import export
    t0 = time.time()
    work = Path(a.work)
    cache = write_cache(work / "cache")
    print(f"demo cache {time.time() - t0:.0f} s")
    art = write_scorecards(cache, work / "artifacts", n_boot=a.n_boot)
    print(f"scorecards {time.time() - t0:.0f} s")
    export.main(["--cache", str(cache), "--art", str(art), "--out", a.out, "--demo", "--dates", *a.dates])
    print(f"done {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
