"""C9 products from a run bundle, for people and tools outside the dashboard.

  GeoJSON   one square polygon per grid cell: blended value of every variable, dominant model and extreme
            probabilities, for one lead or all leads. Served by the API: /api/export/geojson?run=&lead=
  CSV       state-level table (states of India, Survey of India outline): per variable and lead the mean / min / max
            of the blend over the state's cells, per extreme event the highest and mean probability.
            Served by the API: /api/export/csv?run=
  NetCDF    every array of the bundle with named dimensions, CF-style coordinates:
            python -m blend.deliver RUN_ID [--bundles bundles] [--out products]

At 1.5° a cell is ~167 km across, larger than most districts, so there is no district table: the state table is
the finest honest roll-up. GeoJSON and CSV use numpy and the stdlib only (the server imports this module);
NetCDF imports xarray when called.
"""

import argparse
import csv
import io
import math
from pathlib import Path

import numpy as np

from . import bundle as B
from .geo import load_states, state_index

UNITS = {"rain": "mm", "t2m": "degC", "wind": "m s-1", "mslp": "hPa"}


def _num(x, nd=3):
    x = float(x)
    return round(x, nd) if math.isfinite(x) else None


def _grid(meta):
    g = meta["grid"]
    lat = g["lat0"] + g["step"] * np.arange(g["ny"])
    lon = g["lon0"] + g["step"] * np.arange(g["nx"])
    return g, lat, lon


def _events(meta, arrays):
    return [e for e in meta.get("extremes") or [] if e.get("available") and f"p_{e['id']}" in arrays]


def geojson(meta: dict, arrays: dict, lead: int | None = None) -> dict:
    """FeatureCollection of cell squares; properties keyed <var>_d<lead>, dominant_<var>_d<lead>, p_<event>_d<lead>."""
    g, lat, lon = _grid(meta)
    leads = meta["leads"] if lead is None else [lead]
    li = [meta["leads"].index(x) for x in leads]
    states = [s[0] for s in load_states()]
    sidx = state_index(lat, lon)
    events = _events(meta, arrays)
    dom = {}
    for v in meta["vars"]:
        w = arrays[f"w_{v}"]                                          # (model, lead, cell)
        ok = np.isfinite(w).any(0)
        dom[v] = np.where(ok, np.argmax(np.where(np.isfinite(w), w, -np.inf), axis=0), -1)
    h = g["step"] / 2
    feats = []
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            k = i * g["nx"] + j
            props = {"i": i, "j": j, "lat": float(la), "lon": float(lo),
                     "state": states[sidx[k]] if sidx[k] >= 0 else None}
            for v in meta["vars"]:
                models = meta["modelsByVar"][v]
                for L, n in zip(leads, li):
                    props[f"{v}_d{L}"] = _num(arrays[f"blend_{v}"][n, k])
                    d = dom[v][n, k]
                    props[f"dominant_{v}_d{L}"] = models[d] if d >= 0 else None
            for e in events:
                for L, n in zip(leads, li):
                    props[f"p_{e['id']}_d{L}"] = _num(arrays[f"p_{e['id']}"][n, k])
            ring = [[lo - h, la - h], [lo + h, la - h], [lo + h, la + h], [lo - h, la + h], [lo - h, la - h]]
            feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": props})
    return {"type": "FeatureCollection",
            "properties": {"run": meta["id"], "init": meta["init"], "leads": leads,
                           "units": {v: UNITS[v] for v in meta["vars"]},
                           "events": {e["id"]: e["name"] for e in events},
                           "note": "Lead d = the 24 h ending 00 UTC d days after init; rain is that 24 h total."},
            "features": feats}


def states_csv(meta: dict, arrays: dict) -> str:
    """state, kind (variable | event), name, units, lead, mean, min, max, cells."""
    _, lat, lon = _grid(meta)
    sidx = state_index(lat, lon)
    names = [s[0] for s in load_states()]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["run", "state", "kind", "name", "units", "lead_day", "mean", "min", "max", "cells"])
    events = _events(meta, arrays)
    for s, name in enumerate(names):
        cells = sidx == s
        if not cells.any():
            continue
        for v in meta["vars"]:
            for n, L in enumerate(meta["leads"]):
                x = arrays[f"blend_{v}"][n, cells]
                x = x[np.isfinite(x)]
                if x.size:
                    w.writerow([meta["id"], name, "variable", v, UNITS[v], L,
                                _num(x.mean()), _num(x.min()), _num(x.max()), int(x.size)])
        for e in events:
            for n, L in enumerate(meta["leads"]):
                x = arrays[f"p_{e['id']}"][n, cells]
                x = x[np.isfinite(x)]
                if x.size:
                    w.writerow([meta["id"], name, "event", e["id"], "probability", L,
                                _num(x.mean()), _num(x.min()), _num(x.max()), int(x.size)])
    return buf.getvalue()


def to_netcdf(root: Path, run_id: str, out: Path) -> Path:
    """Every bundle array as a NetCDF variable with (model, lead, latitude, longitude) dimensions."""
    import xarray as xr
    meta, arrays = B.read_meta(root, run_id), B.read_arrays(root, run_id)
    g, lat, lon = _grid(meta)
    shape = (g["ny"], g["nx"])
    coords = {"lead": ("lead", meta["leads"], {"long_name": "forecast day", "units": "days"}),
              "latitude": ("latitude", lat, {"units": "degrees_north"}),
              "longitude": ("longitude", lon, {"units": "degrees_east"})}
    data = {}
    for k, a in arrays.items():
        a = np.asarray(a, dtype="float32")
        prefix, _, var = k.partition("_")
        if a.ndim == 3:                                               # (model, lead, cell)
            models = meta["modelsByVar"].get(var) or (meta.get("_x", {}).get("t12Models") if k == "t12_t2m" else None)
            dim = f"model_{var}" if models else "member"
            if models:
                coords[dim] = (dim, list(models))
            data[k] = ((dim, "lead", "latitude", "longitude"), a.reshape(a.shape[:2] + shape))
        elif a.ndim == 2:                                             # (lead, cell)
            data[k] = (("lead", "latitude", "longitude"), a.reshape(a.shape[:1] + shape))
        units = UNITS.get(var) if prefix in ("fc", "blend", "bias") else ("1" if prefix in ("w", "p") else None)
        if units:
            data[k] = data[k] + ({"units": units},)
    ds = xr.Dataset(data, coords=coords)
    ds.attrs = {"title": f"Samanvay blended forecast {run_id}", "init": meta["init"], "rung": meta.get("rung", ""),
                "models": ", ".join(meta["models"]), "notes": " | ".join(meta.get("notes") or []),
                "conventions": "fc_<var> member forecasts, blend_<var> blended forecast, w_<var> weights, "
                               "mse_<var> error used for the weights, bias_<var> bias removed, p_<event> probability"}
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{run_id}.nc"
    ds.to_netcdf(path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write a run bundle as NetCDF (GeoJSON / CSV are served by the API).")
    ap.add_argument("run", nargs="?", help="run id; default: every run in the bundles folder")
    ap.add_argument("--bundles", default="bundles")
    ap.add_argument("--out", default="products")
    a = ap.parse_args(argv)
    root = Path(a.bundles)
    for rid in [a.run] if a.run else B.list_runs(root):
        print(to_netcdf(root, rid, Path(a.out)))


if __name__ == "__main__":
    main()
