"""NCUM / NEPS-G GRIB2 adapter (blend/adapters.py) on generated files in the layouts NCMRWF may use."""

import datetime

import numpy as np
import pytest

pytest.importorskip("eccodes")

from blend import adapters as A  # noqa: E402
from blend import config as C  # noqa: E402
from blend import live as L  # noqa: E402
from tests.grib_fixtures import write_field  # noqa: E402

LAT = np.arange(4.0, 41.01, 0.5)
LON = np.arange(64.0, 101.01, 0.5)
ONES = np.ones((len(LAT), len(LON)))
INIT = datetime.datetime(2026, 9, 30)
DATE = 20260930


def ncum_like(folder, skip_hour=None):
    """One file per 12 h step: 2t every 12 h, wind and pressure every 24 h, rain as 24 h buckets in kg m-2 (APCP),
    plus one stray message from yesterday's run."""
    folder.mkdir()
    for h in range(0, 241, 12):
        if h == skip_hour:
            continue
        with open(folder / f"ncum_{DATE}00_f{h:03d}.grib2", "wb") as fh:
            write_field(fh, "2t", (300.0 + h / 24) * ONES, LAT, LON, DATE, h)
            if h % 24 == 0:
                write_field(fh, "10u", 3.0 * ONES, LAT, LON, DATE, h)
                write_field(fh, "10v", 4.0 * ONES, LAT, LON, DATE, h)
                write_field(fh, "msl", 100000.0 * ONES, LAT, LON, DATE, h)
                if h:
                    write_field(fh, "tp", 5.0 * ONES, LAT, LON, DATE, h, start=h - 24)
    with open(folder / "stray.grib2", "wb") as fh:
        write_field(fh, "2t", 999.0 * ONES, LAT, LON, DATE - 1, 24)


def test_ncum_layout_to_training_grid(tmp_path):
    ncum_like(tmp_path / "ncum")
    fields, t12, info = A.load(tmp_path / "ncum", INIT)
    assert info == {"members": 1, "skipped": 1, "analysis": True}
    ds, t12g, _ = L.load_ncmrwf(str(tmp_path / "ncum"), INIT)
    assert list(ds.lead.values) == list(C.LEAD_DAYS)
    assert np.allclose(ds[C.T2M].sel(lead=1), 301.0, atol=1e-3)          # +24 h
    assert np.allclose(ds[C.WIND], 5.0, atol=1e-3)                          # hypot(3, 4)
    assert np.allclose(ds[C.RAIN], 0.005, atol=1e-6)                        # 5 mm per day, in metres
    assert np.allclose(ds[f"ana_{C.T2M}"], 300.0, atol=1e-3)                # step 0 = analysis
    assert ds[C.T2M].shape == (10, len(L.LAT), len(L.LON))
    assert np.allclose(t12g.sel(lead=1), 300.5, atol=1e-3)                  # +12 h = Day 1 afternoon


def test_nepsg_members_are_averaged(tmp_path):
    folder = tmp_path / "nepsg"
    folder.mkdir()
    with open(folder / "nepsg_all.grb2", "wb") as fh:
        for member, offset in ((1, -1.0), (2, 0.0), (3, 1.0)):
            for h in range(0, 241, 24):
                write_field(fh, "2t", (300.0 + offset) * ONES, LAT, LON, DATE, h, member=member)
                write_field(fh, "10u", (2.0 + offset) * ONES, LAT, LON, DATE, h, member=member)
                write_field(fh, "10v", 0.0 * ONES, LAT, LON, DATE, h, member=member)
                write_field(fh, "msl", 101000.0 * ONES, LAT, LON, DATE, h, member=member)
                if h:   # ECMWF style: total since the start, metres
                    write_field(fh, "tp", 0.002 * h / 24 * ONES, LAT, LON, DATE, h, start=0, member=member,
                                units_mm=False)
    fields, t12, info = A.load(folder, INIT)
    assert info["members"] == 3 and t12 is None                             # no 12 UTC steps in these files
    ds, _, _ = L.load_ncmrwf(str(folder), INIT)
    assert np.allclose(ds[C.T2M], 300.0, atol=1e-3)
    assert np.allclose(ds[C.RAIN], 0.002, atol=1e-6)


def test_missing_step_is_an_error(tmp_path):
    ncum_like(tmp_path / "ncum", skip_hour=120)
    with pytest.raises(ValueError, match=r"\+\[120\] h"):
        A.load(tmp_path / "ncum", INIT)


def test_no_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        A.load(tmp_path, INIT)


def test_rain_buckets_chain():
    b = {(0, 6): 1.0, (6, 24): 2.0, (24, 48): 4.0}
    acc = A.accumulated(b, [0, 24, 48])
    assert acc[24] == 3.0 and acc[48] == 7.0 and acc[0] is None
    with pytest.raises(ValueError):
        A.accumulated({(0, 6): 1.0}, [24])
