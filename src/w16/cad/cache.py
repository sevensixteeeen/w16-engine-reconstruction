"""BREP cache for expensive solids.  The key includes a hash of the generating sources, so stale geometry is never reused."""
from __future__ import annotations
import hashlib
import os
from build123d import export_brep, import_brep

from .common import ROOT

CACHE = os.path.join(ROOT, ".cache")
_SRC = os.path.join(ROOT, "src", "w16")
_BASE = ["params.py", "layout.py", os.path.join("analysis", "valvetrain.py")]


def _digest(files):
    h = hashlib.sha1()
    for f in _BASE + list(files):
        with open(os.path.join(_SRC, f), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:12]


def cached(name, builder, files=()):
    """Return builder() or its cached BREP.  files: module files (relative to src/w16) the shape depends on."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{name}_{_digest(files)}.brep")
    if os.path.exists(path):
        return import_brep(path)
    shape = builder()
    export_brep(shape, path)
    for f in os.listdir(CACHE):
        if f.startswith(name + "_") and f.endswith(".brep") and os.path.join(CACHE, f) != path:
            os.remove(os.path.join(CACHE, f))
    return shape
