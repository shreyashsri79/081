"""C9 Products: weight maps, dominant-model map, where-the-blend-wins map."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

# One fixed colour per model across every chart (Okabe-Ito)
MODEL_COLOURS = {"hres": "#0072B2", "graphcast": "#E69F00", "pangu": "#009E73",
                 "fuxi": "#CC79A7", "gencast": "#D55E00", "aifs": "#56B4E9", "gfs": "#999999"}


def _coast(ax):
    try:
        import cartopy.io.shapereader as shp
        from shapely.geometry import box
        clip = box(60, 0, 105, 45)
        for g in shp.Reader(shp.natural_earth("50m", "physical", "coastline")).geometries():
            g = g.intersection(clip)
            for line in getattr(g, "geoms", [g]):
                if not line.is_empty:
                    x, y = line.xy
                    ax.plot(x, y, color="k", lw=0.6)
    except Exception:
        pass  # coastlines are cosmetic; plots still work without cartopy or offline


def weight_maps(w: xr.DataArray, title: str, path: str):
    """One panel per model; w dims (model, latitude, longitude)."""
    models = list(w.model.values)
    fig, axes = plt.subplots(1, len(models), figsize=(4.2 * len(models), 4), constrained_layout=True)
    for ax, m in zip(np.atleast_1d(axes), models):
        pc = ax.pcolormesh(w.longitude, w.latitude, w.sel(model=m), vmin=0, vmax=1, cmap="viridis", shading="nearest")
        _coast(ax)
        ax.set_title(m, color=MODEL_COLOURS.get(m, "k"), fontweight="bold")
        ax.set_aspect("equal")
    fig.colorbar(pc, ax=axes, shrink=0.8, label="weight")
    fig.suptitle(title)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def dominant_map(w: xr.DataArray, title: str, path: str):
    from matplotlib.colors import ListedColormap
    models = list(w.model.values)
    idx = w.argmax("model")
    cmap = ListedColormap([MODEL_COLOURS.get(m, "#777") for m in models])
    fig, ax = plt.subplots(figsize=(5.5, 5), constrained_layout=True)
    ax.pcolormesh(w.longitude, w.latitude, idx, cmap=cmap, vmin=-0.5, vmax=len(models) - 0.5, shading="nearest")
    _coast(ax)
    ax.set_aspect("equal")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=MODEL_COLOURS.get(m, "#777")) for m in models],
              labels=models, loc="lower left", fontsize=8)
    ax.set_title(title)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def gain_map(cell_mse: xr.DataArray, rung: str, ref: str, lead: int, title: str, path: str):
    """% RMSE change of `rung` vs `ref` per cell on held-out data. Blue = blend better."""
    g = 100 * (np.sqrt(cell_mse.sel(rung=rung, lead=lead)) / np.sqrt(cell_mse.sel(rung=ref, lead=lead)) - 1)
    lim = float(np.nanpercentile(np.abs(g), 98)) or 1.0
    fig, ax = plt.subplots(figsize=(5.5, 5), constrained_layout=True)
    pc = ax.pcolormesh(g.longitude, g.latitude, g, cmap="RdBu_r", vmin=-lim, vmax=lim, shading="nearest")
    _coast(ax)
    ax.set_aspect("equal")
    fig.colorbar(pc, ax=ax, shrink=0.8, label=f"% RMSE change, {rung} vs {ref}")
    ax.set_title(title)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def rmse_vs_lead(card, var: str, rungs, path: str):
    c = card[card["var"] == var]
    fig, ax = plt.subplots(figsize=(6.5, 4), constrained_layout=True)
    for r in rungs:
        d = c[c.rung == r].sort_values("lead_day")
        name = r.split(":")[-1]
        style = {"color": MODEL_COLOURS[name], "ls": "--"} if name in MODEL_COLOURS else {"lw": 2.5}
        ax.plot(d.lead_day, d.rmse, marker="o", label=r, **style)
    ax.set_xlabel("lead (days)")
    ax.set_ylabel("RMSE")
    ax.set_title(f"{var}: held-out RMSE by lead")
    ax.legend(fontsize=8)
    fig.savefig(path, dpi=150)
    plt.close(fig)
