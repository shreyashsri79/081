"""IMD heat-wave rule on the grid (blend/heatwave.py) and its use in the live run."""

import datetime

import numpy as np
import xarray as xr

from blend import heatwave as HW

P, H, K, OUT = HW.PLAINS, HW.HILLS, HW.COAST, -1


def flags(t, normal, cls):
    hw, sv = HW.daily_flags(np.array(t, float), np.array(normal, float), np.array(cls))
    return hw.tolist(), sv.tolist()


def test_plains_departure_and_actual():
    # 41 °C, 5 above normal: heat wave, not severe; 41 °C, 7 above: severe; 39 °C, 7 above: below 40, nothing
    assert flags([41, 41, 39], [36, 34, 32], [P, P, P]) == ([True, True, False], [False, True, False])
    # actual-temperature route: 45 -> heat wave, 47 -> severe, whatever the normal
    assert flags([45, 47, 44.9], [44, 46, 44], [P, P, P]) == ([True, True, False], [False, True, False])


def test_hills_and_coast():
    assert flags([31, 31, 29], [26, 24, 20], [H, H, H]) == ([True, True, False], [False, True, False])
    # coast: >= 37 °C and >= 4.5 above normal; the FAQ gives no severe level for the coast
    assert flags([38, 38, 36], [33.5, 34, 30], [K, K, K]) == ([True, False, False], [False, False, False])


def test_outside_india_and_nan():
    assert flags([50, np.nan], [30, 30], [OUT, P]) == ([False, False], [False, False])


def test_two_consecutive_days():
    cls = np.array([[P]])
    normal = np.full((3, 1, 1), 35.0)
    t = np.array([41.0, 41.0, 30.0]).reshape(1, 3, 1, 1)        # hot on Day 1 and 2, cool on Day 3
    hw, _ = HW.event_flags(t, normal, cls)
    assert hw[0, :, 0, 0].tolist() == [True, True, False]      # Day 1 judged on its own afternoon
    cool_before = np.array([[[30.0]]])
    hw, _ = HW.event_flags(t, normal, cls, cool_before, np.array([[35.0]]))
    assert hw[0, :, 0, 0].tolist() == [False, True, False]     # Day 1 needs yesterday too


def test_probability_is_weight_of_models_meeting_the_rule():
    flags_ = np.array([True, False, True]).reshape(3, 1, 1, 1)
    w = np.array([0.5, 0.3, 0.2]).reshape(3, 1, 1, 1)
    p = HW.probability(flags_, w, np.array([[True]]))
    assert np.isclose(p[0, 0, 0], 0.7)
    assert np.isnan(HW.probability(flags_, w, np.array([[False]]))[0, 0, 0])


def test_cell_class():
    lsm = np.array([[0.0, 1.0, 1.0, 1.0],
                    [1.0, 1.0, 1.0, 1.0],
                    [1.0, 1.0, 1.0, 1.0]])
    oro = np.zeros_like(lsm)
    oro[2, 3] = 2000.0
    static = xr.Dataset({"land_sea_mask": (("latitude", "longitude"), lsm),
                         "orography": (("latitude", "longitude"), oro)})
    india = np.ones_like(lsm, bool)
    india[0, 0] = False
    cls = HW.cell_class(static, india)
    assert cls[0, 0] == OUT                  # outside India
    assert cls[0, 1] == K and cls[1, 1] == K  # touching the sea cell
    assert cls[1, 3] == P and cls[2, 2] == P
    assert cls[2, 3] == H


def test_normals_follow_the_afternoon_date():
    static = xr.Dataset({"t12_normal": (("dayofyear", "latitude", "longitude"),
                                        np.arange(1, 367, dtype=float).reshape(366, 1, 1))},
                        coords={"dayofyear": np.arange(1, 367)})
    init = datetime.datetime(2026, 5, 10)                    # day of year 130
    n = HW.normals_for(static, init, [0, 1, 3])
    assert n[:, 0, 0].tolist() == [129, 130, 132]            # Day 1's afternoon is 12 UTC on the init date


def test_live_heat_events_use_yesterdays_afternoon(tmp_path):
    from blend import bundle as B
    from blend import live as L
    ny, nx = len(L.LAT), len(L.LON)
    static = xr.Dataset({
        "t12_normal": (("dayofyear", "latitude", "longitude"), np.full((366, ny, nx), 35.0)),
        "orography": (("latitude", "longitude"), np.zeros((ny, nx))),
        "land_sea_mask": (("latitude", "longitude"), np.ones((ny, nx))),
    }, coords={"dayofyear": np.arange(1, 367), "latitude": L.LAT, "longitude": L.LON})
    init = datetime.datetime(2026, 5, 10)
    grid = dict(coords={"lead": np.arange(1, 11), "latitude": L.LAT, "longitude": L.LON},
                dims=("lead", "latitude", "longitude"))
    t12 = {m: xr.DataArray(np.full((10, ny, nx), 273.15 + 41.0), **grid) for m in ("ifs", "aifs")}
    w = xr.DataArray(np.full((2, 10, ny, nx), 0.5), dims=("model", "lead", "latitude", "longitude"),
                     coords={"model": ["ifs", "aifs"], "lead": np.arange(1, 11), "latitude": L.LAT, "longitude": L.LON})

    events, arrays, used = L.heat_events(tmp_path, init, t12, w, static)
    assert used == ["ifs", "aifs"] and [e["id"] for e in events] == ["heat", "heat_severe"]
    india = np.isfinite(arrays["p_heat"][0])
    assert india.any() and np.allclose(arrays["p_heat"][:, india], 1.0)        # 41 °C, 6 above normal
    assert np.allclose(arrays["p_heat_severe"][:, india], 0.0)
    assert "own afternoon" in events[0]["note"]

    # yesterday's run kept, with a cool afternoon: today's Day 1 is no longer a heat wave
    meta = {"id": "live-20260509", "kind": "live", "init": "2026-05-09T00:00Z", "status": "ok", "models": ["ifs", "aifs"],
            "_x": {"t12Models": ["ifs", "aifs"]}}
    B.write_run(tmp_path, meta, {"t12_t2m": np.full((2, 10, ny * nx), 30.0)})
    events, arrays, _ = L.heat_events(tmp_path, init, t12, w, static)
    assert np.allclose(arrays["p_heat"][0, india], 0.0) and np.allclose(arrays["p_heat"][1, india], 1.0)
    assert "yesterday" in events[0]["note"]
