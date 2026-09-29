"""One hindcast bundle end to end: real formula, display units, notes (plan T6)."""

import numpy as np
import pytest

from blend import api_models as A
from blend import bundle as B
from blend import config as C
from blend import export as E

RUN = "hindcast-20200715"


@pytest.fixture(scope="module")
def run(bundle_root):
    return B.read_meta(bundle_root, RUN), B.read_arrays(bundle_root, RUN)


def test_meta_validates_as_run(run):
    meta, _ = run
    r = A.Run.model_validate({k: v for k, v in meta.items() if k != "_x"})
    assert r.provenance == "measured" and r.kind == "hindcast"
    assert r.models_by_var["rain"] == ["hres", "graphcast"]           # Pangu never votes on rain
    assert r.models_by_var["t2m"] == ["hres", "graphcast", "pangu"]
    assert r.grid.ny == 5 and r.grid.nx == 5 and r.grid.step == 1.5
    assert r.regime.basis == "init"
    assert meta["_x"]["sets"] == {"rain": "S2", "t2m": "S1", "wind": "S1", "mslp": "S1"}   # FuXi/GenCast not cached


def test_array_shapes(run):
    meta, a = run
    n = meta["grid"]["ny"] * meta["grid"]["nx"]
    for ui, models in meta["modelsByVar"].items():
        m = len(models)
        for name in ("fc", "w", "mse", "bias"):
            assert a[f"{name}_{ui}"].shape == (m, 10, n), name
        for name in ("blend", "obs"):
            assert a[f"{name}_{ui}"].shape == (10, n), name
    for ex in ("rain64", "rain115", "rain204", "wind15"):
        assert a[f"p_{ex}"].shape == (10, n)
    assert "p_heat" not in a


def test_weights_sum_to_one(run):
    _, a = run
    for ui in ("rain", "t2m", "wind", "mslp"):
        s = a[f"w_{ui}"].sum(0)
        ok = np.isfinite(s)
        assert ok.any()
        np.testing.assert_allclose(s[ok], 1.0, atol=1e-5)


def test_display_units(run):
    _, a = run
    t = a["blend_t2m"][np.isfinite(a["blend_t2m"])]
    p = a["blend_mslp"][np.isfinite(a["blend_mslp"])]
    assert (t > -60).all() and (t < 60).all()           # °C, not K
    assert (p > 850).all() and (p < 1100).all()         # hPa, not Pa
    r = a["blend_rain"][np.isfinite(a["blend_rain"])]
    assert r.max() < 500                                # mm once, not ×1000 twice


def test_blend_is_weighted_bias_corrected_mean(run):
    _, a = run
    rng = np.random.default_rng(0)
    for ui in ("t2m", "mslp", "rain"):
        lead, k = int(rng.integers(10)), int(rng.integers(25))
        fc, w, bias = a[f"fc_{ui}"][:, lead, k], a[f"w_{ui}"][:, lead, k], a[f"bias_{ui}"][:, lead, k]
        corrected = np.maximum(fc - bias, 0) if ui == "rain" else fc - bias    # skill.apply_bias keeps rain >= 0
        np.testing.assert_allclose((w * corrected).sum(), a[f"blend_{ui}"][lead, k], rtol=1e-4, atol=1e-3)


def test_extremes_are_probabilities(run):
    _, a = run
    for ex in ("rain64", "wind15"):
        v = a[f"p_{ex}"][np.isfinite(a[f"p_{ex}"])]
        assert ((v >= 0) & (v <= 1)).all()


def test_notes(run):
    meta, _ = run
    text = " ".join(meta["notes"])
    assert "ERA5" in text and "out-of-sample" in text and "year 2020" in text
    assert E.HEAT_NOTE in meta["notes"]
    assert "Rung per variable" in text


def test_index_and_scorecards(bundle_root):
    idx = B.read_index(bundle_root)
    assert [r["id"] for r in idx["runs"]] == [RUN]
    for s in ("S1", "S2"):
        card = A.Scorecard.model_validate(B.read_scorecard(bundle_root, s))
        assert card.rows and card.validation.startswith("Leave-one-year-out")


def test_unknown_date_is_skipped(tmp_path, fake_cache, capsys):
    E.main(["--cache", str(fake_cache), "--out", str(tmp_path / "b"), "--dates", "2020-12-25"])
    assert "skip 2020-12-25" in capsys.readouterr().out
    assert B.read_index(tmp_path / "b")["runs"] == []


def test_no_scorecard_defaults_to_b2(tmp_path, fake_cache):
    ctx = E.Context(str(fake_cache), None)
    E.build_run(ctx, "2018-07-10", tmp_path)
    meta = B.read_meta(tmp_path, "hindcast-20180710")
    assert set(meta["_x"]["rungs"].values()) == {"B2"}
    assert meta["_x"]["folds"]["t2m"] == "year 2018"


def test_auto_dates_start_with_default_run(fake_cache):
    ctx = E.Context(str(fake_cache), None)
    dates = E.auto_dates(ctx)
    assert dates[0].strftime("%Y-%m-%d") == "2020-07-15"
    assert len(dates) == len(set(dates)) and len(dates) <= 12
    assert all(d.year in C.SETS["S1"]["years"] for d in dates)
