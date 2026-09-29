"""The server stays light and offline: it must work with xarray, dask and gcsfs unimportable (plan T9)."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_server_imports_without_science_stack(bundle_root):
    code = textwrap.dedent(f"""
        import sys
        class Poison:
            def __getattr__(self, name):
                raise ImportError("server must not use this module")
        for mod in ("xarray", "dask", "gcsfs", "zarr", "pandas", "netCDF4", "blend.sources", "blend.export"):
            sys.modules[mod] = Poison()
        from fastapi.testclient import TestClient
        from blend.server import create_app
        c = TestClient(create_app({str(bundle_root)!r}))
        r = c.get("/api/health"); assert r.status_code == 200, r.text
        r = c.get("/api/meteogram?run=hindcast-20200715&i=1&j=1"); assert r.status_code == 200, r.text
        r = c.get("/api/extremes?run=hindcast-20200715&type=rain_p95&lead=1"); assert r.status_code == 200, r.text
        r = c.get("/api/export/geojson?run=hindcast-20200715&lead=1"); assert r.status_code == 200, r.text
        r = c.get("/api/export/csv?run=hindcast-20200715"); assert r.status_code == 200, r.text
        print(__import__("json").dumps({{"ok": True}}))
    """)
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"ok": True}
