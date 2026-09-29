"""Out-of-sample fit for one date: the date's fold never trains its weights (plan T4)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import make_forecast, make_truth  # noqa: E402

from blend import config as C  # noqa: E402
from blend.export import fit_for_date, fold_for, sets_for  # noqa: E402
from blend.harmonise import prepare  # noqa: E402
from blend.regimes import label  # noqa: E402
from conftest import make_regime_indices  # noqa: E402

LABELS = label(make_regime_indices(), C.CLIM_YEARS)


def _fc_obs(years, months=(7,), days=20, var=C.T2M, models=("hres", "graphcast", "pangu")):
    truth = make_truth(years, months, days)
    fcs = {m: __import__("xarray").concat([make_forecast(truth, m, y, months, days) for y in years], "init")
           for m in models}
    return prepare(fcs, truth, var, LABELS)


def test_loyo_fold_excludes_the_whole_year():
    fc, _ = _fc_obs([2018, 2020, 2022])
    name, train, test = fold_for(fc.init, "2020-07-05", "loyo")
    years = pd.DatetimeIndex(fc.init.values).year
    assert name == "2020"
    assert not (years[train] == 2020).any()
    assert (years[test] == 2020).all()


def test_weights_sum_to_one_and_favour_best_model():
    fc, obs = _fc_obs([2018, 2020, 2022])
    p = fit_for_date(fc, obs, "2020-07-05", "loyo")
    for key in ("w_B2", "w_B3s", "w_B3"):
        s = p[key].sum("model")
        ok = np.isfinite(s.values)
        np.testing.assert_allclose(s.values[ok], 1.0, atol=1e-6)
    mean_w = p["w_B2"].mean(["lead", "latitude", "longitude"]).to_series()
    assert mean_w.idxmax() == "graphcast"          # smallest noise in the fixture
    assert p["fold"] == "2020" and p["n_train"] == 40
    assert sum(p["n_season"].values()) == 40
    assert set(p) >= {"mse_B2", "mse_B3s", "mse_B3", "n_regime", "bias"}


def test_months_fold_drops_the_gap():
    fc, obs = _fc_obs([2020], months=(6, 7, 8), days=28)
    name, train, test = fold_for(fc.init, "2020-07-10", "months")
    t = pd.DatetimeIndex(fc.init.values)
    assert name == "m07"
    lo, hi = t[test].min() - pd.Timedelta(days=10), t[test].max() + pd.Timedelta(days=10)
    assert not ((t[train] >= lo) & (t[train] <= hi)).any()
    assert train.sum() > 0


def test_unknown_date_raises():
    fc, _ = _fc_obs([2018, 2020, 2022])
    with pytest.raises(KeyError):
        fold_for(fc.init, "2019-07-05", "loyo")


def test_sets_for(tmp_path):
    assert sets_for(2018, str(tmp_path)) == {"t2m": "S1", "wind": "S1", "mslp": "S1", "rain": "S2"}
    assert sets_for(2020, str(tmp_path))["rain"] == "S2"          # FuXi / GenCast not cached -> fall back
    for m in ("hres", "graphcast", "pangu", "fuxi", "gencast"):
        (tmp_path / f"fc_{m}_2020.nc").write_text("")
    assert sets_for(2020, str(tmp_path)) == {"t2m": "S3", "wind": "S3", "mslp": "S3", "rain": "S4"}
    with pytest.raises(ValueError):
        sets_for(2019, str(tmp_path))
