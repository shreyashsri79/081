"""Deck-ready figures from a finished run's artifacts (no re-training, no download).

    python make_deck_figures.py path/to/artifacts        -> path/to/artifacts/deck/*.png
"""

import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from blend import products as P

NICE = {"2m_temperature": ("Temperature (2 m)", "K"), "10m_wind_speed": ("Wind speed (10 m)", "m/s"),
        "mean_sea_level_pressure": ("Sea-level pressure", "Pa"), "total_precipitation_24hr": ("24 h rain", "mm")}


def gain_bars(card, path):
    """% RMSE change of the shipped blend vs the best single model, per lead, per variable."""
    vars_ = list(dict.fromkeys(card["var"]))
    fig, ax = plt.subplots(figsize=(7.5, 3.8), constrained_layout=True)
    width = 0.8 / len(vars_)
    colours = ["#C1121F", "#0072B2", "#009E73", "#E69F00"]
    for i, v in enumerate(vars_):
        c = card[(card["var"] == v) & (card.rung == "B3s")].sort_values("lead_day")
        x = c.lead_day + (i - (len(vars_) - 1) / 2) * width
        ax.bar(x, c.pct_vs_B0, width, color=colours[i], label=NICE.get(v, (v,))[0])
        # 95 % CI of the RMSE difference, converted to % of the reference RMSE
        ref = card[(card["var"] == v) & (card.rung == "B0")].set_index("lead_day").rmse
        lo = 100 * c.set_index("lead_day").lo_vs_B0 / ref
        hi = 100 * c.set_index("lead_day").hi_vs_B0 / ref
        ax.errorbar(x, c.pct_vs_B0, yerr=[c.pct_vs_B0.values - lo.values, hi.values - c.pct_vs_B0.values],
                    fmt="none", ecolor="k", capsize=2, lw=0.8)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(range(1, 11))
    ax.set_xlabel("forecast lead (days)")
    ax.set_ylabel("RMSE change vs best single model (%)")
    ax.set_title("Blend error vs best single model, held-out years (lower = better)")
    ax.legend(frameon=False)
    fig.savefig(path, dpi=200)
    plt.close(fig)


def main(art):
    """art: one set folder, e.g. artifacts/S1."""
    out = os.path.join(art, "deck")
    os.makedirs(out, exist_ok=True)
    card = pd.read_csv(os.path.join(art, [f for f in os.listdir(art) if f.startswith("scorecard_")][0]))
    gain_bars(card, f"{out}/gain_by_lead.png")
    for f in sorted(os.listdir(art)):
        if not (f.startswith("weights_") and f.endswith(".nc")):
            continue
        ds = xr.load_dataset(os.path.join(art, f))
        var = [v for v in NICE if v.replace("_", "") in f][0]
        name, _ = NICE[var]
        tag = var.replace("_", "")
        w = ds["w_B3s"].sel(lead=3, season="JJAS")
        P.dominant_map(w, f"{name}: most-trusted model\nDay 3, monsoon season (JJAS)", f"{out}/dominant_{tag}.png")
        P.weight_maps(ds["w_B2"].sel(lead=3), f"{name}: weight given to each model, Day 3", f"{out}/weights_{tag}.png")
        models = [str(m) for m in ds.model.values]
        P.rmse_vs_lead(card, var, [f"m:{m}" for m in models] + ["B0bc", "B3s"], f"{out}/rmse_vs_lead_{tag}.png")
    print("wrote", sorted(os.listdir(out)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/kaggle/working/artifacts/S1")
