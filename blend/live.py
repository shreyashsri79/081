"""C10 Daily live run: today's ECMWF IFS, ECMWF AIFS and NOAA GFS forecasts, blended with learned weights.

    python -m blend.live build-model --art artifacts --cache cache   # once, after a Kaggle training run
    python -m blend.live run --bundles bundles                       # every day, after ~09 UTC

build-model reads artifacts/S1 (t2m, wind, mslp) and artifacts/S2 (rain) and writes models/live_model.nc: for each
variable the training error covariance between models and each model's seasonal bias; with --cache also the
extreme-event tables (truth thresholds, per-model quantile thresholds, calibration) behind the live probabilities.

run
  1. downloads the newest 00 UTC run of every live model (Day 1-10) and averages it onto the 1.5° training cells;
  2. verifies the earlier live runs against today's analysis (IFS step 0) and updates the online error statistics
     (rung B4: exponentially weighted, ~20-day memory) in models/live_state.nc;
  3. blends: minimum-variance weights (B2c) from the covariance, where the prior comes from each live model's
     training counterpart (PROXY) and the online statistics take over as verified days accumulate;
  4. writes calibrated extreme-event probabilities and a live bundle for the dashboard.

Honest limits, repeated in every bundle's notes: the live models are not the training models (IFS <- HRES,
AIFS <- GraphCast, GFS <- HRES with a deliberately inflated error); the online truth is the IFS analysis, which
favours IFS; rain has no live truth, so rain weights stay at their training prior.
"""

import argparse
import datetime
import json
import os
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import bundle as B
from . import config as C
from .export import EVENT_TEXT, HEAT_EVENT, REGIME_TEXT, diff_scale, to_display
from .weights import min_variance

ECMWF_MODELS = {"ifs": "ifs", "aifs": "aifs-single"}             # our id -> ecmwf-opendata model name
LIVE_MODELS = ["ifs", "aifs", "gfs", "ncum", "nepsg"]
NCMRWF_MODELS = ["ncum", "nepsg"]                                # only when NCMRWF files are given (blend/adapters.py)
PROXY = {"ifs": "hres", "aifs": "graphcast", "gfs": "hres", "ncum": "hres", "nepsg": "hres"}
PRIOR_INFLATION = {"gfs": 1.5, "ncum": 1.5, "nepsg": 1.5}        # no training counterpart: start from 1.5x HRES error
BIAS_FROM_PROXY = {"ifs"}                                        # others: no bias correction until verified
VAR_IDS = {"t2m": C.T2M, "wind": C.WIND, "mslp": C.MSLP, "rain": C.RAIN}
SET_OF = {"t2m": "S1", "wind": "S1", "mslp": "S1", "rain": "S2"}
VERIFIED = ["t2m", "wind", "mslp"]                               # vars with a live truth (the analysis)
LAT = np.arange(6.0, 39.01, 1.5)                                 # training grid cells inside the India box
LON = np.arange(66.0, 99.01, 1.5)
ROOT = Path(__file__).resolve().parent.parent
MODEL_FILE = ROOT / "models" / "live_model.nc"
STATE_FILE = Path(os.environ.get("BLEND_LIVE_STATE", ROOT / "models" / "live_state.nc"))
KEEP_LIVE = 10                                                   # live bundles kept: enough to verify Day 1-10
LAMBDA = 0.95                                                    # online memory (~20 days)
K_ONLINE = 20.0                                                  # prior strength, in verified days
GFS_URL = ("https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?dir=%2Fgfs.{d:%Y%m%d}%2F00%2Fatmos"
           "&file=gfs.t00z.pgrb2.0p25.f{h:03d}&var_APCP=on&var_PRMSL=on&var_TMP=on&var_UGRD=on&var_VGRD=on"
           "&lev_2_m_above_ground=on&lev_10_m_above_ground=on&lev_mean_sea_level=on&lev_surface=on"
           "&subregion=&toplat=41&leftlon=64&rightlon=101&bottomlat=4")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ================================================================== build-model

def build_model(art: str, cache: str | None = None, out: Path = MODEL_FILE) -> Path:
    parts = {}
    for vid, wb2 in VAR_IDS.items():
        f = Path(art) / SET_OF[vid] / f"weights_{SET_OF[vid]}_{wb2.replace('_', '')}.nc"
        if not f.exists():
            log(f"skip {vid}: {f} not found")
            continue
        ds = xr.load_dataset(f)
        if "cov_all" not in ds:
            raise SystemExit(f"{f} has no cov_all: re-run training with the current code (run_all.py)")
        parts[f"cov_{vid}"] = ds["cov_all"].rename(m1=f"m1_{vid}", m2=f"m2_{vid}")
        parts[f"bias_{vid}"] = ds["bias"].rename(model=f"model_{vid}")
    if not parts:
        raise SystemExit("no weights files found under " + art)
    model = xr.Dataset(parts)
    if cache:
        model = model.merge(extreme_tables(cache, model))
    out.parent.mkdir(parents=True, exist_ok=True)
    model.attrs.update({"source": str(art), "created": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    model.to_netcdf(out)
    log(f"wrote {out}: {sorted(model.data_vars)}")
    return out


def extreme_tables(cache: str, model: xr.Dataset) -> xr.Dataset:
    """Per event: the proxies' quantile thresholds (tau) and the calibration table of their weighted vote,
    fitted on all training years exactly as blend/extremes.py does per fold."""
    from . import extremes as X
    from .cache import load_forecasts, load_truth
    from .harmonise import prepare
    truth = load_truth(cache)
    proxies = sorted(set(PROXY[m] for m in ECMWF_MODELS))           # the pair the calibration is fitted for
    out = {}
    for vid, wb2 in VAR_IDS.items():
        events = X.EVENTS.get(wb2, [])
        if not events or f"cov_{vid}" not in model:
            continue
        s = C.SETS[SET_OF[vid]]
        fc, obs = prepare(load_forecasts(cache, proxies, s["years"]), truth, wb2)
        fc = fc.sel(model=proxies)
        w = min_variance(pair_prior(model, vid, proxies)).fillna(1.0 / len(proxies))
        w = w.assign_coords(lead=fc.lead.values).transpose("model", "lead", "latitude", "longitude")
        for name, kind, value in events:
            thr = X.truth_threshold(obs, kind, value)
            base = (obs >= thr).where(obs.notnull()).mean(["init", "lead"])
            tau = X.model_thresholds(fc, base)                        # (model, lead, lat, lon)
            votes = (fc >= tau).where(fc.notnull() & tau.notnull())
            p_raw = (votes * w).sum("model", skipna=False).transpose("init", "lead", ...)
            ev = (obs >= thr).where(obs.notnull()).transpose("init", "lead", ...)
            table = X.fit_calibration(p_raw.values, ev.values)
            key = f"{vid}_{name}"
            out[f"tau_{key}"] = tau.rename(model=f"tmodel_{key}").transpose(f"tmodel_{key}", "lead", "latitude", "longitude")
            out[f"cal_{key}"] = xr.DataArray(table, dims=("lead", "pbin"), coords={"lead": fc.lead.values})
            log(f"extreme table {key}: base rate {float(base.mean()):.3f}")
    return xr.Dataset(out)


# ================================================================== download + regrid

def _conservative_matrix(src: np.ndarray, centres: np.ndarray) -> np.ndarray:
    """Weights that average 0.25° point values over 1.5° cells (edges at centre ± 0.75°, half weight at edges)."""
    W = np.zeros((len(centres), len(src)))
    for i, c in enumerate(centres):
        d = np.abs(src - c)
        w = np.where(d < 0.75 - 1e-6, 1.0, np.where(np.abs(d - 0.75) < 1e-6, 0.5, 0.0))
        W[i] = w / w.sum()
    return W


def to_training_grid(da: xr.DataArray) -> xr.DataArray:
    """(…, latitude, longitude) at 0.25° -> the 1.5° training cells."""
    da = da.sortby("latitude").sortby("longitude").sel(latitude=slice(LAT[0] - 0.8, LAT[-1] + 0.8),
                                                       longitude=slice(LON[0] - 0.8, LON[-1] + 0.8))
    Wy = _conservative_matrix(da.latitude.values, LAT)
    Wx = _conservative_matrix(da.longitude.values, LON)
    out = np.einsum("ia,...ab,jb->...ij", Wy, da.values, Wx)
    dims = da.dims[:-2] + ("latitude", "longitude")
    coords = {d: da[d] for d in da.dims[:-2]} | {"latitude": LAT, "longitude": LON}
    return xr.DataArray(out, dims=dims, coords=coords)


def _assemble(t2m, u, v, msl, tp_acc) -> xr.Dataset:
    """Arrays with an 'hours' axis (0, 24, ..., 240) -> dataset on the training grid, dims (lead, lat, lon),
    plus the step-0 analysis. tp_acc: accumulation since the start, in metres."""
    leads = [24 * d for d in C.LEAD_DAYS]
    rain = np.maximum(tp_acc.sel(hours=leads).values - tp_acc.sel(hours=[h - 24 for h in leads]).values, 0)
    rain = xr.DataArray(rain, dims=("hours", "latitude", "longitude"),
                        coords={"hours": leads, "latitude": tp_acc.latitude, "longitude": tp_acc.longitude})
    fields = {C.T2M: t2m, C.MSLP: msl, C.WIND: np.hypot(u, v), "u10": u, "v10": v}
    out = {k: to_training_grid(f.sel(hours=leads)) for k, f in fields.items()}
    out[C.RAIN] = to_training_grid(rain)
    ds = xr.Dataset(out).rename(hours="lead").assign_coords(lead=C.LEAD_DAYS)
    if 0 in t2m.hours.values:                                     # analysis at the init time
        for k in (C.T2M, C.MSLP, C.WIND):
            ds[f"ana_{k}"] = to_training_grid(fields[k].sel(hours=0))
    return ds


def latest_ecmwf(model: str) -> datetime.datetime:
    from ecmwf.opendata import Client
    return Client(source="ecmwf", model=ECMWF_MODELS[model]).latest(time=0, step=240, param="2t")


def fetch_ecmwf(model: str, init: datetime.datetime, work: Path) -> xr.Dataset:
    from ecmwf.opendata import Client
    path = work / f"{model}_{init:%Y%m%d}.grib2"
    if not path.exists():
        Client(source="ecmwf", model=ECMWF_MODELS[model]).retrieve(
            date=init, time=0, step=[24 * d for d in range(0, 11)], param=["2t", "10u", "10v", "msl", "tp"],
            target=str(path) + ".tmp")
        os.replace(str(path) + ".tmp", path)

    def one(short):
        ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"filter_by_keys": {"shortName": short}, "indexpath": ""})
        da = ds[list(ds.data_vars)[0]]
        da = da.assign_coords(step=(da.step.values / np.timedelta64(1, "h")).astype(int)).rename(step="hours")
        return da.drop_vars([c for c in da.coords if c not in da.dims])

    tp = one("tp")
    tp = tp / 1000.0 if tp.attrs.get("units", "m") != "m" else tp  # AIFS: kg m-2 (= mm)
    return _assemble(one("2t"), one("10u"), one("10v"), one("msl"), tp)


AFTERNOON_STEPS = [24 * d - 12 for d in C.LEAD_DAYS]             # 12 UTC (17:30 IST) of each lead's day


def fetch_ecmwf_afternoon(model: str, init: datetime.datetime, work: Path) -> xr.DataArray:
    """2 m temperature at 12 UTC of each lead's day, (lead, lat, lon) on the training grid, in K."""
    from ecmwf.opendata import Client
    path = work / f"{model}_{init:%Y%m%d}_t12.grib2"
    if not path.exists():
        Client(source="ecmwf", model=ECMWF_MODELS[model]).retrieve(
            date=init, time=0, step=AFTERNOON_STEPS, param=["2t"], target=str(path) + ".tmp")
        os.replace(str(path) + ".tmp", path)
    ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"filter_by_keys": {"shortName": "2t"}, "indexpath": ""})
    da = ds[list(ds.data_vars)[0]]
    hours = (da.step.values / np.timedelta64(1, "h")).astype(int)
    da = da.assign_coords(step=hours).sel(step=AFTERNOON_STEPS)
    da = da.drop_vars([c for c in da.coords if c not in da.dims])
    return to_training_grid(da).rename(step="lead").assign_coords(lead=C.LEAD_DAYS)


def fetch_gfs_afternoon(init: datetime.datetime, work: Path) -> xr.DataArray:
    """GFS 2 m temperature at 12 UTC of each lead's day (NOMADS grib filter, 2 m TMP only)."""
    import eccodes
    url = GFS_URL.split("&var_APCP")[0] + "&var_TMP=on&lev_2_m_above_ground=on&subregion=" + GFS_URL.split("&subregion=")[1]
    out, lat, lon = [], None, None
    for h in AFTERNOON_STEPS:
        path = work / f"gfs_{init:%Y%m%d}_f{h:03d}_t2m.grib2"
        if not path.exists():
            urllib.request.urlretrieve(url.format(d=init, h=h), str(path) + ".tmp")
            os.replace(str(path) + ".tmp", path)
            time.sleep(0.5)
        with open(path, "rb") as f:
            g = eccodes.codes_grib_new_from_file(f)
            ni, nj = eccodes.codes_get(g, "Ni"), eccodes.codes_get(g, "Nj")
            out.append(eccodes.codes_get_values(g).reshape(nj, ni))
            lat = eccodes.codes_get_array(g, "distinctLatitudes")
            lon = eccodes.codes_get_array(g, "distinctLongitudes")
            if eccodes.codes_get(g, "jScansPositively") == 0:
                lat = np.sort(lat)[::-1]
            eccodes.codes_release(g)
    da = xr.DataArray(np.stack(out), dims=("lead", "latitude", "longitude"),
                      coords={"lead": C.LEAD_DAYS, "latitude": lat, "longitude": lon})
    return to_training_grid(da)


def fetch_gfs(init: datetime.datetime, work: Path) -> xr.Dataset:
    """NOAA GFS 0.25° from the NOMADS grib filter, India box only (~0.2 MB per step)."""
    import eccodes
    hours = [24 * d for d in range(0, 11)]
    fields = {k: {} for k in ("2t", "10u", "10v", "prmsl", "tp")}
    lat = lon = None
    for h in hours:
        path = work / f"gfs_{init:%Y%m%d}_f{h:03d}.grib2"
        if not path.exists():
            urllib.request.urlretrieve(GFS_URL.format(d=init, h=h), str(path) + ".tmp")
            os.replace(str(path) + ".tmp", path)
            time.sleep(0.5)                                       # be gentle with NOMADS
        with open(path, "rb") as f:
            while (g := eccodes.codes_grib_new_from_file(f)) is not None:
                short, rng = eccodes.codes_get(g, "shortName"), str(eccodes.codes_get(g, "stepRange"))
                if short in fields and (short != "tp" or rng == f"0-{h}"):
                    ni, nj = eccodes.codes_get(g, "Ni"), eccodes.codes_get(g, "Nj")
                    vals = eccodes.codes_get_values(g).reshape(nj, ni)
                    lat = eccodes.codes_get_array(g, "distinctLatitudes")
                    lon = eccodes.codes_get_array(g, "distinctLongitudes")
                    if eccodes.codes_get(g, "jScansPositively") == 0:
                        lat = np.sort(lat)[::-1]
                    fields[short][h] = vals
                eccodes.codes_release(g)
        if h == 0:
            fields["tp"][0] = np.zeros_like(fields["2t"][0])       # no rain accumulated at step 0

    def da(short, scale=1.0):
        arr = np.stack([fields[short][h] for h in hours]) * scale
        return xr.DataArray(arr, dims=("hours", "latitude", "longitude"),
                            coords={"hours": hours, "latitude": lat, "longitude": lon})

    return _assemble(da("2t"), da("10u"), da("10v"), da("prmsl"), da("tp", 1 / 1000.0))


def load_ncmrwf(path: str, init: datetime.datetime):
    """NCUM / NEPS-G GRIB2 run (blend/adapters.py) -> (dataset on the training grid, afternoon 2 m T or None, info)."""
    from .adapters import load
    f, t12, info = load(path, init)
    ds = _assemble(f["2t"], f["10u"], f["10v"], f["msl"], f["tp"])
    if t12 is not None:
        t12 = to_training_grid(t12).rename(hours="lead").assign_coords(lead=C.LEAD_DAYS)
    return ds, t12, info


def latest_gfs() -> datetime.datetime:
    """Newest 00 UTC GFS run on NOMADS whose Day-10 file exists."""
    today = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    for back in range(0, 3):
        d = today - datetime.timedelta(days=back)
        try:
            req = urllib.request.Request(GFS_URL.format(d=d, h=240), method="HEAD")
            if urllib.request.urlopen(req, timeout=30).status == 200:
                return d
        except Exception:
            continue
    raise RuntimeError("no complete 00 UTC GFS run on NOMADS in the last 3 days")


# ================================================================== weights: prior + online (B4)

def pair_prior(model: xr.Dataset, vid: str, members: list[str]) -> xr.DataArray:
    """Training covariance for `members` (training ids or live ids), dims (m1, m2, lead, lat, lon)."""
    cov = model[f"cov_{vid}"].rename({f"m1_{vid}": "m1", f"m2_{vid}": "m2"})
    src = [PROXY.get(m, m) for m in members]
    c = cov.sel(m1=src, m2=src).assign_coords(m1=members, m2=members).transpose(
        "m1", "m2", "lead", "latitude", "longitude").copy()
    for i, m in enumerate(members):                               # inflate a weaker member's prior error
        f = np.sqrt(PRIOR_INFLATION.get(m, 1.0))
        if f != 1.0:
            c[dict(m1=i)] = c[dict(m1=i)] * f
            c[dict(m2=i)] = c[dict(m2=i)] * f
    return c


def load_state() -> dict:
    """{vid: (S, n, mu)}: S = EWMA of e_i e_j, dims (m1, m2, lead, lat, lon); n = effective days (lead, lat, lon);
    mu = EWMA of e_i (m1, lead, lat, lon). e is the raw forecast error against the analysis."""
    if not STATE_FILE.exists():
        return {}
    ds = xr.load_dataset(STATE_FILE)
    out = {}
    for v in ds.data_vars:
        if v.startswith("s_") and f"mu_{v[2:]}" in ds:
            vid = v[2:]
            out[vid] = (ds[v].rename({f"m1_{vid}": "m1", f"m2_{vid}": "m2"}), ds[f"n_{vid}"],
                        ds[f"mu_{vid}"].rename({f"m1_{vid}": "m1"}))
    return out


def save_state(state: dict):
    ds = xr.Dataset({**{f"s_{v}": s.rename(m1=f"m1_{v}", m2=f"m2_{v}") for v, (s, _, _) in state.items()},
                     **{f"n_{v}": n for v, (_, n, _) in state.items()},
                     **{f"mu_{v}": mu.rename(m1=f"m1_{v}") for v, (_, _, mu) in state.items()}})
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(str(STATE_FILE) + ".tmp")
    os.replace(str(STATE_FILE) + ".tmp", STATE_FILE)


def online_cov(prior: xr.DataArray, state: dict, vid: str, members: list[str]):
    """B4: (n * C_online + K * C_prior) / (n + K). C_online is the covariance of the members' errors against the
    analysis with each member's mean error removed (S - mu_i mu_j): the analysis is not the training truth (ERA5),
    so only the random part of the error, not the bias, is learned online. n = effective verified days."""
    if vid not in state:
        return prior, 0.0
    s, n, mu = state[vid]
    if any(m not in s.m1.values for m in members):                # a member never verified: prior only
        return prior, 0.0
    m_ = mu.sel(m1=members).values
    s = s.sel(m1=members, m2=members).values - m_[:, None] * m_[None, :]
    ok = np.isfinite(s)
    nn = np.broadcast_to(n.values, s.shape)
    cov = np.where(ok, (nn * np.nan_to_num(s) + K_ONLINE * prior.values) / (nn + K_ONLINE), prior.values)
    return prior.copy(data=cov), float(n.mean())


def verify_and_update(bundles: Path, today: datetime.datetime, analysis: xr.Dataset, state: dict):
    """Score every kept live run whose valid time is `today` against the analysis; update the online statistics.
    Returns (state, rows)."""
    rows = []
    for rid in B.list_runs(bundles):
        if not rid.startswith("live-"):
            continue
        init = datetime.datetime.strptime(rid[5:], "%Y%m%d")
        lead = (today - init).days
        if not 1 <= lead <= 10:
            continue
        meta, arr = B.read_meta(bundles, rid), B.read_arrays(bundles, rid)
        li = meta["leads"].index(lead)
        wlat = np.repeat(np.cos(np.deg2rad(LAT)), len(LON))
        for vid in VERIFIED:
            if f"fc_{vid}" not in arr or f"ana_{VAR_IDS[vid]}" not in analysis:
                continue
            truth = to_display(vid, analysis[f"ana_{VAR_IDS[vid]}"].values.reshape(-1))
            members = meta["modelsByVar"][vid]
            k = diff_scale(vid)
            err = (arr[f"fc_{vid}"][:, li] - truth) / k                          # training units (K, m/s, Pa)
            e = err                                                              # raw error; bias removed online
            rmse = lambda x: float(np.sqrt(np.nansum(wlat * x ** 2) / np.nansum(wlat * np.isfinite(x))))
            row = {"run": rid, "valid": f"{today:%Y-%m-%d}", "lead": lead, "var": vid,
                   "blend": rmse(arr[f"blend_{vid}"][li] - truth), **{m: rmse(err[n] * k) for n, m in enumerate(members)}}
            rows.append(row)
            # online second moments per (member pair, lead, cell)
            prod = np.einsum("ic,jc->ijc", e, e).reshape(len(members), len(members), len(LAT), len(LON))
            state = _ewma(state, vid, members, lead, prod, e.reshape(len(members), len(LAT), len(LON)))
    return state, rows


def _ewma(state: dict, vid, members, lead, prod, e):
    old_s, old_n, old_mu = state.get(vid, (None, None, None))
    if old_s is None or any(m not in old_s.m1.values for m in members):
        allm = sorted(set(members) | (set(old_s.m1.values) if old_s is not None else set()), key=LIVE_MODELS.index)
        s = xr.DataArray(np.full((len(allm), len(allm), 10, len(LAT), len(LON)), np.nan),
                         dims=("m1", "m2", "lead", "latitude", "longitude"),
                         coords={"m1": allm, "m2": allm, "lead": C.LEAD_DAYS, "latitude": LAT, "longitude": LON})
        n = xr.DataArray(np.zeros((10, len(LAT), len(LON))), dims=("lead", "latitude", "longitude"),
                         coords={"lead": C.LEAD_DAYS, "latitude": LAT, "longitude": LON})
        mu = xr.DataArray(np.full((len(allm), 10, len(LAT), len(LON)), np.nan), dims=("m1", "lead", "latitude", "longitude"),
                          coords={"m1": allm, "lead": C.LEAD_DAYS, "latitude": LAT, "longitude": LON})
        if old_s is not None:
            s.loc[dict(m1=list(old_s.m1.values), m2=list(old_s.m2.values))] = old_s.values
            mu.loc[dict(m1=list(old_mu.m1.values))] = old_mu.values
            n[:] = old_n.values
    else:
        s, n, mu = old_s.copy(), old_n.copy(), old_mu.copy()
    sel = dict(m1=members, m2=members, lead=lead)
    cur = s.loc[sel].values
    s.loc[sel] = np.where(np.isfinite(cur), LAMBDA * cur + (1 - LAMBDA) * prod, prod)
    sel_mu = dict(m1=members, lead=lead)
    cur = mu.loc[sel_mu].values
    mu.loc[sel_mu] = np.where(np.isfinite(cur), LAMBDA * cur + (1 - LAMBDA) * e, e)
    n.loc[dict(lead=lead)] = LAMBDA * n.loc[dict(lead=lead)].values + 1.0
    return {**state, vid: (s, n, mu)}


# ================================================================== blend + extremes + bundle

def blend_var(vid, fcs: dict, model: xr.Dataset, state: dict, season: str):
    """fcs: {live model: DataArray (lead, lat, lon) in training units, rain in mm}."""
    live = list(fcs)
    prior = pair_prior(model, vid, live)
    cov, n_online = online_cov(prior, state, vid, live) if vid in VERIFIED else (prior, 0.0)
    w = min_variance(cov).transpose("model", "lead", "latitude", "longitude")
    w = w.fillna(1.0 / len(live))            # rain truth is land only: no learned skill over the sea
    bias = model[f"bias_{vid}"].rename({f"model_{vid}": "model"}).sel(season=season, model=[PROXY[m] for m in live])
    bias = bias.assign_coords(model=live).transpose("model", "lead", "latitude", "longitude")
    bias = bias.where(xr.DataArray([m in BIAS_FROM_PROXY for m in live], dims="model", coords={"model": live}), 0.0)
    fc = xr.concat([fcs[m] for m in live], pd.Index(live, name="model")).transpose("model", "lead", "latitude", "longitude")
    fc_bc = fc - bias.values
    if vid == "rain":
        fc_bc = fc_bc.clip(min=0)
    blended = (fc_bc * w.values).sum("model")
    mse = np.stack([cov.sel(m1=m, m2=m).values for m in live])
    k = diff_scale(vid)
    arrays = {f"fc_{vid}": _flat(to_display(vid, fc.values)), f"blend_{vid}": _flat(to_display(vid, blended.values)),
              f"w_{vid}": _flat(w.values), f"mse_{vid}": _flat(mse * k * k), f"bias_{vid}": _flat(bias.values * k)}
    return arrays, w, fc, n_online


def extreme_probs(vid, fc: xr.DataArray, w: xr.DataArray, model: xr.Dataset) -> list[dict]:
    """Calibrated probabilities for today's forecasts from the stored proxy tables."""
    from . import extremes as X
    out = []
    for name, _, _ in X.EVENTS.get(VAR_IDS[vid], []):
        key = f"{vid}_{name}"
        if f"tau_{key}" not in model:
            continue
        tau_p = model[f"tau_{key}"].rename({f"tmodel_{key}": "model"})
        tau = tau_p.sel(model=[PROXY[m] for m in fc.model.values]).assign_coords(model=fc.model.values)
        votes = (fc >= tau.values).where(fc.notnull() & np.isfinite(tau.values))
        p_raw = (votes * w.values).sum("model", skipna=False).transpose("lead", "latitude", "longitude").values
        p = X.apply_calibration(p_raw[None], model[f"cal_{key}"].values)[0]
        text = EVENT_TEXT.get((vid, name), (f"{vid} {name}", f"{vid} {name}", f"{vid} event {name}"))
        out.append({"id": key, "var": vid, "name": text[0], "short": text[1], "threshold": text[2],
                    "available": True, "prob": _flat(p)})
    return out


def _flat(a):
    a = np.asarray(a)
    return a.reshape(a.shape[:-2] + (len(LAT) * len(LON),)).astype(np.float32)


def _afternoon_before(root: Path, init: datetime.datetime, members: list[str]):
    """The afternoon before today's Day 1 = yesterday's live run, Day 1 afternoon: (model, lat, lon) °C, or None."""
    rid = f"live-{init - datetime.timedelta(days=1):%Y%m%d}"
    if rid not in B.list_runs(root):
        return None
    arr, x = B.read_arrays(root, rid), B.read_meta(root, rid).get("_x", {})
    have = x.get("t12Models") or []
    if "t12_t2m" not in arr or any(m not in have for m in members):
        return None
    t = arr["t12_t2m"][[have.index(m) for m in members], 0]                  # (model, cells)
    return t.reshape(len(members), len(LAT), len(LON))


def heat_events(root: Path, init: datetime.datetime, t12: dict, w: xr.DataArray, static) -> tuple[list, dict, list]:
    """IMD heat-wave probabilities from the live models' 12 UTC temperatures (blend/heatwave.py).
    Returns (events, arrays, models used). Empty when no afternoon field or no static file."""
    from . import heatwave as HW
    from .geo import india_mask
    members = [m for m in w.model.values if m in t12]
    if not members or static is None:
        return [], {}, []
    india = india_mask(LAT, LON)
    cls = HW.cell_class(static, india)
    t = np.stack([t12[m].transpose("lead", "latitude", "longitude").values for m in members]) - 273.15
    normal = HW.normals_for(static, init, C.LEAD_DAYS)
    before = _afternoon_before(root, init, members)
    normal_before = HW.normals_for(static, init, [0])[0] if before is not None else None
    hw, sv = HW.event_flags(t, normal, cls, before, normal_before)
    ww = w.sel(model=members).transpose("model", "lead", "latitude", "longitude").values
    day1 = ("Day 1 is checked against yesterday's afternoon from the previous live run." if before is not None
            else "Day 1 is judged on its own afternoon: yesterday's live run is not kept or has no afternoon field.")
    arrays, events = {"t12_t2m": _flat(t)}, []
    for key, flags in (("heat", hw), ("heat_severe", sv)):
        arrays[f"p_{key}"] = _flat(HW.probability(flags, ww, india))
        events.append({"id": key, "var": "t2m", **HW.EVENTS[key], "available": True,
                       "note": f"{HW.NOTE} Models: {', '.join(m.upper() for m in members)}. {day1}"})
    return events, arrays, members


def live_regime_of(root: Path, init: datetime.datetime, data: dict):
    """(regime or None, z-scores, missing indices, note line) for the init day (blend/live_regime.py)."""
    from . import live_regime as LR
    clim = LR.load_clim()
    if clim is None:
        return None, {}, LR.COLS, ("Regime: season only; models/live_regime.nc (ERA5 index climatology) is missing: "
                                   "python -m blend.live_regime build-clim.")
    key = f"ana_{C.MSLP}"
    ana = data["ifs"][key].values if "ifs" in data and key in data["ifs"] else None
    regime, z, missing = LR.live_label(clim, LR.live_indices(root, init, LAT, LON, ana))
    zs = ", ".join(f"{k} {v:+.1f}" for k, v in z.items() if v is not None) or "none"
    note = (f"Regime of the init day: {REGIME_TEXT.get(regime, regime)} (same rules and ERA5 2003-2017 climatology as the "
            f"hindcasts; live proxies: yesterday's Day-1 blended rain and afternoon temperature, today's IFS analysis "
            f"pressure; z-scores {zs}). Weights do not depend on it: regime weights gave no held-out gain.")
    if missing:
        note += f" Not available yet: {', '.join(missing)} (needs earlier live runs), so those rules could not fire."
    return regime, z, missing, note


def run(bundles: str, init: datetime.datetime | None = None, workdir: str = "live_work", model_file: Path = MODEL_FILE,
        ncmrwf: dict[str, str] | None = None):
    """ncmrwf: {"ncum": path, "nepsg": path} to NCMRWF GRIB2 files of the same 00 UTC run (optional)."""
    t_start = time.time()
    root, work = Path(bundles), Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    model = xr.load_dataset(model_file)
    steps, data, t12 = [], {}, {}
    ncmrwf = {m: p for m, p in (ncmrwf or {}).items() if p}

    ecmwf_init = init or min(latest_ecmwf(m) for m in ECMWF_MODELS)
    init = ecmwf_init
    log(f"init {init:%Y-%m-%d} 00 UTC")
    for m in LIVE_MODELS:
        if m in NCMRWF_MODELS and m not in ncmrwf:
            continue                                              # not public: used only when files are given
        t0 = time.time()
        try:
            if m in NCMRWF_MODELS:
                data[m], afternoon, info = load_ncmrwf(ncmrwf[m], init)
                if afternoon is not None:
                    t12[m] = afternoon
                log(f"{m}: {info['members']} member(s), {info['skipped']} message(s) from other runs skipped")
            elif m == "gfs":
                if init > latest_gfs():
                    raise RuntimeError(f"GFS {init:%Y-%m-%d} 00 UTC not complete on NOMADS yet")
                data[m] = fetch_gfs(init, work)
            else:
                data[m] = fetch_ecmwf(m, init, work)
            steps.append({"name": f"fetch {m} 00 UTC Day 1-10", "status": "ok", "seconds": round(time.time() - t0, 2)})
            log(f"fetched {m}")
        except Exception as e:  # one model down must not stop the run
            steps.append({"name": f"fetch {m}", "status": "failed", "seconds": round(time.time() - t0, 2),
                          "note": repr(e)[:200]})
            log(f"{m} failed: {e!r}")
    if not data:
        raise SystemExit("no live model could be fetched")

    # afternoon (12 UTC) 2 m temperature for the IMD heat-wave rule (NCMRWF files carry their own, if any)
    for m in data:
        if m in NCMRWF_MODELS:
            continue
        t0 = time.time()
        try:
            t12[m] = fetch_gfs_afternoon(init, work) if m == "gfs" else fetch_ecmwf_afternoon(m, init, work)
            steps.append({"name": f"fetch {m} 12 UTC 2 m temperature (heat wave)", "status": "ok",
                          "seconds": round(time.time() - t0, 2)})
        except Exception as e:  # heat-wave guidance then leaves this model out
            steps.append({"name": f"fetch {m} 12 UTC 2 m temperature (heat wave)", "status": "failed",
                          "seconds": round(time.time() - t0, 2), "note": repr(e)[:200]})
            log(f"{m} afternoon failed: {e!r}")
    from .heatwave import load_static
    static = load_static()

    # verify earlier live runs against today's IFS analysis, update the online statistics (B4)
    t0 = time.time()
    state, rows = load_state(), []
    if "ifs" in data:
        state, rows = verify_and_update(root, init, data["ifs"], state)
        if rows:
            save_state(state)
    ver = append_verification(root, rows)
    steps.append({"name": f"verify {len(rows)} earlier forecasts against the IFS analysis; update online weights (B4)",
                  "status": "ok" if "ifs" in data else "skipped", "seconds": round(time.time() - t0, 2)})

    season = C.SEASON_OF_MONTH[init.month]
    regime, regime_z, regime_missing, regime_note = live_regime_of(root, init, data)
    arrays, models_by_var, vars_done, events, n_online = {}, {}, [], [], {}
    heat, heat_models = [], []
    t0 = time.time()
    for vid, wb2 in VAR_IDS.items():
        if f"cov_{vid}" not in model:
            continue
        fcs = {m: ds[wb2] * (1000.0 if vid == "rain" else 1.0) for m, ds in data.items()}   # rain: m -> mm
        a, w, fc, n_online[vid] = blend_var(vid, fcs, model, state, season)
        arrays.update(a)
        models_by_var[vid] = list(fcs)
        vars_done.append(vid)
        for ev in extreme_probs(vid, fc, w, model):
            arrays[f"p_{ev['id']}"] = ev.pop("prob")
            events.append(ev)
        if vid == "t2m":
            heat, heat_arrays, heat_models = heat_events(root, init, t12, w, static)
            arrays.update(heat_arrays)
        if vid == "wind":   # blended wind components for the particle layer
            uv = {c: sum(data[m][c].values * w.sel(model=m).values for m in fcs) for c in ("u10", "v10")}
            arrays["u10"], arrays["v10"] = _flat(uv["u10"]), _flat(uv["v10"])
    rung = "B4" if any(v > 0 for v in n_online.values()) else "B2c"
    steps.append({"name": f"blend ({rung}) + extreme probabilities", "status": "ok", "seconds": round(time.time() - t0, 2)})

    no_twin = [m.upper().replace("NEPSG", "NEPS-G") for m in data if m in PRIOR_INFLATION]
    notes = [
        f"Live run: {', '.join(m.upper() for m in data)} 00 UTC forecasts, averaged onto the 1.5° training grid.",
        "Weights start from learned training skill (IFS <- HRES, AIFS <- GraphCast) and move toward each model's own "
        "live record as days are verified (B4, ~20-day memory; each model's mean error against the analysis is "
        "removed first, so only its random error shapes the weights)."
        + (f" {' and '.join(no_twin)} {'has' if len(no_twin) == 1 else 'have'} no training counterpart: "
           f"{'it starts' if len(no_twin) == 1 else 'each starts'} from HRES skill with 1.5x the error, so it carries "
           "little weight until its own verified days accumulate." if no_twin else ""),
        f"Verified days behind today's weights (mean over cells and leads): "
        + ", ".join(f"{v} {n_online.get(v, 0):.1f}" for v in VERIFIED) + ". Rain has no live truth: training prior only.",
        "Live truth is the IFS analysis (step 0), which favours IFS; hindcast scorecards use ERA5 / CHIRPS.",
        "Bias correction: IFS uses the HRES seasonal bias; the other models are not bias-corrected.",
        "Rain weights over the sea are equal (rain truth is land only, so there is no learned skill there).",
        "Extremes: each live model votes at its training counterpart's quantile threshold; calibrated on training "
        "years for the IFS/AIFS pair.",
        regime_note,
    ] + ver
    failed = [s for s in steps if s["status"] == "failed"]
    run_id = f"live-{init:%Y%m%d}"
    meta = {
        "id": run_id, "kind": "live", "init": f"{init:%Y-%m-%d}T00:00Z",
        "status": "partial" if failed else "ok", "models": list(data),
        "grid": {"lat0": float(LAT[0]), "lon0": float(LON[0]), "step": 1.5, "ny": len(LAT), "nx": len(LON)},
        "leads": [int(x) for x in C.LEAD_DAYS], "vars": vars_done, "modelsByVar": models_by_var,
        "regime": {"season": season, "basis": "init",
                   "label": REGIME_TEXT.get(regime, regime) if regime else f"{season} (season only)"},
        "rung": rung, "steps": steps, "provenance": "measured", "notes": notes,
        "extremes": events + (heat or [{**HEAT_EVENT, "note": "Heat-wave guidance unavailable today: "
                                        + ("no 12 UTC temperature could be fetched." if static is not None
                                           else "models/live_static.nc (normals) is missing.")}]),
        "_x": {"sets": {v: SET_OF[v] for v in vars_done}, "proxy": PROXY, "k": float(K_ONLINE),
               "nSeason": {}, "nRegime": {}, "nOnline": {v: round(n, 1) for v, n in n_online.items()},
               "extremeCalibrated": bool(events), "extremeMethod":
                   "quantile-mapped weighted vote of the live models (training-counterpart thresholds), calibrated",
               "modelFile": model.attrs.get("source", ""),
               "t12Models": heat_models,
               "regime": regime, "regimeZ": regime_z, "regimeMissing": regime_missing,
               "uncalibrated": [e["id"] for e in heat],
               "eventMethod": {e["id"]: "IMD rule per model on 12 UTC 2 m temperature; probability = temperature "
                                        "weights of the models meeting it (uncalibrated)" for e in heat},
               "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
    }
    B.write_run(root, meta, arrays)
    meta["steps"].append({"name": "write bundle", "status": "ok", "seconds": round(time.time() - t_start, 2)})
    B.write_meta(root, meta)
    prune(root)
    B.write_index(root)
    log(f"wrote {bundles}/runs/{run_id} (rung {rung}; {', '.join(vars_done)}; models {', '.join(data)}; "
        f"{len(events)} extreme layers; verified {len(rows)} forecasts)")
    return run_id


def append_verification(root: Path, rows: list[dict]) -> list[str]:
    """Keep a rolling log of live forecast errors (bundles/live_verification.json); return note lines."""
    path = root / "live_verification.json"
    log_ = json.loads(path.read_text()) if path.exists() else []
    log_ = [r for r in log_ if (r["run"], r["valid"], r["var"]) not in {(x["run"], x["valid"], x["var"]) for x in rows}]
    log_ = (log_ + rows)[-2000:]
    path.write_text(json.dumps(B._clean(log_), indent=1))
    if not log_:
        return ["Live verification: no earlier live forecast has reached its valid date yet."]
    df = pd.DataFrame(log_)
    lines = []
    for vid, unit in (("t2m", "°C"), ("wind", "m/s"), ("mslp", "hPa")):
        d = df[df["var"] == vid]
        if d.empty:
            continue
        cols = [c for c in ("blend", "ifs", "aifs", "gfs") if c in d and d[c].notna().any()]
        mean = d.groupby("lead")[cols].mean()
        best_lead = mean.index.min()
        txt = ", ".join(f"{c} {mean.loc[best_lead, c]:.2f}" for c in cols)
        lines.append(f"Live verification {vid} (RMSE {unit}, Day {best_lead}, {int((d.lead == best_lead).sum())} "
                     f"day(s) vs IFS analysis): {txt}.")
    return lines


def prune(root: Path, keep: int = KEEP_LIVE):
    import shutil
    live = sorted(r for r in B.list_runs(root) if r.startswith("live-"))
    for r in live[:-keep]:
        shutil.rmtree(root / "runs" / r)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-model")
    b.add_argument("--art", required=True, help="artifacts dir holding S1/ and S2/ from run_all.py")
    b.add_argument("--cache", help="training cache dir: adds the extreme-event tables")
    r = sub.add_parser("run")
    r.add_argument("--bundles", default="bundles")
    r.add_argument("--date", help="init date YYYY-MM-DD (default: latest complete 00 UTC run)")
    r.add_argument("--work", default="live_work")
    r.add_argument("--ncum", default=os.environ.get("BLEND_NCUM_DIR"),
                   help="NCUM GRIB2 file or folder for the same 00 UTC run (env BLEND_NCUM_DIR)")
    r.add_argument("--nepsg", default=os.environ.get("BLEND_NEPSG_DIR"),
                   help="NEPS-G GRIB2 file or folder, all members (env BLEND_NEPSG_DIR)")
    a = ap.parse_args(argv)
    if a.cmd == "build-model":
        build_model(a.art, a.cache)
    else:
        init = datetime.datetime.strptime(a.date, "%Y-%m-%d") if a.date else None
        run(a.bundles, init, a.work, ncmrwf={"ncum": a.ncum, "nepsg": a.nepsg})


if __name__ == "__main__":
    main()
