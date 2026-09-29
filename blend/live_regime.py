"""Weather-regime label for the live run (C4 on live data).

The label is the one blend/regimes.py gives the hindcasts: the same four indices, standardised against the same
2003-2017 ERA5 day-of-year climatology, the same rules. Only the source of today's indices differs:

  index          hindcast (ERA5)                          live proxy
  cmz_rain       Core Monsoon Zone rain, 24 h to 00 UTC d  blended Day-1 rain of the run started on d-1
  nw_rain        north-west India rain, same window        same, north-west box
  heat_t2m       mean 12 UTC 2 m temperature on d-1        mean over models of the d-1 run's Day-1 afternoon
  bay_mslp_min   lowest 00 UTC pressure over the Bay, d    today's IFS analysis

Active / break need the Core Monsoon Zone index on d, d-1 and d-2, so they appear once three earlier live runs are
kept. The live weights do not depend on the label (regime weights gave no held-out gain); it is shown and logged.

    python -m blend.live_regime build-clim     # once: models/live_regime.nc from ERA5 (needs zarr + gcsfs)
"""

import argparse
import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import bundle as B
from . import config as C
from .regimes import label

ROOT = Path(__file__).resolve().parent.parent
CLIM_FILE = ROOT / "models" / "live_regime.nc"
COLS = ["cmz_rain", "nw_rain", "heat_t2m", "bay_mslp_min"]


def build_clim(out: Path = CLIM_FILE, workers: int = 32) -> Path:
    """Daily regime indices over the climatology years, downloaded from ERA5 with regimes.download_indices."""
    from .regimes import download_indices
    y0, y1 = C.CLIM_YEARS
    df = download_indices(f"{y0}-01-01", f"{y1}-12-31", workers=workers)
    df = df[(df.index.year >= y0) & (df.index.year <= y1)]
    ds = xr.Dataset({c: ("date", df[c].values.astype("float64")) for c in COLS}, coords={"date": df.index.values})
    ds.attrs = {"source": "ERA5 via blend.regimes.download_indices", "years": f"{y0}-{y1}",
                "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    out.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(out)
    return out


def load_clim(path: Path = CLIM_FILE) -> pd.DataFrame | None:
    if not Path(path).exists():
        return None
    ds = xr.load_dataset(path)
    return pd.DataFrame({c: ds[c].values for c in COLS}, index=pd.DatetimeIndex(ds["date"].values, name="date"))


def _box_mean(field: np.ndarray, lat: np.ndarray, lon: np.ndarray, box, how="mean") -> float:
    """(lat, lon) field -> box mean (cos-latitude weighted) or minimum, like regimes._box_series."""
    lat0, lat1, lon0, lon1 = box
    i = (lat >= lat0) & (lat <= lat1)
    j = (lon >= lon0) & (lon <= lon1)
    sub = field[np.ix_(i, j)]
    if how == "min":
        return float(np.nanmin(sub)) if np.isfinite(sub).any() else np.nan
    w = np.broadcast_to(np.cos(np.deg2rad(lat[i]))[:, None], sub.shape)
    ok = np.isfinite(sub)
    return float((sub[ok] * w[ok]).sum() / w[ok].sum()) if ok.any() else np.nan


def live_indices(root: Path, init: datetime.datetime, lat: np.ndarray, lon: np.ndarray,
                 analysis_mslp: np.ndarray | None, today_arrays: dict | None = None) -> pd.DataFrame:
    """Indices for init and the two days before, from kept live bundles and today's analysis (NaN where missing)."""
    Bx = C.REGIME_BOXES
    runs = set(B.list_runs(root))
    rows = {}
    for back in (2, 1, 0):
        d = init - datetime.timedelta(days=back)
        row = dict.fromkeys(COLS, np.nan)
        prev = f"live-{d - datetime.timedelta(days=1):%Y%m%d}"         # the run whose Day 1 ends at 00 UTC on d
        if prev in runs:
            arr, meta = B.read_arrays(root, prev), B.read_meta(root, prev)
            li = meta["leads"].index(1)
            if "blend_rain" in arr:
                rain = arr["blend_rain"][li].reshape(len(lat), len(lon))
                row["cmz_rain"] = _box_mean(rain, lat, lon, Bx["cmz"])
                row["nw_rain"] = _box_mean(rain, lat, lon, Bx["nw"])
            if "t12_t2m" in arr:                                          # Day-1 afternoon = 12 UTC on d-1
                t = np.nanmean(arr["t12_t2m"][:, li], axis=0).reshape(len(lat), len(lon)) + 273.15
                row["heat_t2m"] = _box_mean(t, lat, lon, Bx["heat"])
        if back == 0 and analysis_mslp is not None:
            row["bay_mslp_min"] = _box_mean(analysis_mslp, lat, lon, Bx["bay"], how="min")
        rows[pd.Timestamp(d.date())] = row
    df = pd.DataFrame.from_dict(rows, orient="index")[COLS]
    df.index.name = "date"
    return df


def live_label(clim: pd.DataFrame | None, today: pd.DataFrame) -> tuple[str, dict, list[str]]:
    """(regime, z-scores of init day, missing index names). 'normal' with a reason when no climatology."""
    if clim is None:
        return "normal", {}, COLS
    lab = label(pd.concat([clim, today]).sort_index(), C.CLIM_YEARS)
    last = lab.iloc[-1]
    z = {c: (None if not np.isfinite(last[f"z_{c}"]) else round(float(last[f"z_{c}"]), 2)) for c in COLS}
    missing = [c for c in COLS if not np.isfinite(today[c].iloc[-1])]
    if today["cmz_rain"].isna().any():
        missing = sorted(set(missing) | {"cmz_rain (3 days)"})
    return str(last["regime"]), z, missing


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-clim", help="download the 2003-2017 ERA5 regime indices (needs zarr + gcsfs)")
    b.add_argument("--workers", type=int, default=32)
    a = ap.parse_args(argv)
    if a.cmd == "build-clim":
        print(build_clim(workers=a.workers))


if __name__ == "__main__":
    main()
