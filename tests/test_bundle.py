"""Bundles are atomic, pickle-free, and indexed (plan T3)."""

import json

import numpy as np

from blend import bundle as B


def _meta(run_id="hindcast-20200715", kind="hindcast", init="2020-07-15T00:00Z"):
    return {"id": run_id, "kind": kind, "init": init, "status": "ok", "models": ["hres", "graphcast"],
            "note_nan": float("nan"), "_x": {"k": 20}}


def test_round_trip(tmp_path):
    arrays = {"blend_t2m": np.arange(20, dtype=np.float64).reshape(2, 10), "w_t2m": np.full((2, 2, 10), 0.5)}
    B.write_run(tmp_path, _meta(), arrays)
    got = B.read_arrays(tmp_path, "hindcast-20200715")
    assert set(got) == set(arrays)
    for k in arrays:
        assert got[k].dtype == np.float32
        np.testing.assert_allclose(got[k], arrays[k])
    meta = B.read_meta(tmp_path, "hindcast-20200715")
    assert meta["note_nan"] is None          # NaN never reaches JSON
    assert meta["_x"] == {"k": 20}


def test_npz_is_pickle_free(tmp_path):
    B.write_run(tmp_path, _meta(), {"a": np.zeros(3)})
    with np.load(tmp_path / "runs" / "hindcast-20200715" / "arrays.npz", allow_pickle=False) as z:
        assert z["a"].shape == (3,)


def test_index_orders_live_first(tmp_path):
    B.write_run(tmp_path, _meta("hindcast-20220428", init="2022-04-28T00:00Z"), {"a": np.zeros(1)})
    B.write_run(tmp_path, _meta("hindcast-20200715"), {"a": np.zeros(1)})
    B.write_run(tmp_path, _meta("live-20261001", "live", "2026-10-01T00:00Z"), {"a": np.zeros(1)})
    B.write_run(tmp_path, _meta("live-20261002", "live", "2026-10-02T00:00Z"), {"a": np.zeros(1)})
    idx = B.write_index(tmp_path)
    assert [r["id"] for r in idx["runs"]] == ["live-20261002", "live-20261001", "hindcast-20200715", "hindcast-20220428"]
    assert set(idx["runs"][0]) == set(B.SUMMARY_KEYS)
    assert json.loads((tmp_path / "index.json").read_text())["contractVersion"] == idx["contractVersion"]


def test_half_written_run_is_ignored(tmp_path):
    B.write_run(tmp_path, _meta(), {"a": np.zeros(1)})
    # simulate a crash mid-write of another run: only its .tmp directory exists
    (tmp_path / "runs" / "hindcast-20200716.tmp").mkdir()
    (tmp_path / "runs" / "hindcast-20200716.tmp" / "meta.json").write_text("{}")
    assert B.list_runs(tmp_path) == ["hindcast-20200715"]
    assert [r["id"] for r in B.write_index(tmp_path)["runs"]] == ["hindcast-20200715"]


def test_rewrite_replaces_run(tmp_path):
    B.write_run(tmp_path, _meta(), {"a": np.zeros(1), "old": np.zeros(1)})
    B.write_run(tmp_path, _meta(), {"a": np.ones(1)})
    got = B.read_arrays(tmp_path, "hindcast-20200715")
    assert set(got) == {"a"} and got["a"][0] == 1


def test_scorecard_round_trip(tmp_path):
    card = {"validation": "x", "rows": [{"delta": float("nan")}], "regions": []}
    B.write_scorecard(tmp_path, "S1", card)
    assert B.read_scorecard(tmp_path, "S1")["rows"][0]["delta"] is None
