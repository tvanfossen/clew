# SPDX-License-Identifier: MIT
"""Single-mechanism mutation control.

A green test proves nothing until the mechanism it guards has been deleted and that same test
has been watched to fail. This runs that experiment: apply ONE textual substitution to ONE file,
run ONE test, and report whether the test caught it.

RESTORE IS `git checkout HEAD -- <the one file>`, never a directory and never a bare
`git checkout --`. A directory restore against an uncommitted tree has already destroyed a
session's finished work in this repo; the refusal to start on a dirty tree below is the guard.

`__pycache__` is purged around every run. A same-length edit inside one mtime second is masked
by bytecode caching, and PYTHONDONTWRITEBYTECODE does NOT fix it — it reports a working test as
not catching the mutation.

@brief Mutation control harness.
@version 1
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


## @brief Delete every __pycache__ under the repository.
## @return None.
## @version 1
def purge_cache() -> None:
    """@brief Purge bytecode caches.
    @return None.
    @version 1
    """
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


## @brief Run one test selector and report whether it passed.
## @param selector pytest node id or path.
## @return True when pytest exits 0.
## @version 1
def run_test(selector: str) -> bool:
    """@brief Run pytest.
    @return Pass state.
    @version 1
    """
    purge_cache()
    done = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-m", "pytest", selector, "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    purge_cache()
    if done.returncode not in (0, 1):
        print(done.stdout[-2000:], file=sys.stderr)
    return done.returncode == 0


## @brief Refuse to run on a dirty tree.
## @return None.
## @version 1
def require_clean() -> None:
    """A mutation is restored FROM A COMMIT. If uncommitted work is present, the restore would
    discard it — which is exactly how ten files of finished work were lost here once.

    @brief Dirty-tree refusal.
    @return None.
    @version 1
    """
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    if dirty:
        sys.exit(f"REFUSED: working tree is dirty; commit first.\n{dirty}")


## @brief Apply one substitution, run one test, restore the file.
## @param path Repo-relative file to mutate.
## @param old Exact text to replace; must appear exactly once.
## @param new Replacement text.
## @param selector pytest selector for the guarding test.
## @return True when the test CAUGHT the mutation.
## @version 1
def mutate(path: str, old: str, new: str, selector: str) -> bool:
    """@brief One mutation, one verdict.
    @return Caught state.
    @version 1
    """
    target = ROOT / path
    source = target.read_text()
    hits = source.count(old)
    if hits != 1:
        sys.exit(f"REFUSED: pattern appears {hits} times in {path}; a mutation must be singular.")
    target.write_text(source.replace(old, new))
    try:
        caught = not run_test(selector)
    finally:
        subprocess.run(["git", "checkout", "HEAD", "--", path], cwd=ROOT, check=True)
        purge_cache()
    return caught


## @brief CLI.
## @return Process exit code.
## @version 1
def main() -> int:
    """@brief Entry point.
    @return Exit code.
    @version 1
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("selector")
    args = ap.parse_args()

    require_clean()
    ## The BASELINE half: the test must pass before the mutation, or a failure afterwards proves
    ## only that the suite was already broken.
    if not run_test(args.selector):
        sys.exit("REFUSED: the test fails BEFORE the mutation; there is nothing to control for.")
    caught = mutate(args.path, args.old, args.new, args.selector)
    print(f"{'CAUGHT' if caught else 'MISS  '}  {args.path}  <- {args.selector}")
    return 0 if caught else 2


if __name__ == "__main__":
    raise SystemExit(main())
