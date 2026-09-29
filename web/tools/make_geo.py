"""Bake the India outline and state boundaries into one small JSON for the map.

Sources (datameet/maps, Survey of India boundary incl. all of J&K and Ladakh):
  Country/india-composite.geojson
  States/Admin2.{shp,dbf}
Neighbours and coastlines (Natural Earth 1:50m, public domain):
  ne_50m_admin_0_countries.geojson  (saved as ne50.geojson)

Natural Earth draws India's northern boundary differently from the Survey of
India. Any neighbour line that falls inside, or within ~0.15 deg of, the SoI
outline is dropped, so the only boundary drawn around India is the SoI one.

Usage: python3 tools/make_geo.py <dir with the downloads>  ->  src/geo/india.json

No third-party libraries: the shapefile reader and Douglas-Peucker are inline so
this runs on any machine with Python 3.
"""

import json
import struct
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "geo" / "india.json"


def dp(pts, tol):
    """Douglas-Peucker, iterative. pts: list of (x, y)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if d > best:
                best, idx = d, i
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def area(ring):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def clean(rings, tol, min_area):
    out = []
    for r in rings:
        if area(r) < min_area:
            continue
        # A closed ring starts and ends on the same point, which gives
        # Douglas-Peucker a zero-length baseline. Simplify the two halves.
        h = len(r) // 2
        s = dp(r[: h + 1], tol)[:-1] + dp(r[h:], tol)
        if len(s) >= 4:
            out.append([[round(x, 3), round(y, 3)] for x, y in s])
    return out


def read_shp(path):
    d = Path(path).read_bytes()
    i = 100
    shapes = []
    while i < len(d):
        _, length = struct.unpack(">II", d[i : i + 8])
        rec = d[i + 8 : i + 8 + length * 2]
        i += 8 + length * 2
        stype = struct.unpack("<i", rec[:4])[0]
        if stype != 5:
            shapes.append([])
            continue
        nparts, npts = struct.unpack("<ii", rec[36:44])
        parts = list(struct.unpack(f"<{nparts}i", rec[44 : 44 + 4 * nparts]))
        base = 44 + 4 * nparts
        pts = [struct.unpack("<dd", rec[base + 16 * k : base + 16 * k + 16]) for k in range(npts)]
        parts.append(npts)
        shapes.append([pts[parts[k] : parts[k + 1]] for k in range(nparts)])
    return shapes


def read_dbf_names(path):
    d = Path(path).read_bytes()
    n, hl, rl = struct.unpack("<IHH", d[4:12])
    return [d[hl + r * rl + 1 : hl + r * rl + 1 + 50].decode("latin1").strip() for r in range(n)]


NB_BOX = (55.0, -2.0, 110.0, 48.0)  # lon0, lat0, lon1, lat1


def india_mask(outline, step=0.05, lon0=60.0, lat0=0.0, lon1=105.0, lat1=45.0, grow=3):
    """Even-odd scanline raster of the SoI outline, dilated by `grow` cells."""
    nx, ny = int((lon1 - lon0) / step), int((lat1 - lat0) / step)
    edges = []
    for r in outline:
        for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
            if y1 != y2:
                edges.append((x1, y1, x2, y2))
    m = [[False] * nx for _ in range(ny)]
    for i in range(ny):
        y = lat0 + (i + 0.5) * step
        xs = sorted(x1 + (y - y1) * (x2 - x1) / (y2 - y1) for x1, y1, x2, y2 in edges if (y1 > y) != (y2 > y))
        for a, b in zip(xs[::2], xs[1::2]):
            j0, j1 = max(0, int((a - lon0) / step)), min(nx - 1, int((b - lon0) / step))
            for j in range(j0, j1 + 1):
                m[i][j] = True
        # the outline itself counts as inside, so shared borders are dropped too
    for x1, y1, x2, y2 in edges:
        for t in range(11):
            x, y = x1 + (x2 - x1) * t / 10, y1 + (y2 - y1) * t / 10
            i, j = int((y - lat0) / step), int((x - lon0) / step)
            if 0 <= i < ny and 0 <= j < nx:
                m[i][j] = True
    g = [[False] * nx for _ in range(ny)]
    for i in range(ny):
        for j in range(nx):
            if m[i][j]:
                for di in range(-grow, grow + 1):
                    for dj in range(-grow, grow + 1):
                        a, b = i + di, j + dj
                        if 0 <= a < ny and 0 <= b < nx:
                            g[a][b] = True

    def inside(x, y):
        i, j = int((y - lat0) / step), int((x - lon0) / step)
        return 0 <= i < ny and 0 <= j < nx and g[i][j]
    return inside


def neighbours(src, outline):
    path = src / "ne50.geojson"
    if not path.exists():
        return []
    inside = india_mask(outline)
    lo0, la0, lo1, la1 = NB_BOX
    lines = []
    for f in json.loads(path.read_text())["features"]:
        if f["properties"].get("ADMIN") == "India":
            continue
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            for ring in poly:
                ring = [tuple(p[:2]) for p in ring]
                xs, ys = [p[0] for p in ring], [p[1] for p in ring]
                if max(xs) < lo0 or min(xs) > lo1 or max(ys) < la0 or min(ys) > la1:
                    continue
                run = []
                for a, b in zip(ring, ring[1:]):
                    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                    keep = lo0 - 2 <= mx <= lo1 + 2 and la0 - 2 <= my <= la1 + 2 and not inside(mx, my)
                    if keep:
                        if not run:
                            run.append(a)
                        run.append(b)
                    elif run:
                        lines.append(run)
                        run = []
                if run:
                    lines.append(run)
    out = []
    for ln in lines:
        s = dp(ln, 0.03)
        if len(s) >= 2:
            out.append([[round(x, 3), round(y, 3)] for x, y in s])
    return out


def main(src):
    src = Path(src)
    g = json.loads((src / "india.geojson").read_text())
    rings = []
    for f in g["features"]:
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            rings.append([tuple(p[:2]) for p in poly[0]])
    outline = clean(rings, tol=0.02, min_area=0.002)

    states = []
    for name, shape in zip(read_dbf_names(src / "Admin2.dbf"), read_shp(src / "Admin2.shp")):
        rs = clean([list(r) for r in shape], tol=0.04, min_area=0.004)
        if rs:
            states.append({"name": name, "rings": rs})

    nb = neighbours(src, outline)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "datameet/maps (Survey of India boundary), simplified",
        "outline": outline,
        "states": states,
        "neighbours": nb,
    }, separators=(",", ":")))
    print(f"{OUT}  {OUT.stat().st_size / 1024:.0f} KB  outline rings={len(outline)}  states={len(states)}  neighbour lines={len(nb)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
