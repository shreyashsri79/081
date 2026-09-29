"""Live regime label (blend/live_regime.py): same rules and climatology as the hindcasts, live proxies."""

import datetime

import numpy as np
import pandas as pd

from blend import bundle as B
from blend import config as C
from blend import live_regime as LR

LAT = np.arange(6.0, 39.01, 1.5)
LON = np.arange(66.0, 99.01, 1.5)


def fake_clim(seed=C.SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range(f"{C.CLIM_YEARS[0]}-01-01", f"{C.CLIM_YEARS[1]}-12-31", freq="D", name="date")
    n = len(days)
    return pd.DataFrame({"cmz_rain": 8 + 3 * rng.standard_normal(n), "nw_rain": 2 + rng.standard_normal(n),
                         "heat_t2m": 305 + 2 * rng.standard_normal(n), "bay_mslp_min": 99800 + 300 * rng.standard_normal(n)},
                        index=days)


def today(d, **vals) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(d) - pd.Timedelta(days=k) for k in (2, 1, 0)], name="date")
    df = pd.DataFrame({c: [np.nan] * 3 for c in LR.COLS}, index=idx)
    for c, v in vals.items():
        df[c] = v
    return df


def test_no_climatology_gives_normal_with_everything_missing():
    regime, z, missing = LR.live_label(None, today("2026-07-20"))
    assert regime == "normal" and z == {} and missing == LR.COLS


def test_depression_from_a_deep_bay_low():
    regime, z, missing = LR.live_label(fake_clim(), today("2026-07-20", cmz_rain=8.0, bay_mslp_min=98500.0))
    assert regime == "depression" and z["bay_mslp_min"] < -1.5
    assert "heat_t2m" in missing


def test_active_needs_three_wet_days_and_break_three_dry():
    clim = fake_clim()
    assert LR.live_label(clim, today("2026-07-20", cmz_rain=[20.0, 20.0, 20.0], bay_mslp_min=99800.0))[0] == "active"
    assert LR.live_label(clim, today("2026-07-20", cmz_rain=[0.0, 0.0, 0.0], bay_mslp_min=99800.0))[0] == "break"
    # one missing day: the three-day rule cannot fire, and the gap is reported
    regime, _, missing = LR.live_label(clim, today("2026-07-20", cmz_rain=[np.nan, 20.0, 20.0], bay_mslp_min=99800.0))
    assert regime == "normal" and "cmz_rain (3 days)" in missing


def test_heat_outside_the_monsoon():
    regime, _, _ = LR.live_label(fake_clim(), today("2026-05-10", heat_t2m=320.0))
    assert regime == "heat"


def test_live_indices_read_yesterdays_runs(tmp_path):
    ny, nx = len(LAT), len(LON)
    init = datetime.datetime(2026, 7, 20)
    for back in (1, 2, 3):
        d = init - datetime.timedelta(days=back)
        rain = np.full((10, ny * nx), float(back))                     # run d-1 -> 1 mm, d-2 -> 2 mm, d-3 -> 3 mm
        t12 = np.full((2, 10, ny * nx), 30.0)
        meta = {"id": f"live-{d:%Y%m%d}", "kind": "live", "init": f"{d:%Y-%m-%d}T00:00Z", "status": "ok",
                "models": ["ifs", "aifs"], "leads": list(range(1, 11))}
        B.write_run(tmp_path, meta, {"blend_rain": rain, "t12_t2m": t12})
    mslp = np.full((ny, nx), 100500.0)
    mslp[LAT.tolist().index(21.0), LON.tolist().index(87.0)] = 99000.0     # inside the Bay box
    df = LR.live_indices(tmp_path, init, LAT, LON, mslp)
    assert np.allclose(df["cmz_rain"], [3.0, 2.0, 1.0])                   # d-2, d-1, d
    assert np.allclose(df["heat_t2m"], 303.15)
    assert np.isnan(df["bay_mslp_min"].iloc[0]) and df["bay_mslp_min"].iloc[-1] == 99000.0
