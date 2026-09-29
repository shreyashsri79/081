"""Every endpoint validates against the contract; errors are 404 JSON; no NaN on the wire (plan T8)."""

import pytest
from fastapi.testclient import TestClient

from blend import api_models as A
from blend.server import create_app

RUN = "hindcast-20200715"


@pytest.fixture(scope="module")
def client(bundle_root):
    return TestClient(create_app(bundle_root))


def get(client, url, model=None, status=200):
    r = client.get(url)
    assert r.status_code == status, (url, r.status_code, r.text[:300])
    assert r.headers["content-type"].startswith("application/json")
    assert "NaN" not in r.text and "Infinity" not in r.text
    if model is not None:
        return model.model_validate(r.json())
    return r.json()


def test_health_and_runs(client):
    h = get(client, "/api/health", A.Health)
    assert h.runs == 1 and h.provenance == "measured" and h.contract_version == A.CONTRACT_VERSION
    runs = get(client, "/api/runs")
    assert [A.RunSummary.model_validate(r).id for r in runs] == [RUN]


def test_run(client):
    r = get(client, f"/api/runs/{RUN}", A.Run)
    assert r.provenance == "measured" and r.notes
    assert "_x" not in client.get(f"/api/runs/{RUN}").json()


@pytest.mark.parametrize("var", ["rain", "t2m", "wind", "mslp"])
def test_field_blend_and_member(client, var):
    f = get(client, f"/api/field?run={RUN}&var={var}&lead=3", A.Field)
    assert len(f.values) == 25 and f.units
    m = get(client, f"/api/field?run={RUN}&var={var}&lead=3&model=hres", A.Field)
    assert m.values != f.values


def test_weights(client):
    w = get(client, f"/api/weights?run={RUN}&var=rain&lead=5", A.WeightSet)
    assert w.models == ["hres", "graphcast"] and len(w.weights) == 2 and len(w.dominant) == 25
    for k in range(25):
        col = [row[k] for row in w.weights]
        if all(c is not None for c in col):
            assert abs(sum(col) - 1) < 1e-3
            assert w.dominant[k] == col.index(max(col))


def test_scorecard(client):
    s = get(client, f"/api/scorecard?run={RUN}", A.Scorecard)
    assert {r.var for r in s.rows} == {"rain", "t2m", "wind", "mslp"}
    assert len([r for r in s.rows if r.var == "t2m"]) == 10          # t2m rows from S1 only, not also from S2
    assert "Leave-one-year-out" in s.validation


def test_extremes(client):
    x = get(client, f"/api/extremes?run={RUN}&type=rain_p95&lead=2", A.ExtremeMap)
    assert x.available and x.calibrated is True and "calibrated" in x.method and len(x.prob) == 25
    assert "95th percentile" in x.threshold
    assert all(s.cells > 0 for s in x.states)
    heat = get(client, f"/api/extremes?run={RUN}&type=heat&lead=2", A.ExtremeMap)
    assert heat.available is False and "12 UTC" in heat.note and heat.states == []


def test_cell_and_meteogram(client):
    c = get(client, f"/api/cell?run={RUN}&var=t2m&lead=4&i=2&j=3", A.CellReport)
    assert [m.model for m in c.members] == ["hres", "graphcast", "pangu"]
    assert len(c.mse_by_lead[0].mse) == 10 and c.k == 20 and c.n_season > 0
    assert c.lat == 9.0 and c.lon == 76.5
    mg = get(client, f"/api/meteogram?run={RUN}&i=2&j=3", A.Meteogram)
    assert [v.var for v in mg.vars] == ["rain", "t2m", "wind", "mslp"]
    assert all(len(v.blend) == 10 for v in mg.vars)


@pytest.mark.parametrize("url", [
    "/api/runs/hindcast-19990101",
    f"/api/field?run=nope&var=t2m&lead=1",
    f"/api/field?run={RUN}&var=snow&lead=1",
    f"/api/field?run={RUN}&var=t2m&lead=11",
    f"/api/field?run={RUN}&var=rain&lead=1&model=pangu",
    f"/api/cell?run={RUN}&var=t2m&lead=1&i=9&j=0",
    f"/api/meteogram?run={RUN}&i=0&j=-1",
    f"/api/extremes?run={RUN}&type=hail&lead=1",
    f"/api/extremes?run={RUN}&type=rain64&lead=1",
    "/api/nothing-here",
])
def test_404s(client, url):
    body = get(client, url, status=404)
    assert body["detail"]


def test_empty_bundle_dir(tmp_path):
    c = TestClient(create_app(tmp_path))
    assert c.get("/api/runs").json() == []
    assert c.get("/api/health").json()["provenance"] == "synthetic"


def test_serves_built_dashboard(tmp_path, bundle_root):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "a.js").write_text("js")
    c = TestClient(create_app(bundle_root, tmp_path))
    assert c.get("/forecast").text == "<html>app</html>"          # SPA fallback
    assert c.get("/assets/a.js").text == "js"
    assert c.get("/api/health").json()["status"] == "ok"
    assert c.get("/api/unknown").status_code == 404


def test_cors_allows_browser_reads(client):
    r = client.get("/api/health", headers={"Origin": "https://example.org"})
    assert r.headers["access-control-allow-origin"] == "*"
    pre = client.options("/api/runs", headers={"Origin": "https://example.org", "Access-Control-Request-Method": "GET"})
    assert pre.status_code == 200 and "GET" in pre.headers["access-control-allow-methods"]
    bad = client.options("/api/runs", headers={"Origin": "https://example.org", "Access-Control-Request-Method": "POST"})
    assert bad.status_code == 400
