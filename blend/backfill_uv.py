"""Add wind components (u10, v10) to hindcast bundles exported without them, so the map can draw wind particles.

    python -m blend.backfill_uv --bundles bundles        # needs network, zarr and gcsfs (WeatherBench 2)

For each hindcast bundle lacking u10/v10: download each wind member's 10 m u and v for the bundle's init date from
the same WeatherBench 2 store, India box and Day 1-10 leads as blend/sources.py, and blend them with the bundle's own
stored wind weights, exactly as blend/export.py does (direction only, no bias correction). Nothing else in the bundle
changes except the particles note.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from . import bundle as B
from . import config as C
from .export import U10, UV_NOTE, UV_OK_NOTE, V10
from .sources import _box, _lead_index, open_store


def member_uv(model: str, date: pd.Timestamp) -> dict[str, np.ndarray]:
    """{U10: (lead, lat, lon), V10: ...} for one model and init date."""
    for url, years in C.STORES[model]:
        if date.year not in years:
            continue
        ds = open_store(url)
        if U10 not in ds or V10 not in ds:
            raise KeyError(f"{model}: no 10 m u/v in {url}")
        ds = _box(ds[[U10, V10]]).sel(time=date)
        ds = ds.isel(prediction_timedelta=_lead_index(ds.prediction_timedelta))
        return {v: ds[v].transpose("prediction_timedelta", "latitude", "longitude").values for v in (U10, V10)}
    raise KeyError(f"{model}: no store covers {date:%Y}")


def backfill_run(root: Path, run_id: str) -> bool:
    meta, arrays = B.read_meta(root, run_id), B.read_arrays(root, run_id)
    if meta["kind"] != "hindcast" or "wind" not in meta["vars"] or "u10" in arrays:
        return False
    date = pd.Timestamp(meta["init"].rstrip("Z")).tz_localize(None)
    models = meta["modelsByVar"]["wind"]
    w = arrays["w_wind"]                                              # (model, lead, cell)
    g = meta["grid"]
    comps = {U10: [], V10: []}
    for m in models:
        uv = member_uv(m, date)
        for v in comps:
            a = uv[v]
            if a.shape[1:] != (g["ny"], g["nx"]):
                raise ValueError(f"{run_id} {m}: grid {a.shape[1:]} != bundle {g['ny']} x {g['nx']}")
            comps[v].append(a.reshape(a.shape[0], -1))
    for name, v in (("u10", U10), ("v10", V10)):
        arrays[name] = (np.stack(comps[v]) * w).sum(0).astype(np.float32)
    meta["notes"] = [UV_OK_NOTE if n == UV_NOTE else n for n in meta.get("notes") or []]
    B.write_run(root, meta, arrays)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", default="bundles")
    a = ap.parse_args(argv)
    root = Path(a.bundles)
    for rid in B.list_runs(root):
        print(rid, "u/v added" if backfill_run(root, rid) else "skipped")
    B.write_index(root)


if __name__ == "__main__":
    main()
