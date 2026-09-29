"""IMD heat-wave guidance for the live run (IMD FAQ on heat wave, research note R11).

IMD rule, per station maximum temperature (Tmax), declared for a met sub-division:
  plains  Tmax >= 40 °C and departure from normal 4.5-6.4 °C (heat wave) or > 6.4 °C (severe);
          or actual Tmax >= 45 °C (heat wave) / >= 47 °C (severe)
  hills   Tmax >= 30 °C and the same departures
  coast   Tmax >= 37 °C and departure >= 4.5 °C (heat wave; the FAQ gives no severe level for the coast)
  declared when met at >= 2 stations of a sub-division on 2 consecutive days, on the second day.

What this module does on the 1.5° grid (repeated in every bundle's event note):
  Tmax      -> 2 m temperature at 12 UTC (17:30 IST), a cell mean. It runs below a station's Tmax, so the
               absolute thresholds (40 / 45 / 47 °C) are met less often than at stations.
  normal    -> ERA5 1990-2019 climatology of 2 m temperature at 12 UTC, same cell and day of year.
  hills     -> cell-mean orography >= 1000 m; coast -> an Indian cell touching the sea; plains -> other Indian cells.
  stations  -> cells; "2 consecutive days" -> the day and the day before, both in the forecast (Day 1 takes the day
               before from yesterday's live run when it is kept, else Day 1 is judged on one day).
  probability = sum of today's temperature weights (B2c / B4) of the live models that meet the rule.
               Uncalibrated: training holds no afternoon truth to calibrate against.

    python -m blend.heatwave build-static        # once: writes models/live_static.nc (needs zarr + gcsfs)
"""

import argparse
import datetime
from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path(__file__).resolve().parent.parent
STATIC_FILE = ROOT / "models" / "live_static.nc"
WB2 = "gs://weatherbench2/datasets"
CLIM_STORE = f"{WB2}/era5-hourly-climatology/1990-2019_6h_240x121_equiangular_with_poles_conservative.zarr"
ERA5_STORE = f"{WB2}/era5/1959-2023_01_10-6h-240x121_equiangular_with_poles_conservative.zarr"
G = 9.80665
HILL_M = 1000.0
PLAINS, HILLS, COAST = 0, 1, 2
AFTERNOON_HOUR = 12                                      # UTC; Day d's afternoon is step 24 d - 12

EVENTS = {
    "heat": {"name": "Heat wave (IMD rule)", "short": "Heat wave",
             "threshold": "IMD heat-wave rule on 12 UTC 2 m temperature, 2 consecutive days"},
    "heat_severe": {"name": "Severe heat wave (IMD rule)", "short": "Severe heat",
                    "threshold": "IMD severe heat-wave rule on 12 UTC 2 m temperature, 2 consecutive days"},
}
NOTE = ("IMD rule applied per 1.5° cell to 12 UTC (17:30 IST) 2 m temperature; normal = ERA5 1990-2019 12 UTC "
        "climatology; hills = orography >= 1000 m, coast = cells touching the sea; stations -> cells. A cell mean at "
        "17:30 IST runs below station Tmax, so absolute thresholds trigger less often than at stations. "
        "Probability = temperature weights of the models meeting the rule; uncalibrated.")


# ------------------------------------------------------------------ static fields (one-off download)

def build_static(lat: np.ndarray, lon: np.ndarray, out: Path = STATIC_FILE) -> Path:
    """Normal 12 UTC 2 m temperature by day of year, orography and land-sea mask on the live cells."""
    opts = {"token": "anon"}
    clim = xr.open_zarr(CLIM_STORE, storage_options=opts)["2m_temperature"].sel(hour=AFTERNOON_HOUR)
    era5 = xr.open_zarr(ERA5_STORE, storage_options=opts)[["geopotential_at_surface", "land_sea_mask"]]
    def pick(da):   # store coordinates differ from ours by float rounding: nearest cell, then our exact values
        da = da.sel(latitude=lat, longitude=lon, method="nearest", tolerance=0.01)
        return da.assign_coords(latitude=lat, longitude=lon)

    ds = xr.Dataset({
        "t12_normal": pick(clim).transpose("dayofyear", "latitude", "longitude").load() - 273.15,
        "orography": pick(era5["geopotential_at_surface"]).transpose("latitude", "longitude").load() / G,
        "land_sea_mask": pick(era5["land_sea_mask"]).transpose("latitude", "longitude").load(),
    })
    for v in ds.variables:
        ds[v].attrs, ds[v].encoding = {}, {}
    ds["t12_normal"].attrs["units"] = "degC"
    ds["orography"].attrs["units"] = "m"
    ds.attrs = {"source": f"{CLIM_STORE} (hour 12); {ERA5_STORE} (static fields)",
                "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    out.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(out)
    return out


def load_static(path: Path = STATIC_FILE) -> xr.Dataset | None:
    return xr.load_dataset(path) if Path(path).exists() else None


# ------------------------------------------------------------------ the rule

def cell_class(static: xr.Dataset, india: np.ndarray) -> np.ndarray:
    """(lat, lon) int: PLAINS / HILLS / COAST for cells inside India, -1 elsewhere. Hills win over coast."""
    sea = static["land_sea_mask"].values < 0.5
    pad = np.pad(sea, 1, constant_values=False)
    near_sea = np.zeros_like(sea)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            near_sea |= pad[1 + di:pad.shape[0] - 1 + di, 1 + dj:pad.shape[1] - 1 + dj]
    cls = np.full(sea.shape, PLAINS, dtype=np.int8)
    cls[near_sea] = COAST
    cls[static["orography"].values >= HILL_M] = HILLS
    cls[~india] = -1
    return cls


def daily_flags(t: np.ndarray, normal: np.ndarray, cls: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """One afternoon: t, normal in °C, (..., lat, lon); cls (lat, lon). Returns (heat wave, severe) booleans;
    severe implies heat wave. NaN temperatures give False."""
    dep = t - normal
    plains, hills, coast = cls == PLAINS, cls == HILLS, cls == COAST
    with np.errstate(invalid="ignore"):
        hw = (plains & (((t >= 40) & (dep >= 4.5)) | (t >= 45))
              | hills & (t >= 30) & (dep >= 4.5)
              | coast & (t >= 37) & (dep >= 4.5))
        severe = (plains & (((t >= 40) & (dep > 6.4)) | (t >= 47))
                  | hills & (t >= 30) & (dep > 6.4))
    return hw, severe


def normals_for(static: xr.Dataset, init: datetime.datetime, leads) -> np.ndarray:
    """(lead, lat, lon) normal 12 UTC temperature of each lead's afternoon (12 UTC on init + lead - 1 days;
    lead 0 = the afternoon before init)."""
    days = [(init + datetime.timedelta(days=int(d) - 1)).timetuple().tm_yday for d in leads]
    return static["t12_normal"].sel(dayofyear=days).values


def event_flags(t12: np.ndarray, normal: np.ndarray, cls: np.ndarray,
                t12_before: np.ndarray | None = None, normal_before: np.ndarray | None = None):
    """t12: (model, lead, lat, lon) afternoon temperatures in °C for leads 1..L; normal: (lead, lat, lon);
    t12_before: (model, lat, lon) the afternoon before Day 1 (from yesterday's run) with its normal (lat, lon),
    or None, in which case Day 1 is judged on its own afternoon.
    Returns (heat wave, severe), each (model, lead, lat, lon): the rule met on the day AND the day before."""
    hw, sv = daily_flags(t12, normal[None], cls)
    prev_hw, prev_sv = np.ones_like(hw), np.ones_like(sv)
    prev_hw[:, 1:], prev_sv[:, 1:] = hw[:, :-1], sv[:, :-1]
    if t12_before is not None:
        prev_hw[:, 0], prev_sv[:, 0] = daily_flags(t12_before, normal_before[None], cls)
    return hw & prev_hw, sv & prev_sv


def probability(flags: np.ndarray, w: np.ndarray, india: np.ndarray) -> np.ndarray:
    """flags (model, lead, lat, lon) bool, w (model, lead, lat, lon) weights summing to 1 -> (lead, lat, lon);
    NaN outside India (the rule is defined for Indian stations only)."""
    p = np.nansum(flags * np.nan_to_num(w), axis=0) / np.maximum(np.nansum(np.nan_to_num(w), axis=0), 1e-9)
    return np.where(india[None], p, np.nan)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-static", help="download normals + orography for the live cells (needs zarr, gcsfs)")
    a = ap.parse_args(argv)
    if a.cmd == "build-static":
        from .live import LAT, LON
        print(build_static(LAT, LON))


if __name__ == "__main__":
    main()
