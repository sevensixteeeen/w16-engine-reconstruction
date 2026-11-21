"""Publish the W16 project from the alacrity monorepo to its own GitHub repository.

Takes the COMMITTED history of one branch of the monorepo (never the working tree, never the monorepo itself), and in a
fresh clone in a temporary folder:
  1. keeps only this project folder, with its history (git filter-repo --subdirectory-filter);
  2. strips from the whole history: the generated CAD exports, virtual environments / wheel and build caches, the
     third-party source documents (01_RESEARCH/sources/), and every file larger than 50 MB;
  3. replaces local absolute paths (this folder, the user's home folder) in text files of every commit;
  4. rewrites the commit e-mail to the GitHub noreply address of the logged-in gh account (or --email);
  5. verifies the result - no blob > 50 MB, none of the stripped paths, no third-party source documents, no local home
     path, no token / key patterns - and stops (exit 1, nothing pushed) if any check fails;
  6. with --push, pushes it to github.com/<gh user>/<repo> (created with --create public|private if missing).

The rewrite is deterministic: the same monorepo commits give the same published commits, so a re-publish after new
commits is a fast-forward push.  --force is needed only after the published history itself was rewritten (e.g. when
the strip list changes).  The monorepo is only read.

Needs git, git-filter-repo (`uv pip install --python .venv\\Scripts\\python.exe git-filter-repo`) and, for the noreply address and
--push, the GitHub CLI logged in (`gh auth login`).

    .venv\\Scripts\\python tools\\publish_github.py                 # build + verify only, prints the folder
    .venv\\Scripts\\python tools\\publish_github.py --push          # build + verify + push (fast-forward)
    .venv\\Scripts\\python tools\\publish_github.py --push --force  # after a history rewrite
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRIP_PATHS = ["13_EXPORTS_STEP/", "14_EXPORTS_STL_3MF/", "06_ASSEMBLIES/step/", "01_RESEARCH/sources/",
               ".venv/", "wheelhouse/", ".cache/", "regen_logs/", "regen_logs_console.log"]
STRIP_GLOBS = ["*/.venv/*", "*/.cache/*", "*/__pycache__/*", "*.pyc"]
MAX_BYTES = 50 * 1024 * 1024
SECRET_RE = (r"ghp_[A-Za-z0-9]{20,}|github[_]pat_|gho_[A-Za-z0-9]{20}|sk-[A-Za-z0-9_-]{20,}|sk[-]ant-|AKIA[0-9A-Z]{16}"
             r"|-----BEGIN [A-Z ]*PRIVATE KEY|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|hf_[A-Za-z0-9]{30,}"
             r"|(api[_-]?key|secret|passw(or)?d|token)\s*[:=]\s*[\"'][^\"']{8,}")
SENSITIVE_NAMES = re.compile(r"(^|/)(\.env|.*\.pem|.*\.key|id_rsa.*|credentials.*\.json|settings\.local\.json|\.npmrc|\.pypirc)$", re.I)


def run(cmd, cwd=None, check=True, capture=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        sys.exit(f"FAILED: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r


def filter_repo_cmd():
    if run(["git", "filter-repo", "--version"], check=False).returncode == 0:
        return ["git", "filter-repo"]
    if run([sys.executable, "-m", "git_filter_repo", "--version"], check=False).returncode == 0:
        return [sys.executable, "-m", "git_filter_repo"]
    sys.exit("git-filter-repo not found: run  uv pip install --python .venv\\Scripts\\python.exe git-filter-repo")


def gh(*args, check=True):
    if not shutil.which("gh"):
        sys.exit("GitHub CLI (gh) not found")
    return run(["gh", *args], check=check)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--branch", default="bugatti-w16-engine", help="monorepo branch to publish (default %(default)s)")
    ap.add_argument("--repo", default="w16-engine-reconstruction", help="GitHub repository name (default %(default)s)")
    ap.add_argument("--email", help="author e-mail for the published commits (default: noreply address of the gh account)")
    ap.add_argument("--out", help="folder for the published clone (default: a new temporary folder)")
    ap.add_argument("--push", action="store_true", help="push after a successful verification")
    ap.add_argument("--force", action="store_true", help="force-push (only after a rewrite of the published history)")
    ap.add_argument("--create", choices=["public", "private"], help="create the GitHub repository with this visibility if it does not exist")
    a = ap.parse_args()

    mono = run(["git", "rev-parse", "--show-toplevel"], cwd=PROJECT).stdout.strip()
    sub = os.path.relpath(PROJECT, mono).replace("\\", "/")
    dirty = run(["git", "status", "--porcelain", "--", "."], cwd=PROJECT).stdout.strip()
    if dirty:
        print(f"note: uncommitted changes in {sub}/ are NOT published (only commits on {a.branch}):\n{dirty[:2000]}\n")
    head = run(["git", "rev-parse", "--short", a.branch], cwd=mono).stdout.strip()
    fr = filter_repo_cmd()

    out = a.out or os.path.join(tempfile.gettempdir(), f"w16_publish_{time.strftime('%Y%m%d_%H%M%S')}")
    if os.path.exists(out):
        sys.exit(f"{out} exists - choose another --out")
    print(f"[1] clone {a.branch} ({head}) of {mono} -> {out}")
    run(["git", "clone", "-q", "--no-local", "--single-branch", "--branch", a.branch, mono, out])

    print(f"[2] keep only {sub}/ with its history")
    run(fr + ["--force", "--subdirectory-filter", sub], cwd=out)

    print("[3] strip exports, environments, third-party sources, files > 50 MB; replace local paths")
    home = os.path.expanduser("~")
    repl = []
    for path, to in ((PROJECT, "<project root>"), (mono, "<monorepo root>"), (home, "~")):
        for v in {path, path.replace("\\", "/"), path.replace("\\", "\\\\")}:
            repl.append(f"{v}==>{to}")
    repl_file = os.path.join(out, "..", f".w16_publish_replace_{os.getpid()}.txt")
    with open(repl_file, "w", encoding="utf-8") as fh:
        fh.write("\n".join(repl) + "\n")
    cmd = fr + ["--force", "--invert-paths"]
    for p_ in STRIP_PATHS:
        cmd += ["--path", p_]
    for g in STRIP_GLOBS:
        cmd += ["--path-glob", g]
    cmd += ["--strip-blobs-bigger-than", "50M", "--replace-text", repl_file]
    run(cmd, cwd=out)
    os.remove(repl_file)

    print("[4] commit e-mail")
    email = a.email
    login = None
    if not email or a.push:
        u = json.loads(gh("api", "user").stdout)
        login = u["login"]
        email = email or f"{u['id']}+{login}@users.noreply.github.com"
    names = set(run(["git", "log", "--format=%an <%ae>%n%cn <%ce>"], cwd=out).stdout.split("\n")) - {""}
    mm = os.path.join(out, "..", f".w16_publish_mailmap_{os.getpid()}.txt")
    with open(mm, "w", encoding="utf-8") as fh:
        for n in sorted(names):
            m = re.match(r"(.*) <(.*)>", n)
            fh.write(f"{m.group(1)} <{email}> <{m.group(2)}>\n")
    run(fr + ["--force", "--mailmap", mm], cwd=out)
    os.remove(mm)
    run(["git", "branch", "-M", "main"], cwd=out)
    run(["git", "config", "user.email", email], cwd=out)

    print("[5] verify")
    problems = []
    objs = run(["git", "rev-list", "--objects", "--all"], cwd=out).stdout
    r = subprocess.run(["git", "cat-file", "--batch-check=%(objecttype) %(objectsize) %(rest)"], cwd=out, input=objs,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    blobs = [(int(b[1]), b[2] if len(b) > 2 else "") for b in (l.split(" ", 2) for l in r.stdout.splitlines() if l.startswith("blob "))]
    big = [b for b in blobs if b[0] > MAX_BYTES]
    largest = max(blobs, default=(0, ""))
    if big:
        problems.append(f"blobs > 50 MB: {big[:5]}")
    paths = set(run(["git", "log", "--all", "--name-only", "--format="], cwd=out).stdout.split("\n")) - {""}
    bad = [p_ for p_ in paths if any(p_.startswith(s.rstrip("/")) for s in STRIP_PATHS)
           or re.search(r"(^|/)(\.venv|\.cache|wheelhouse|__pycache__)/", p_) or SENSITIVE_NAMES.search(p_)]
    if bad:
        problems.append(f"stripped or sensitive paths still in history: {sorted(bad)[:10]}")
    revs = run(["git", "rev-list", "--all"], cwd=out).stdout.split()
    # matches are reported per file; the only allowed ones are the pattern definition of this script (SECRET_RE lines,
    # in every revision of it - an earlier revision spelled two of the token prefixes literally)
    lines = run(["git", "grep", "-I", "-n", "-E", SECRET_RE, *revs, "--", "."], cwd=out, check=False).stdout.splitlines()
    own = re.compile(r"^SECRET_RE = \(r\"|^ {13}r\"\|")
    hits = set()
    for ln in lines:
        _, path, _, text = (ln.split(":", 3) + ["", "", ""])[:4]
        if not (path == "tools/publish_github.py" and own.match(text)):
            hits.add(path)
    if hits:
        problems.append(f"token / key patterns: {sorted(hits)[:10]}")
    for needle in {home, home.replace("\\", "/")}:
        hits = run(["git", "grep", "-I", "-l", "-i", "-F", needle, *revs, "--", "."], cwd=out, check=False).stdout.split()
        if hits:
            problems.append(f"local path {needle!r} in: {sorted(set(h.split(':', 1)[1] for h in hits))[:10]}")
    emails = set(run(["git", "log", "--format=%ae%n%ce"], cwd=out).stdout.split()) - {email}
    if emails:
        problems.append(f"other commit e-mails left: {emails}")
    size = run(["git", "count-objects", "-vH"], cwd=out).stdout
    pack = re.search(r"size-pack: (.*)", size).group(1)
    n_commits = len(revs)
    print(f"    commits {n_commits}, files in history {len(paths)}, largest blob {largest[0] / 1e6:.1f} MB ({largest[1]}), pack {pack}")
    if problems:
        print("VERIFICATION FAILED - nothing pushed:\n  " + "\n  ".join(problems))
        sys.exit(1)
    print("    verification passed")

    if not a.push:
        print(f"\nbuilt and verified in {out} (not pushed; add --push)")
        return
    full = f"{login}/{a.repo}"
    exists = gh("repo", "view", full, "--json", "name", check=False).returncode == 0
    if not exists:
        if not a.create:
            sys.exit(f"{full} does not exist - add --create public|private")
        gh("repo", "create", a.repo, f"--{a.create}", "--description",
           "Independent concept-level engineering reconstruction of a quad-turbo W16 engine from public data "
           "(parametric CAD, analysis, FE). Not manufacturer data.")
    url = f"https://github.com/{full}"
    run(["git", "remote", "add", "origin", url + ".git"], cwd=out)
    print(f"[6] push to {url}{' (force)' if a.force else ''}")
    run(["git", "push", "-u", "origin", "main"] + (["--force"] if a.force else []), cwd=out, capture=False)
    print(f"\npublished {url} - main = {run(['git', 'rev-parse', '--short', 'HEAD'], cwd=out).stdout.strip()} "
          f"(from {a.branch} {head}), pack {pack}")


if __name__ == "__main__":
    main()
