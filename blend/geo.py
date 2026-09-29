"""India outline and states for masks and state roll-ups (BACKEND_BUILD_PLAN.md T5/T6).

Reads web/src/geo/india.json (Survey of India boundary, baked by web/tools/make_geo.py) so the server and the map
agree on every cell. Point-in-polygon is a port of web/src/lib/geo.ts (inRing, stateAt). Stdlib + numpy only.
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

INDIA_JSON = Path(__file__).resolve().parents[1] / "web" / "src" / "geo" / "india.json"


@lru_cache(maxsize=1)
def _geo() -> dict:
    return json.loads(INDIA_JSON.read_text())


@lru_cache(maxsize=1)
def load_states() -> list[tuple[str, list[list[list[float]]], tuple[float, float, float, float]]]:
    """[(name, rings, bbox)] with rings as [[lon, lat], ...]."""
    out = []
    for s in _geo()["states"]:
        pts = [p for r in s["rings"] for p in r]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        out.append((s["name"], s["rings"], (min(xs), min(ys), max(xs), max(ys))))
    return out


def _in_ring(x: float, y: float, ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xa, ya = ring[i]
        xb, yb = ring[j]
        if (ya > y) != (yb > y) and x < (xb - xa) * (y - ya) / (yb - ya) + xa:
            inside = not inside
        j = i
    return inside


def state_at(lon: float, lat: float) -> int:
    """Index into load_states() of the state containing the point, or -1 outside India."""
    for s, (_, rings, (x0, y0, x1, y1)) in enumerate(load_states()):
        if lon < x0 or lon > x1 or lat < y0 or lat > y1:
            continue
        if sum(_in_ring(lon, lat, r) for r in rings) % 2 == 1:
            return s
    return -1


def state_index(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """State index per cell of the (lat, lon) grid, flattened row-major (row 0 = first latitude). -1 outside India."""
    return np.array([state_at(float(x), float(y)) for y in lat for x in lon], dtype=np.int16)


def india_mask(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """(len(lat), len(lon)) bool: cell centre inside India."""
    return (state_index(lat, lon) >= 0).reshape(len(lat), len(lon))


def state_rollup(prob: np.ndarray, idx: np.ndarray) -> list[dict]:
    """[{name, pmax, pmean, cells}] over cells with a finite probability, sorted by pmax (highest first)."""
    names = [s[0] for s in load_states()]
    out = []
    for s, name in enumerate(names):
        v = prob[(idx == s) & np.isfinite(prob)]
        if v.size:
            out.append({"name": name, "pmax": float(v.max()), "pmean": float(v.mean()), "cells": int(v.size)})
    return sorted(out, key=lambda r: -r["pmax"])
