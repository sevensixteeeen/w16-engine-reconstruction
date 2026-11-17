"""Resumable, multi-connection wheel downloader for slow per-connection links to PyPI.

Reads pinned `name==version` lines from requirements.txt, picks the CPython 3.12 / win_amd64 wheel from the
official PyPI JSON API, downloads it from files.pythonhosted.org with parallel HTTP range requests
(each chunk retried independently, completed chunks kept on disk), and verifies the published SHA-256.

Standard library only, so it runs on any Python.  Usage:  python tools/fetch_wheels.py [requirements.txt] [wheelhouse]
"""
import concurrent.futures as cf
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

REQ = sys.argv[1] if len(sys.argv) > 1 else "requirements.txt"
OUT = sys.argv[2] if len(sys.argv) > 2 else "wheelhouse"
CHUNK = 150_000
THREADS = 32
UA = {"User-Agent": "wheel-fetch/1.0"}


def get(url, rng=None, timeout=40):
    h = dict(UA)
    if rng:
        h["Range"] = f"bytes={rng[0]}-{rng[1]}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.read()


def rank(fn):
    """Lower is better; None = not installable on cp312 win_amd64."""
    m = re.match(r"^(.+?)-(.+?)(-\d[^-]*)?-([^-]+)-([^-]+)-([^-]+)\.whl$", fn)
    if not m:
        return None
    py, abi, plat = m.group(4), m.group(5), m.group(6)
    pys, plats = py.split("."), plat.split(".")
    if "win_amd64" in plats:
        if "cp312" in pys and abi in ("cp312", "none"):
            return 0
        if abi == "abi3" and any(re.fullmatch(r"cp3(\d+)", p) and int(p[3:]) <= 12 for p in pys):
            return 1
        if abi == "none" and any(p in ("py3", "py2.py3", "py312") or p.startswith("py3") for p in pys):
            return 2
        return None
    if "any" in plats and abi == "none" and any(p.startswith("py3") or p == "py2.py3" for p in pys + py.split(".")):
        return 3
    return None


def pick(name, ver):
    meta = json.loads(get(f"https://pypi.org/pypi/{name}/{ver}/json"))
    best = None
    for f in meta["urls"]:
        if f["packagetype"] != "bdist_wheel":
            continue
        r = rank(f["filename"])
        if r is not None and (best is None or r < best[0]):
            best = (r, f)
    return best[1] if best else None


def fetch_chunk(url, path, i, a, b):
    part = f"{path}.part{i:05d}"
    if os.path.exists(part) and os.path.getsize(part) == b - a + 1:
        return b - a + 1
    for attempt in range(40):
        try:
            data = get(url, (a, b))
            if len(data) == b - a + 1:
                with open(part, "wb") as fh:
                    fh.write(data)
                return len(data)
        except Exception:
            pass
        time.sleep(min(1 + attempt, 8))
    raise RuntimeError(f"chunk {i} failed: {url}")


def download(f, pool):
    path = os.path.join(OUT, f["filename"])
    size, sha = f["size"], f["digests"]["sha256"]
    if os.path.exists(path) and os.path.getsize(path) == size:
        return "cached"
    ranges = [(i, a, min(a + CHUNK, size) - 1) for i, a in enumerate(range(0, size, CHUNK))]
    list(pool.map(lambda t: fetch_chunk(f["url"], path, *t), ranges))
    h = hashlib.sha256()
    with open(path + ".tmp", "wb") as out:
        for i, a, b in ranges:
            with open(f"{path}.part{i:05d}", "rb") as p:
                d = p.read()
            h.update(d)
            out.write(d)
    if h.hexdigest() != sha:
        os.remove(path + ".tmp")
        for i, a, b in ranges:
            os.remove(f"{path}.part{i:05d}")
        raise RuntimeError(f"SHA-256 mismatch for {f['filename']}")
    os.replace(path + ".tmp", path)
    for i, a, b in ranges:
        os.remove(f"{path}.part{i:05d}")
    return "ok"


def main():
    os.makedirs(OUT, exist_ok=True)
    pins = []
    for line in open(REQ, encoding="utf-8"):
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;\\]+)", line.strip())
        if m:
            pins.append((m.group(1), m.group(2)))
    print(f"{len(pins)} pinned packages", flush=True)
    with cf.ThreadPoolExecutor(8) as mp:
        files = list(mp.map(lambda p: (p, pick(*p)), pins))
    missing = [p for p, f in files if f is None]
    files = [f for p, f in files if f is not None]
    total = sum(f["size"] for f in files)
    print(f"total {total/1e6:.1f} MB in {len(files)} wheels; no wheel for: {missing}", flush=True)
    t0 = time.time()
    done = 0
    failed = []
    with cf.ThreadPoolExecutor(THREADS) as pool:
        for f in sorted(files, key=lambda f: f["size"]):
            try:
                st = download(f, pool)
            except Exception as e:
                st = f"FAILED {e}"
                failed.append(f["filename"])
            done += f["size"]
            print(f"[{done/1e6:7.1f}/{total/1e6:.1f} MB {time.time()-t0:6.0f}s] {st:7s} {f['filename']}", flush=True)
    print("DONE" if not failed and not missing else f"INCOMPLETE failed={failed} missing={missing}", flush=True)
    return 1 if failed or missing else 0


if __name__ == "__main__":
    sys.exit(main())
