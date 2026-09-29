"""C11 dashboard API (BACKEND_BUILD_PLAN.md T7-T9): serves run bundles in the shapes of web/src/lib/contract.ts.

    BLEND_BUNDLES=bundles uvicorn blend.server:app --port 8081
    BLEND_BUNDLES=bundles BLEND_WEB_DIST=web/dist uvicorn blend.server:app --port 8081   # API + built dashboard

Besides the contract endpoints it serves downloads (blend/deliver.py): /api/export/geojson and /api/export/csv.
No science happens here: bundles are already in display units. Only numpy, FastAPI and the bundle/geo helpers are
imported, so the server starts fast and runs with no network (tests/test_server_imports.py enforces it).
"""

import logging
import math
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from . import api_models as A
from . import bundle as B
from . import deliver as D
from .geo import state_index, state_rollup

UNITS = {"rain": "mm", "t2m": "°C", "wind": "m/s", "mslp": "hPa"}
DIGITS = {"field": 3, "weight": 4, "prob": 3}

log = logging.getLogger("uvicorn.error")


def _num(x, nd):
    """float -> rounded float, NaN / Inf -> None."""
    x = float(x)
    return round(x, nd) if math.isfinite(x) else None


def _list(a: np.ndarray, nd: int) -> list:
    return [None if not math.isfinite(v) else v for v in np.round(np.asarray(a, dtype=np.float64), nd).tolist()]


def _out(model: A.Api) -> JSONResponse:
    return JSONResponse(model.model_dump(by_alias=True))


def create_app(bundles: Path | str | None = None, web_dist: Path | str | None = None) -> FastAPI:
    root = Path(bundles or os.environ.get("BLEND_BUNDLES", "bundles")).resolve()
    dist = web_dist or os.environ.get("BLEND_WEB_DIST")
    dist = Path(dist).resolve() if dist else None
    app = FastAPI(title="Samanvay API", version=A.CONTRACT_VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    # Read-only public data: other sites may call the API from the browser. BLEND_CORS_ORIGINS narrows it
    # (comma-separated origins); no cookies or credentials are ever accepted.
    origins = [o.strip() for o in os.environ.get("BLEND_CORS_ORIGINS", "*").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"],
                       allow_credentials=False, max_age=86400)

    # ------------------------------------------------------------ reads (T7)

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except FileNotFoundError:
            return 0.0

    @lru_cache(maxsize=4)
    def _index_at(mtime: float) -> dict:
        return B.read_index(root)

    def index() -> dict:
        """Re-read when index.json changes, so a daily job can add runs without a restart."""
        return _index_at(_mtime(root / "index.json"))

    @lru_cache(maxsize=16)
    def _meta_at(run_id: str, mtime: float) -> dict:
        return B.read_meta(root, run_id)

    @lru_cache(maxsize=8)
    def _arrays_at(run_id: str, mtime: float) -> dict:
        return B.read_arrays(root, run_id)

    @lru_cache(maxsize=8)
    def _states(lat0, lon0, step, ny, nx) -> np.ndarray:
        return state_index(lat0 + step * np.arange(ny), lon0 + step * np.arange(nx))

    def meta(run_id: str) -> dict:
        if run_id not in {r["id"] for r in index()["runs"]}:
            raise HTTPException(404, f"unknown run '{run_id}'")
        return _meta_at(run_id, _mtime(root / "runs" / run_id / "meta.json"))

    def arrays(run_id: str) -> dict:
        return _arrays_at(run_id, _mtime(root / "runs" / run_id / "arrays.npz"))

    def var_of(m: dict, var: str) -> str:
        if var not in m["vars"]:
            raise HTTPException(404, f"variable '{var}' not in run {m['id']} (has {', '.join(m['vars'])})")
        return var

    def lead_of(m: dict, lead: int) -> int:
        if lead not in m["leads"]:
            raise HTTPException(404, f"lead {lead} not in run {m['id']} (leads {m['leads'][0]}-{m['leads'][-1]})")
        return m["leads"].index(lead)

    def cell_of(m: dict, i: int, j: int) -> int:
        g = m["grid"]
        if not (0 <= i < g["ny"] and 0 <= j < g["nx"]):
            raise HTTPException(404, f"cell ({i}, {j}) outside the {g['ny']} x {g['nx']} grid")
        return i * g["nx"] + j

    # --------------------------------------------------------- endpoints (T8)

    @app.get("/api/health")
    def health():
        ids = [r["id"] for r in index()["runs"]]
        measured = bool(ids) and all(meta(i)["provenance"] == "measured" for i in ids)
        return _out(A.Health(status="ok", contract_version=A.CONTRACT_VERSION, runs=len(ids),
                             provenance="measured" if measured else "synthetic"))

    @app.get("/api/runs")
    def runs():
        return JSONResponse([A.RunSummary.model_validate(r).model_dump(by_alias=True) for r in index()["runs"]])

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        m = meta(run_id)
        return _out(A.Run.model_validate({k: v for k, v in m.items() if k != "_x"}))

    @app.get("/api/field")
    def field(run: str, var: str, lead: int, model: str | None = None):
        m = meta(run)
        v, li = var_of(m, var), lead_of(m, lead)
        a = arrays(run)
        if model:
            models = m["modelsByVar"][v]
            if model not in models:
                raise HTTPException(404, f"model '{model}' has no {v} in run {run} (has {', '.join(models)})")
            values = a[f"fc_{v}"][models.index(model), li]
        else:
            values = a[f"blend_{v}"][li]
        uv = {}
        if v == "wind" and not model and "u10" in a and "v10" in a:
            uv = {"u": _list(a["u10"][li], 2), "v": _list(a["v10"][li], 2)}
        return _out(A.Field(var=v, lead=lead, units=UNITS[v], values=_list(values, DIGITS["field"]), **uv))

    @app.get("/api/weights")
    def weights(run: str, var: str, lead: int):
        m = meta(run)
        v, li = var_of(m, var), lead_of(m, lead)
        w = arrays(run)[f"w_{v}"][:, li]
        finite = np.isfinite(w).any(0)
        dominant = np.where(finite, np.argmax(np.where(np.isfinite(w), w, -np.inf), axis=0), 0)
        return _out(A.WeightSet(var=v, lead=lead, models=m["modelsByVar"][v],
                                weights=[_list(row, DIGITS["weight"]) for row in w], dominant=dominant.tolist()))

    @app.get("/api/scorecard")
    def scorecard(run: str):
        m = meta(run)
        sets = m["_x"]["sets"]
        rows, regions, texts = [], [], []
        for s in sorted(set(sets.values())):
            try:
                card = B.read_scorecard(root, s)
            except FileNotFoundError:
                continue
            mine = {v for v, sn in sets.items() if sn == s}
            rows += [r for r in card["rows"] if r["var"] in mine]
            regions += [r for r in card["regions"] if r["var"] in mine]
            texts.append(card["validation"])
        validation = " · ".join(dict.fromkeys(texts)) or "No held-out scorecard in this bundle."
        return _out(A.Scorecard.model_validate({"validation": validation, "rows": rows, "regions": regions}))

    @app.get("/api/extremes")
    def extremes(run: str, type: str, lead: int):
        m = meta(run)
        events = {e["id"]: e for e in m.get("extremes") or []}
        if type not in events:
            raise HTTPException(404, f"unknown event '{type}' in run {run} (has {', '.join(events) or 'none'})")
        li = lead_of(m, lead)
        a, x, g, ev = arrays(run), m["_x"], m["grid"], events[type]
        base = {"type": type, "lead": lead, "threshold": ev["threshold"],
                "calibrated": bool(x.get("extremeCalibrated")) and type not in (x.get("uncalibrated") or []),
                "method": (x.get("eventMethod") or {}).get(type, x.get("extremeMethod"))}
        if not ev.get("available") or f"p_{type}" not in a:
            return _out(A.ExtremeMap(**base, prob=[None] * (g["ny"] * g["nx"]), states=[], available=False,
                                     note=ev.get("note") or "Not produced for this run."))
        prob = a[f"p_{type}"][li]
        idx = _states(g["lat0"], g["lon0"], g["step"], g["ny"], g["nx"])
        return _out(A.ExtremeMap(**base, prob=_list(prob, DIGITS["prob"]),
                                 states=[{**s, "pmax": round(s["pmax"], 3), "pmean": round(s["pmean"], 3)}
                                         for s in state_rollup(prob, idx)],
                                 available=True, note=ev.get("note")))

    @app.get("/api/cell")
    def cell(run: str, var: str, lead: int, i: int, j: int):
        m = meta(run)
        v, li, k = var_of(m, var), lead_of(m, lead), cell_of(m, i, j)
        a, g, x = arrays(run), m["grid"], m["_x"]
        models = m["modelsByVar"][v]
        members = [{"model": md, "value": _num(a[f"fc_{v}"][n, li, k], 3), "weight": _num(a[f"w_{v}"][n, li, k], 4),
                    "mse": _num(a[f"mse_{v}"][n, li, k], 4), "bias": _num(a[f"bias_{v}"][n, li, k], 3)}
                   for n, md in enumerate(models)]
        return _out(A.CellReport(
            i=i, j=j, lat=g["lat0"] + i * g["step"], lon=g["lon0"] + j * g["step"], var=v, lead=lead,
            blend=_num(a[f"blend_{v}"][li, k], 3), members=members,
            mse_by_lead=[{"model": md, "mse": _list(a[f"mse_{v}"][n, :, k], 4)} for n, md in enumerate(models)],
            n_regime=int(x.get("nRegime", {}).get(v, 0)), n_season=int(x.get("nSeason", {}).get(v, 0)),
            k=float(x.get("k", 0))))

    @app.get("/api/meteogram")
    def meteogram(run: str, i: int, j: int):
        m = meta(run)
        k = cell_of(m, i, j)
        a, g = arrays(run), m["grid"]
        out = []
        for v in m["vars"]:
            models = m["modelsByVar"][v]
            out.append({"var": v, "blend": _list(a[f"blend_{v}"][:, k], 3),
                        "members": [{"model": md, "values": _list(a[f"fc_{v}"][n, :, k], 3),
                                     "weights": _list(a[f"w_{v}"][n, :, k], 4)} for n, md in enumerate(models)]})
        return _out(A.Meteogram(i=i, j=j, lat=g["lat0"] + i * g["step"], lon=g["lon0"] + j * g["step"],
                                leads=m["leads"], vars=out))

    # ------------------------------------------------------- products (C9)

    def _attachment(name: str) -> dict:
        return {"Content-Disposition": f'attachment; filename="{name}"'}

    @app.get("/api/export/geojson")
    def export_geojson(run: str, lead: int | None = None):
        m = meta(run)
        if lead is not None:
            lead_of(m, lead)
        body = D.geojson(m, arrays(run), lead)
        name = f"{run}{'' if lead is None else f'_d{lead}'}.geojson"
        return JSONResponse(body, media_type="application/geo+json", headers=_attachment(name))

    @app.get("/api/export/csv")
    def export_csv(run: str):
        m = meta(run)
        return Response(D.states_csv(m, arrays(run)), media_type="text/csv; charset=utf-8",
                        headers=_attachment(f"{run}_states.csv"))

    @app.get("/api/{rest:path}")
    def api_404(rest: str):
        raise HTTPException(404, f"no endpoint /api/{rest}")

    # ------------------------------------------------ built dashboard (optional)

    if dist and (dist / "index.html").exists():
        @app.get("/{path:path}")
        def spa(path: str):
            f = (dist / path).resolve()
            if path and f.is_file() and dist in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    log.info("blend.server: bundles %s, %d runs, contract %s%s", root, len(index()["runs"]), A.CONTRACT_VERSION,
             f", dashboard {dist}" if dist else "")
    return app


app = create_app()
