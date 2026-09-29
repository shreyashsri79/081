"""C12 NCMRWF adapters: NCUM (deterministic) and NEPS-G (ensemble) GRIB2 files -> the live run's fields.

NCUM and NEPS-G are not public. When NCMRWF shares a 00 UTC run as GRIB2 (one file or many, any step layout),
point the live run at it:

    python -m blend.live run --ncum /data/ncum/2026093000 --nepsg /data/nepsg/2026093000

Fields are found by GRIB shortName, so file names and message order do not matter. NEPS-G members
(perturbationNumber) are averaged into an ensemble mean. Each source then enters the blend like GFS: it has no
training counterpart, so its prior is HRES skill with a 1.5x error and it earns weight only from its own verified
days (B4). Stdlib + numpy + eccodes; the output is the same shape blend/live.py builds from ECMWF and GFS.
"""

import datetime
from collections import defaultdict
from pathlib import Path

import numpy as np
import xarray as xr

ALIASES = {"2t": {"2t", "t2m", "tmp2m"}, "10u": {"10u", "u10"}, "10v": {"10v", "v10"},
           "msl": {"msl", "prmsl", "mslp"}, "tp": {"tp", "apcp"}}
CANON = {alias: key for key, names in ALIASES.items() for alias in names}
HOURS = list(range(0, 241, 24))
AFTERNOON = [24 * d - 12 for d in range(1, 11)]


def field_of(g) -> str | None:
    """Canonical field of a GRIB message: by shortName, else by the WMO GRIB2 parameter numbers and level, because a
    centre's local tables (NCMRWF's included) may leave shortName 'unknown'."""
    import eccodes
    key = CANON.get(str(eccodes.codes_get(g, "shortName")).lower())
    if key or eccodes.codes_get(g, "editionNumber") != 2:
        return key
    d, c, n = (eccodes.codes_get(g, k) for k in ("discipline", "parameterCategory", "parameterNumber"))
    surface = eccodes.codes_get(g, "typeOfFirstFixedSurface")
    level = eccodes.codes_get(g, "level") if eccodes.codes_is_defined(g, "level") else None
    if d != 0:
        return None
    if (c, n) == (1, 8):                                          # total precipitation, kg m-2
        return "tp"
    if (c, n) == (0, 0) and surface == 103 and level == 2:        # temperature, 2 m above ground
        return "2t"
    if (c, n) in ((2, 2), (2, 3)) and surface == 103 and level == 10:
        return "10u" if n == 2 else "10v"
    if (c, n) == (3, 1) or ((c, n) == (3, 0) and surface == 101):  # pressure reduced to MSL / at MSL
        return "msl"
    return None


def grib_files(path: str | Path) -> list[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    files = sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in {".grib", ".grib2", ".grb", ".grb2"})
    if not files:
        raise FileNotFoundError(f"no GRIB files (.grib2 / .grb2 / .grib / .grb) under {p}")
    return files


def read_messages(files: list[Path], init: datetime.datetime):
    """{(field, member): {"inst": {hour: values}, "acc": {(start, end): values}}}, plus lat, lon and a skip count.
    Messages from another init date or time are skipped (and counted)."""
    import eccodes
    out = defaultdict(lambda: {"inst": {}, "acc": {}})
    lat = lon = None
    skipped = 0
    want_date, want_time = int(f"{init:%Y%m%d}"), init.hour * 100
    for f in files:
        with open(f, "rb") as fh:
            while (g := eccodes.codes_grib_new_from_file(fh)) is not None:
                try:
                    key = field_of(g)
                    if key is None:
                        continue
                    if (eccodes.codes_get(g, "dataDate"), eccodes.codes_get(g, "dataTime")) != (want_date, want_time):
                        skipped += 1
                        continue
                    member = eccodes.codes_get(g, "perturbationNumber") if eccodes.codes_is_defined(g, "perturbationNumber") else 0
                    ni, nj = eccodes.codes_get(g, "Ni"), eccodes.codes_get(g, "Nj")
                    vals = eccodes.codes_get_values(g).reshape(nj, ni).astype("float64")
                    missing = eccodes.codes_get(g, "missingValue")
                    if eccodes.codes_get(g, "bitmapPresent"):
                        vals[vals == missing] = np.nan
                    la = np.asarray(eccodes.codes_get_array(g, "distinctLatitudes"))
                    lo = np.asarray(eccodes.codes_get_array(g, "distinctLongitudes"))
                    if eccodes.codes_get(g, "jScansPositively") == 0:
                        la = np.sort(la)[::-1]
                    lat, lon = la, lo
                    start, end = eccodes.codes_get(g, "startStep"), eccodes.codes_get(g, "endStep")
                    if key == "tp":
                        units = str(eccodes.codes_get(g, "units")).strip()
                        out[(key, member)]["acc"][(int(start), int(end))] = vals if units == "m" else vals / 1000.0
                    else:
                        out[(key, member)]["inst"][int(end)] = vals
                finally:
                    eccodes.codes_release(g)
    return out, lat, lon, skipped


def accumulated(acc: dict, hours: list[int]) -> dict:
    """Rain accumulated since the start (metres) at each hour, from (0, h) totals or chained interval buckets."""
    out = {0: None}
    for h in hours:
        if h == 0:
            continue
        if (0, h) in acc:
            out[h] = acc[(0, h)]
            continue
        total, t = None, 0                    # chain buckets 0-a, a-b, ... up to h
        while t < h:
            nxt = [(a, b) for (a, b) in acc if a == t and b <= h]
            if not nxt:
                raise ValueError(f"rain accumulation to +{h} h cannot be built (no bucket starting at +{t} h)")
            a, b = max(nxt, key=lambda ab: ab[1])
            total = acc[(a, b)] if total is None else total + acc[(a, b)]
            t = b
        out[h] = total
    return out


def load(path: str | Path, init: datetime.datetime):
    """GRIB2 run -> (fields at 0.25°-or-native resolution with an 'hours' axis, afternoon 2 m temperature or None, info).
    fields: {"2t", "10u", "10v", "msl": DataArray (hours, lat, lon); "tp": accumulation in m}; ensemble mean if
    several members."""
    msgs, lat, lon, skipped = read_messages(grib_files(path), init)
    if lat is None:
        raise ValueError(f"no usable 2t / 10u / 10v / msl / tp messages for {init:%Y-%m-%d %H} UTC in {path}")
    members = sorted({m for (_, m) in msgs})
    coords = {"latitude": lat, "longitude": lon}

    def stack(key, hours, inst=True):
        per_member = []
        for m in members:
            got = msgs.get((key, m))
            if got is None:
                raise ValueError(f"{key} missing for member {m}")
            if inst:
                miss = [h for h in hours if h not in got["inst"]]
                if miss:
                    raise ValueError(f"{key} missing at +{miss} h (member {m})")
                per_member.append(np.stack([got["inst"][h] for h in hours]))
            else:
                acc = accumulated(got["acc"], hours)
                shape = next(iter(got["acc"].values())).shape
                per_member.append(np.stack([np.zeros(shape) if acc[h] is None else acc[h] for h in hours]))
        mean = np.nanmean(np.stack(per_member), axis=0) if len(per_member) > 1 else per_member[0]
        return xr.DataArray(mean, dims=("hours", "latitude", "longitude"), coords={"hours": hours, **coords})

    have_0 = all(0 in msgs.get((k, members[0]), {"inst": {}})["inst"] for k in ("2t", "10u", "10v", "msl"))
    hours = HOURS if have_0 else HOURS[1:]
    fields = {k: stack(k, hours) for k in ("2t", "10u", "10v", "msl")}
    fields["tp"] = stack("tp", HOURS, inst=False)
    try:
        t12 = stack("2t", AFTERNOON)
    except ValueError:
        t12 = None
    info = {"members": len(members), "skipped": skipped, "analysis": have_0}
    return fields, t12, info
