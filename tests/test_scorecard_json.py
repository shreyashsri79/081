"""Scorecard in dashboard shape: units, rung rule, honest regions (plan T5)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).parent))
from conftest import make_forecast, make_regime_indices, make_truth  # noqa: E402

from blend import config as C  # noqa: E402
from blend.export import choose_rung, region_scores, scorecard_json  # noqa: E402
from blend.geo import india_mask, state_rollup, state_index  # noqa: E402
from blend.harmonise import prepare  # noqa: E402
from blend.regimes import label  # noqa: E402


def _rows(var, lead, rmse, verdict="beats", d=-0.1):
    out = []
    for m, r in rmse.items():
        out.append({"set": "S1", "var": var, "lead_day": lead, "rung": f"m:{m}", "rmse": r})
    for rung in ["B0", "B0bc"]:
        out.append({"set": "S1", "var": var, "lead_day": lead, "rung": rung, "rmse": min(rmse.values())})
    for rung, r in {"B1": 0.95, "B2": 0.9, "B2raw": 0.93, "B3s": 0.89, "B3": 0.88}.items():
        v = min(rmse.values()) * r
        out.append({"set": "S1", "var": var, "lead_day": lead, "rung": rung, "rmse": v,
                    "d_vs_B0": d, "lo_vs_B0": d - 0.05, "hi_vs_B0": d + 0.05,
                    "d_vs_B0bc": d, "lo_vs_B0bc": d - 0.05, "hi_vs_B0bc": d + 0.05,
                    "verdict_vs_B0bc": verdict, "verdict_vs_B0": verdict})
    return out


def _card():
    rows = []
    for lead in range(1, 11):
        rows += _rows(C.T2M, lead, {"hres": 1.0, "graphcast": 0.8, "pangu": 1.2})
        rows += _rows(C.MSLP, lead, {"hres": 150.0, "graphcast": 120.0, "pangu": 200.0}, d=-10.0)
    return pd.DataFrame(rows)


def test_choose_rung_prefers_b3_when_it_is_not_worse():
    rung, why = choose_rung(_card(), C.T2M)
    assert rung == "B3" and "10/10" in why


def test_choose_rung_falls_back_when_worse():
    card = _card()
    card.loc[(card["var"] == C.T2M) & card.rung.isin(["B3", "B3s", "B2"]), "verdict_vs_B0bc"] = "worse"
    assert choose_rung(card, C.T2M)[0] == "B1"


def test_scorecard_json_units_best_delta():
    out = scorecard_json("S1", _card(), {"t2m": "B3", "mslp": "B3"}, [])
    assert out["validation"].startswith("Leave-one-year-out 2018 / 2020 / 2022")
    assert len(out["rows"]) == 20
    t = next(r for r in out["rows"] if r["var"] == "t2m" and r["lead"] == 3)
    assert t["best"] == "graphcast"
    assert np.isclose(t["rmse"]["blend"], 0.8 * 0.88) and np.isclose(t["delta"], -0.1)
    assert np.allclose(t["ci"], [-0.15, -0.05])
    p = next(r for r in out["rows"] if r["var"] == "mslp" and r["lead"] == 3)
    assert np.isclose(p["rmse"]["graphcast"], 1.2)          # Pa -> hPa
    assert np.isclose(p["delta"], -0.1) and np.allclose(p["ci"], [-0.1005, -0.0995])  # ±0.05 Pa -> hPa


def test_region_scores_drop_empty_regions():
    labels = label(make_regime_indices(), C.CLIM_YEARS)
    years = [2018, 2020, 2022]
    truth = make_truth(years)
    fcs = {m: xr.concat([make_forecast(truth, m, y) for y in years], "init") for m in ("hres", "graphcast", "pangu")}
    fc, obs = prepare(fcs, truth, C.T2M, labels)
    regs = region_scores(fc, obs, "loyo", "B3", "t2m")
    names = {r["name"] for r in regs}
    assert "North-east" not in names and "North-west" not in names     # no cells of the tiny grid there
    assert "South peninsula" in names
    for r in regs:
        assert r["ci"][0] <= r["delta"] <= r["ci"][1]


def test_geo_state_rollup():
    lat, lon = np.array([6.0, 7.5, 9.0, 10.5, 12.0]), np.array([72.0, 73.5, 75.0, 76.5, 78.0])
    idx = state_index(lat, lon)
    assert (idx >= 0).any() and (idx < 0).any()                          # Kerala / TN land and Arabian Sea
    assert india_mask(lat, lon).shape == (5, 5)
    prob = np.where(idx >= 0, 0.4, np.nan)
    roll = state_rollup(prob, idx)
    assert roll and all(r["cells"] > 0 and r["pmax"] == 0.4 for r in roll)
