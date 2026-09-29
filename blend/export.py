"""Hindcast run bundles (BACKEND_BUILD_PLAN.md T4-T6): real forecasts, out-of-sample weights, errors and
interim extreme probabilities for one init date, written in display units for blend/server.py.

    python -m blend.export --cache out/cache --art out/artifacts --out bundles --auto
    python -m blend.export --cache out/cache --art out/artifacts --out bundles --dates 2020-07-15 2022-04-28

Uses only the existing blend/ science functions; nothing here changes how weights or scores are computed.
"""

import os

import numpy as np
import pandas as pd
import xarray as xr

from . import config as C
from . import verify as V
from .cache import fc_path, load_forecasts, load_truth
from .harmonise import prepare
from .regimes import all_keys
from .skill import apply_bias, fit_mse

# UI variable id -> WB2 name
VAR_IDS = {"rain": C.RAIN, "t2m": C.T2M, "wind": C.WIND, "mslp": C.MSLP}
UI_OF = {v: k for k, v in VAR_IDS.items()}

# set per UI variable (plan §5.2)
SETS_2020 = {"t2m": "S3", "wind": "S3", "mslp": "S3", "rain": "S4"}
SETS_LOYO = {"t2m": "S1", "wind": "S1", "mslp": "S1", "rain": "S2"}


def mode_of(set_name: str) -> str:
    """Validation mode exactly as run_all.train() picks it."""
    return "loyo" if len(C.SETS[set_name]["years"]) > 1 else "months"


def sets_for(year: int, cache: str) -> dict[str, str]:
    """{ui var: set}. 2020 uses the five-model sets S3/S4 when every one of their cache files exists,
    otherwise (and for 2018 / 2022) the three-year sets S1/S2."""
    if year not in C.SETS["S1"]["years"]:
        raise ValueError(f"{year}: no model set covers this year (S1/S2 years: {C.SETS['S1']['years']})")
    if year == 2020:
        need = {m for s in ("S3", "S4") for m in C.SETS[s]["models"]}
        if all(os.path.exists(fc_path(cache, m, 2020)) for m in need):
            return dict(SETS_2020)
    return dict(SETS_LOYO)


def fold_for(init: xr.DataArray, date, mode: str) -> tuple[str, np.ndarray, np.ndarray]:
    """The verify.make_folds fold whose test inits contain `date`."""
    d = np.datetime64(pd.Timestamp(date).normalize(), "ns")
    pos = np.flatnonzero(init.values.astype("datetime64[ns]") == d)
    if not len(pos):
        raise KeyError(f"{pd.Timestamp(date).date()} is not an init in this data")
    for name, train, test in V.make_folds(init, mode):
        if test[pos[0]]:
            return name, np.asarray(train), np.asarray(test)
    raise KeyError(f"no fold holds {pd.Timestamp(date).date()} out")


def fit_for_date(fc: xr.DataArray, obs: xr.DataArray, date, mode: str) -> dict:
    """verify.fit on the training inits of the fold that holds `date` out, plus the MSE tables behind the
    weights and the training case counts (for the cell inspector).

    The MSE tables repeat the fit_mse calls verify.fit makes internally, because fit returns weights only."""
    name, train, _ = fold_for(fc.init, date, mode)
    tr = np.flatnonzero(train)
    if not len(tr):
        raise ValueError(f"fold {name}: no training inits")
    fc_tr, obs_tr = fc.isel(init=tr), obs.isel(init=tr)
    p = V.fit(fc_tr, obs_tr)
    fc_bc = apply_bias(fc_tr, p["bias"])
    p["mse_B2"] = fit_mse(fc_bc, obs_tr, "all")
    p["mse_B3s"] = fit_mse(fc_bc, obs_tr, "season")
    if "regime_key" in fc.coords:
        p["mse_B3"] = fit_mse(fc_bc, obs_tr, "regime", keys=all_keys())
        p["n_regime"] = {str(k): int(v) for k, v in pd.Series(fc_tr.regime_key.values).value_counts().items()}
    p["n_season"] = {str(k): int(v) for k, v in pd.Series(fc_tr.season.values).value_counts().items()}
    p["fold"] = name
    p["n_train"] = int(len(tr))
    return p
