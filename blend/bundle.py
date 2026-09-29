"""Run bundles on disk (BACKEND_BUILD_PLAN.md T3). Written by export.py / live jobs, read by server.py.

    bundles/
      index.json              {contractVersion, created, runs: [RunSummary...]}
      scorecards/<SET>.json   Scorecard-shaped rows for one model set, shared by every run using that set
      runs/<id>/meta.json     Run (camelCase, as served) + private "_x" block
      runs/<id>/arrays.npz    float32 arrays, (…, N) with N = ny*nx cells, row 0 southernmost

Only numpy and the stdlib: the server imports this module.
"""

import datetime
import json
import math
import os
import shutil
from pathlib import Path

import numpy as np

from .api_models import CONTRACT_VERSION

SUMMARY_KEYS = ("id", "kind", "init", "status", "models")


def _clean(x):
    """NaN / Inf -> None so the JSON is valid everywhere."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, np.generic):
        return _clean(x.item())
    return x


def _write_json(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(_clean(obj), indent=1, allow_nan=False))
    os.replace(tmp, path)


def write_run(root: Path, meta: dict, arrays: dict[str, np.ndarray]) -> Path:
    """Write runs/<id>/ atomically: build it in runs/<id>.tmp, then swap it in."""
    root = Path(root)
    runs = root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    final, tmp = runs / meta["id"], runs / f"{meta['id']}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    (tmp / "meta.json").write_text(json.dumps(_clean(meta), indent=1, allow_nan=False))
    np.savez_compressed(tmp / "arrays.npz", **{k: np.asarray(v, dtype=np.float32) for k, v in arrays.items()})
    if final.exists():
        shutil.rmtree(final)
    os.replace(tmp, final)
    return final


def write_meta(root: Path, meta: dict) -> None:
    """Replace meta.json of an existing run (atomic), e.g. to add the timing of the write itself."""
    _write_json(Path(root) / "runs" / meta["id"] / "meta.json", meta)


def read_meta(root: Path, run_id: str) -> dict:
    return json.loads((Path(root) / "runs" / run_id / "meta.json").read_text())


def read_arrays(root: Path, run_id: str) -> dict[str, np.ndarray]:
    with np.load(Path(root) / "runs" / run_id / "arrays.npz", allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def list_runs(root: Path) -> list[str]:
    """Complete runs only: a directory with meta.json, not a leftover .tmp."""
    runs = Path(root) / "runs"
    if not runs.is_dir():
        return []
    return sorted(p.name for p in runs.iterdir() if p.is_dir() and not p.name.endswith(".tmp") and (p / "meta.json").exists())


def write_index(root: Path) -> dict:
    """Rebuild index.json from runs/*/meta.json: live runs first (newest first), then hindcasts by date."""
    root = Path(root)
    summaries = [{k: read_meta(root, r)[k] for k in SUMMARY_KEYS} for r in list_runs(root)]
    live = sorted([s for s in summaries if s["kind"] == "live"], key=lambda s: s["init"], reverse=True)
    hind = sorted([s for s in summaries if s["kind"] != "live"], key=lambda s: s["init"])
    index = {"contractVersion": CONTRACT_VERSION,
             "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
             "runs": live + hind}
    root.mkdir(parents=True, exist_ok=True)
    _write_json(root / "index.json", index)
    return index


def read_index(root: Path) -> dict:
    p = Path(root) / "index.json"
    return json.loads(p.read_text()) if p.exists() else {"contractVersion": CONTRACT_VERSION, "runs": []}


def write_scorecard(root: Path, set_name: str, card: dict) -> None:
    d = Path(root) / "scorecards"
    d.mkdir(parents=True, exist_ok=True)
    _write_json(d / f"{set_name}.json", card)


def read_scorecard(root: Path, set_name: str) -> dict:
    return json.loads((Path(root) / "scorecards" / f"{set_name}.json").read_text())
