"""Samanvay on Modal: the dashboard and its API (blend/server.py) as one web endpoint.

    modal deploy modal_app.py             # build the web first: cd web && npm run build
    modal run modal_app.py::refresh       # pull the latest bundles now (also runs daily on a schedule)

Code, the built dashboard (web/dist) and the India outline are baked into the image from this checkout. Bundles live
on a Modal Volume: `refresh` copies bundles/ from the GitHub repo's main branch, where the daily live-run workflow
commits a new live bundle at ~09:30 UTC, so the site follows the live runs without a redeploy. Each refresh is
written to its own folder and switched in by rewriting CURRENT, so a container never reads a half-written copy.
"""

import os
from pathlib import Path

import modal

REPO_TARBALL = "https://codeload.github.com/shreyashsri79/081/tar.gz/refs/heads/main"
DATA = Path("/data")
APP_DIR = "/root/app"
ROOT = Path(__file__).resolve().parent

app = modal.App("samanvay")
volume = modal.Volume.from_name("samanvay-bundles", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi>=0.115", "pydantic>=2.7", "numpy")
    .env({"PYTHONPATH": APP_DIR})
    .add_local_dir(ROOT / "blend", f"{APP_DIR}/blend", ignore=["__pycache__", "*.pyc"])
    .add_local_file(ROOT / "web" / "src" / "geo" / "india.json", f"{APP_DIR}/web/src/geo/india.json")
    .add_local_dir(ROOT / "web" / "dist", f"{APP_DIR}/web/dist")
)


def _current() -> Path | None:
    f = DATA / "CURRENT"
    if not f.exists():
        return None
    p = DATA / f.read_text().strip() / "bundles"
    return p if (p / "index.json").exists() else None


@app.function(image=image, volumes={str(DATA): volume}, schedule=modal.Cron("15 10 * * *"), timeout=600)
def refresh() -> str:
    """Copy bundles/ from GitHub main into a new folder on the volume, switch CURRENT to it, drop older copies."""
    import io
    import shutil
    import tarfile
    import time
    import urllib.request

    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    dest = DATA / stamp
    raw = urllib.request.urlopen(REPO_TARBALL, timeout=120).read()
    n = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        for m in tar.getmembers():
            parts = Path(m.name).parts                      # <repo>-<sha>/bundles/...
            if len(parts) < 2 or parts[1] != "bundles" or not m.isfile():
                continue
            out = dest.joinpath(*parts[1:])
            out.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(m) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            n += 1
    if not (dest / "bundles" / "index.json").exists():
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError("no bundles/index.json in the GitHub tarball")
    (DATA / "CURRENT").write_text(stamp)
    for old in sorted(p for p in DATA.iterdir() if p.is_dir() and p.name != stamp)[:-1]:
        shutil.rmtree(old, ignore_errors=True)              # keep the previous copy for running containers
    volume.commit()
    return f"{n} files -> {dest}"


@app.function(image=image, volumes={str(DATA): volume}, scaledown_window=300)
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def web():
    root = _current()
    os.environ["BLEND_BUNDLES"] = str(root or DATA / "empty")
    os.environ["BLEND_WEB_DIST"] = f"{APP_DIR}/web/dist"
    from blend.server import create_app
    return create_app(os.environ["BLEND_BUNDLES"], os.environ["BLEND_WEB_DIST"])
