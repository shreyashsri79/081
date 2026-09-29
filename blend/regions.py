"""Verification regions for the scorecard breakdown (BACKEND_BUILD_PLAN.md T5; workflow §C8)."""

import numpy as np

REGIONS = {                          # (lat0, lat1, lon0, lon1, surface)
    "North-west": (24, 35, 68, 78, "land"),
    "Central": (18, 26, 74, 86, "land"),
    "North-east": (22, 29, 89, 97, "land"),
    "South peninsula": (8, 18, 74, 81, "land"),
    "Bay of Bengal": (10, 21, 82, 92, "sea"),
    "Arabian Sea": (8, 20, 64, 73, "sea"),
}
MIN_CELLS = 3


def region_mask(lat: np.ndarray, lon: np.ndarray, name: str, india: np.ndarray) -> np.ndarray:
    """(len(lat), len(lon)) bool. Land = inside India; sea = outside India and south of 22.5° N."""
    lat0, lat1, lon0, lon1, surface = REGIONS[name]
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    box = (la >= lat0) & (la <= lat1) & (lo >= lon0) & (lo <= lon1)
    return box & (india if surface == "land" else (~india & (la < 22.5)))
