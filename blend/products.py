"""C9 Products: weight maps, dominant-model map, where-the-blend-wins map."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

# One fixed colour per model across every chart (Okabe-Ito)
MODEL_COLOURS = {"hres": "#0072B2", "graphcast": "#E69F00", "pangu": "#009E73",
                 "fuxi": "#CC79A7", "gencast": "#D55E00", "aifs": "#56B4E9", "gfs": "#999999"}
# Reference and blend rungs: greys for references, one strong colour for the shipped blend
RUNG_COLOURS = {"B0": "#6B7280", "B0bc": "#374151", "B1": "#A78BFA", "B2": "#7C3AED", "B3s": "#C1121F"}


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
    """One panel per model; w dims (model, latitude, longitude). Colour range fitted to the data so
    differences between models are visible (a 0-1 scale washes them out)."""
    models = list(w.model.values)
    vmax = float(np.ceil(float(w.max()) * 10) / 10)
    fig, axes = plt.subplots(1, len(models), figsize=(4.2 * len(models), 4), constrained_layout=True)
    for ax, m in zip(np.atleast_1d(axes), models):
        pc = ax.pcolormesh(w.longitude, w.latitude, w.sel(model=m), vmin=0, vmax=vmax, cmap="viridis",
                           shading="nearest")
        _coast(ax)
        ax.set_title(m, color=MODEL_COLOURS.get(m, "k"), fontweight="bold")
        ax.set_aspect("equal")
    fig.colorbar(pc, ax=axes, shrink=0.8, label="weight")
    fig.suptitle(title)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def weight_diff_maps(dw: xr.DataArray, title: str, path: str):
    """Change in each model's weight between two situations; dw dims (model, latitude, longitude)."""
    models = list(dw.model.values)
    lim = max(float(np.nanpercentile(np.abs(dw), 98)), 0.02)
    fig, axes = plt.subplots(1, len(models), figsize=(4.2 * len(models), 4), constrained_layout=True)
    for ax, m in zip(np.atleast_1d(axes), models):
        pc = ax.pcolormesh(dw.longitude, dw.latitude, dw.sel(model=m), vmin=-lim, vmax=lim, cmap="PuOr_r",
                           shading="nearest")
        _coast(ax)
        ax.set_title(m, color=MODEL_COLOURS.get(m, "k"), fontweight="bold")
        ax.set_aspect("equal")
    fig.colorbar(pc, ax=axes, shrink=0.8, label="weight change")
    fig.suptitle(title)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def dominant_map(w: xr.DataArray, title: str, path: str):
    from matplotlib.colors import ListedColormap
    models = list(w.model.values)
    idx = w.fillna(-1).argmax("model").where(w.notnull().any("model"))  # rain truth is land only: ocean stays blank
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
        style = {"color": MODEL_COLOURS[name], "ls": "--"} if name in MODEL_COLOURS else \
            {"lw": 2.5, "color": RUNG_COLOURS.get(name, "k")}
        ax.plot(d.lead_day, d.rmse, marker="o", label=r, **style)
    ax.set_xlabel("lead (days)")
    ax.set_ylabel("RMSE")
    ax.set_title(f"{var}: held-out RMSE by lead")
    ax.legend(fontsize=8)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def extremes_figures(table, keep, var, lats, lons, lead_index, art, tag):
    """BSS by lead, reliability at one lead, CSI comparison, and the biggest held-out event day as maps."""
    from .extremes import reliability
    t = table[table["var"] == var]
    events = list(dict.fromkeys(t.event))
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
    for e in events:
        d = t[(t.event == e) & (t.method == "prob>=p*")].sort_values("lead_day")
        axes[0].plot(d.lead_day, d.BSS_vs_clim, marker="o", label=f"{e} vs climatology")
        axes[0].plot(d.lead_day, d.BSS_vs_best_model, marker="s", ls="--", label=f"{e} vs best model")
        k = keep[e]
        fp, ob, n = reliability(k["p"][:, lead_index].ravel(), k["ev"][:, lead_index].ravel())
        axes[1].plot(fp[n > 0], ob[n > 0], marker="o", label=e)
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].set(xlabel="lead (days)", ylabel="Brier skill score", title="Probability skill (>0 = better)")
    axes[0].legend(fontsize=7)
    axes[1].plot([0, 1], [0, 1], color="k", lw=0.8)
    axes[1].set(xlabel="forecast probability", ylabel="observed frequency", title=f"Reliability, Day {lead_index + 1}")
    axes[1].legend(fontsize=8)
    d = t[t.lead_day == lead_index + 1]
    methods = ["prob>=p*", "best_model", "blend_mean"]
    x = np.arange(len(events))
    for i, m in enumerate(methods):
        axes[2].bar(x + (i - 1) * 0.27, [d[(d.event == e) & (d.method == m)].CSI.iloc[0] for e in events], 0.27, label=m)
    axes[2].set_xticks(x, events)
    axes[2].set(ylabel="CSI (higher = better)", title=f"Event detection, Day {lead_index + 1}")
    axes[2].legend(fontsize=8)
    fig.suptitle(f"{var}: extreme-event guidance, held-out years")
    fig.savefig(f"{art}/figures/extremes_{tag}.png", dpi=150)
    plt.close(fig)

    e = events[0]
    k = keep[e]
    ev = k["ev"][:, lead_index]
    day = int(np.nanargmax(np.nansum(ev, axis=(1, 2))))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), constrained_layout=True)
    axes[0].pcolormesh(lons, lats, ev[day], cmap="Greys", vmin=0, vmax=1, shading="nearest")
    axes[0].set_title("observed event (black)")
    pc = axes[1].pcolormesh(lons, lats, k["p"][day, lead_index], cmap="YlOrRd", vmin=0, vmax=1, shading="nearest")
    axes[1].set_title(f"forecast probability, issued {lead_index + 1} day(s) before")
    fig.colorbar(pc, ax=axes[1], shrink=0.8)
    for ax in axes:
        _coast(ax)
        ax.set_aspect("equal")
    valid = np.datetime64(k["init"][day], "D") + np.timedelta64(lead_index + 1, "D")
    fig.suptitle(f"{var} {e}: biggest held-out event day, valid {valid}")
    fig.savefig(f"{art}/figures/extreme_case_{tag}_{e}.png", dpi=150)
    plt.close(fig)
