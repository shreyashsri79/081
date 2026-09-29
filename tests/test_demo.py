"""Demo bundles: the upstream cache layout (tagged per-variable files, CHIRPS land-only rain) through the real
exporter, marked synthetic so the dashboard labels them."""

import os

import numpy as np
import pytest

from blend import bundle as B
from blend import demo as D
from blend import export as E
from blend.cache import fc_files


@pytest.fixture(scope="module")
def demo_cache(tmp_path_factory):
    return D.write_cache(tmp_path_factory.mktemp("demo") / "cache")


def test_cache_uses_run_all_layout(demo_cache):
    files = [os.path.basename(f) for f in fc_files(str(demo_cache), "hres", 2020)]
    assert files == ["fc_hres_2020.nc", "fc_hres_2020_rain.nc"]
    assert (demo_cache / "truth_chirps.nc").exists()
    assert not any("rain" in f for f in [os.path.basename(x) for x in fc_files(str(demo_cache), "pangu", 2020)])
    assert E.sets_for(2020, str(demo_cache))["rain"] == "S4"         # five models cached for 2020


def test_demo_bundle(demo_cache, tmp_path):
    ctx = E.Context(str(demo_cache), None)
    E.build_run(ctx, "2020-07-15", tmp_path, demo=True)
    meta, a = B.read_meta(tmp_path, "hindcast-20200715"), B.read_arrays(tmp_path, "hindcast-20200715")
    assert meta["provenance"] == "synthetic" and meta["notes"][0].startswith("DEMO BUNDLE")
    assert any(n.startswith("Rain truth: CHIRPS") for n in meta["notes"])
    assert meta["modelsByVar"]["rain"] == ["hres", "graphcast", "fuxi", "gencast"]
    assert meta["grid"] == {"lat0": 6.0, "lon0": 66.0, "step": 1.5, "ny": 23, "nx": 23}
    assert a["u10"].shape == a["v10"].shape == (10, 529)              # wind particles
    rain = a["blend_rain"]
    assert np.isnan(rain).any() and np.isfinite(rain).any()           # CHIRPS: land only
    assert np.nanmin(rain) >= 0
