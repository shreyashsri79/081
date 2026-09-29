"""C9 products (blend/deliver.py) and their API endpoints."""

import csv
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from blend import bundle as B
from blend import deliver as D
from blend.server import create_app

RUN = "hindcast-20200715"


@pytest.fixture(scope="module")
def client(bundle_root):
    return TestClient(create_app(bundle_root))


def test_geojson_all_leads(bundle_root):
    meta, arr = B.read_meta(bundle_root, RUN), B.read_arrays(bundle_root, RUN)
    gj = D.geojson(meta, arr)
    g = meta["grid"]
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == g["ny"] * g["nx"]
    f = gj["features"][0]
    ring = f["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    assert abs((ring[1][0] - ring[0][0]) - g["step"]) < 1e-9
    v = meta["vars"][0]
    for lead in meta["leads"]:
        assert f"{v}_d{lead}" in f["properties"] and f"dominant_{v}_d{lead}" in f["properties"]
    x, p = float(arr[f"blend_{v}"][0, 0]), f["properties"][f"{v}_d1"]
    assert (p is None) == (not np.isfinite(x))                              # masked cell -> null, never 0
    if p is not None:
        assert p == pytest.approx(x, abs=1e-3)


def test_geojson_one_lead_and_state_names(bundle_root):
    meta, arr = B.read_meta(bundle_root, RUN), B.read_arrays(bundle_root, RUN)
    gj = D.geojson(meta, arr, lead=3)
    keys = {k for f in gj["features"] for k in f["properties"]}
    assert not any(k.endswith("_d1") for k in keys) and any(k.endswith("_d3") for k in keys)
    assert any(f["properties"]["state"] for f in gj["features"])          # tiny grid covers part of India


def test_states_csv(bundle_root):
    meta, arr = B.read_meta(bundle_root, RUN), B.read_arrays(bundle_root, RUN)
    rows = list(csv.DictReader(io.StringIO(D.states_csv(meta, arr))))
    assert rows and {r["kind"] for r in rows} <= {"variable", "event"}
    r = next(r for r in rows if r["kind"] == "variable")
    assert float(r["min"]) <= float(r["mean"]) <= float(r["max"]) and int(r["cells"]) >= 1
    assert {r["run"] for r in rows} == {RUN}


def test_netcdf_round_trip(bundle_root, tmp_path):
    xr = pytest.importorskip("xarray")
    path = D.to_netcdf(bundle_root, RUN, tmp_path)
    ds = xr.load_dataset(path)
    meta, arr = B.read_meta(bundle_root, RUN), B.read_arrays(bundle_root, RUN)
    v = meta["vars"][0]
    g = meta["grid"]
    assert ds[f"blend_{v}"].shape == (len(meta["leads"]), g["ny"], g["nx"])
    assert np.allclose(ds[f"blend_{v}"].values.reshape(len(meta["leads"]), -1), arr[f"blend_{v}"], equal_nan=True)
    assert list(ds[f"model_{v}"].values) == meta["modelsByVar"][v]


def test_export_endpoints(client):
    r = client.get(f"/api/export/geojson?run={RUN}&lead=2")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    assert "attachment" in r.headers["content-disposition"] and r.json()["properties"]["leads"] == [2]
    r = client.get(f"/api/export/csv?run={RUN}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("run,state,kind")
    assert client.get(f"/api/export/geojson?run={RUN}&lead=99").status_code == 404
    assert client.get("/api/export/csv?run=nope").status_code == 404
