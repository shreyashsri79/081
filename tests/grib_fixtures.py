"""Write small GRIB2 files for adapter tests (needs eccodes). Values are (lat, lon) arrays, latitude ascending."""

import numpy as np


def write_field(fh, short: str, values: np.ndarray, lat: np.ndarray, lon: np.ndarray, date: int, step: int,
                start: int | None = None, member: int | None = None, units_mm: bool = True):
    """One GRIB2 message. short in {'2t', '10u', '10v', 'msl', 'tp'}; tp takes start (accumulation start hour).
    Rain values are written in kg m-2 (mm) as WMO 0/1/8 (shortName 'unknown' outside NCEP, as from a centre with
    its own tables) when units_mm, else as ECMWF 'tp' in metres."""
    import eccodes
    accum = short == "tp"
    template = (11 if accum else 1) if member is not None else (8 if accum else 0)
    g = eccodes.codes_grib_new_from_samples("GRIB2")
    try:
        eccodes.codes_set(g, "productDefinitionTemplateNumber", template)
        eccodes.codes_set(g, "dataDate", date)
        eccodes.codes_set(g, "dataTime", 0)
        eccodes.codes_set(g, "stepUnits", 1)
        if member is not None:
            eccodes.codes_set(g, "typeOfEnsembleForecast", 3)
            eccodes.codes_set(g, "perturbationNumber", member)
            eccodes.codes_set(g, "numberOfForecastsInEnsemble", 23)
        if accum:
            eccodes.codes_set(g, "typeOfStatisticalProcessing", 1)
            eccodes.codes_set(g, "startStep", start or 0)
            eccodes.codes_set(g, "endStep", step)
            if units_mm:
                eccodes.codes_set(g, "discipline", 0)
                eccodes.codes_set(g, "parameterCategory", 1)
                eccodes.codes_set(g, "parameterNumber", 8)       # APCP, kg m-2
                eccodes.codes_set(g, "typeOfFirstFixedSurface", 1)
            else:
                eccodes.codes_set(g, "shortName", "tp")
        else:
            eccodes.codes_set(g, "step", step)
            eccodes.codes_set(g, "shortName", short)
        eccodes.codes_set(g, "gridType", "regular_ll")
        eccodes.codes_set(g, "Ni", len(lon))
        eccodes.codes_set(g, "Nj", len(lat))
        eccodes.codes_set(g, "jScansPositively", 0)             # north to south, like most centres
        eccodes.codes_set(g, "latitudeOfFirstGridPointInDegrees", float(lat[-1]))
        eccodes.codes_set(g, "latitudeOfLastGridPointInDegrees", float(lat[0]))
        eccodes.codes_set(g, "longitudeOfFirstGridPointInDegrees", float(lon[0]))
        eccodes.codes_set(g, "longitudeOfLastGridPointInDegrees", float(lon[-1]))
        eccodes.codes_set(g, "iDirectionIncrementInDegrees", float(lon[1] - lon[0]))
        eccodes.codes_set(g, "jDirectionIncrementInDegrees", float(lat[1] - lat[0]))
        eccodes.codes_set(g, "bitsPerValue", 24)
        eccodes.codes_set_values(g, np.asarray(values, dtype="float64")[::-1].reshape(-1))
        eccodes.codes_write(g, fh)
    finally:
        eccodes.codes_release(g)
