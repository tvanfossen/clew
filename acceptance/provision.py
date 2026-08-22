# SPDX-License-Identifier: MIT
"""Put a target on disk at its pinned commit, index it, and write the index arm's MCP config.

THE ORDER IS THE POINT, and every step refuses rather than degrades:

  1. FETCH THE PINNED COMMIT DIRECTLY, never a branch tip. Fetching a branch and checking out
     transfers a history, materialises a tip that may differ from the pin, and fails silently
     onto whatever `main` happens to be when the commit is gone. `fetch --depth 1 <sha>` fails
     loudly instead.
  2. VERIFY HEAD against the rubric. A rubric verified against one tree and run against another
     grades code the answer never saw, and every line number in it is then a claim about a
     different file.
  3. BUILD IN-PROCESS, never through a running MCP server. A server older than the working tree
     runs old pipeline logic and re-stamps the index with it — which can drop whole layers and
     then report health.
  4. ASSERT THE DECLARATION REACHED THE BUILD, by section name. A committed declaration that
     never arrives makes the measured index differ from the intended one, and every downstream
     number then describes a build nobody chose. This is the check whose absence let a whole
     phase of work go unmeasured.
  5. WRITE THE MCP CONFIG LAST, so it can only exist once the index behind it does.

WHY THE INDEX ARM CANNOT SHARE THE BASELINE ARM'S SETUP: it needs a config pointing at the built
database, and `execute.run_cell` REFUSES to run the index arm without one. An index arm that
quietly ran without its index would produce plausible answers and a publishable-looking number
with nothing downstream able to tell.

Usage:
    .venv/bin/python -m acceptance.provision --rubric <path> --root <dir>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .grader.rubric import RubricError, Rubric, load
from .runner import check_declaration_applied, check_revision

GIT_TIMEOUT = 900
BUILD_TIMEOUT = 3600


class ProvisionError(RuntimeError):
    """@brief A target that cannot be trusted to answer questions about itself.
    @version 1
    """


## @brief Everything a run needs to point both arms at one target.
## @version 1
@dataclass(frozen=True)
class Provisioned:
    """@brief A checked-out tree, its index, and the index arm's config.
    @version 1
    """

    repo: Path
    db: Path
    mcp_config: Path
    build_version: str


## @brief Run git, raising with git's own stderr on any failure.
## @param cwd Working directory.
## @param args Git arguments.
## @return stdout.
## @version 1
def _git(cwd: Path, *args: str) -> str:
    """The message has to carry git's own stderr — telling a network refusal apart from a
    deleted commit without re-running anything depends on it.

    @brief Invoke git.
    @return stdout.
    @version 1
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError(f"git {' '.join(args)} could not run: {exc}") from exc
    if done.returncode != 0:
        raise ProvisionError(
            f"git {' '.join(args)} failed (rc={done.returncode}) in {cwd}: {done.stderr.strip()}"
        )
    return done.stdout.strip()


## @brief Fetch a target's pinned commit into a working tree.
## @param rubric The rubric naming the target and commit.
## @param repo Directory to hold the checkout.
## @return None.
## @version 1
def fetch_pinned(rubric: Rubric, repo: Path) -> None:
    """Idempotent: an existing tree already at the pin is left alone, so re-provisioning costs
    nothing and a run can resume.

    Submodules are NOT initialised. A target that declares one gets a second remote that can be
    unreachable, and the pinned commit's own tree is what the rubric was verified against.

    @brief Put the pinned commit on disk.
    @return None.
    @version 1
    """
    if (repo / ".git").exists():
        head = _git(repo, "rev-parse", "HEAD")
        if head == rubric.commit:
            return
    else:
        repo.mkdir(parents=True, exist_ok=True)
        _git(repo, "init", "--quiet", ".")
        _git(repo, "remote", "add", "origin", f"https://github.com/{rubric.target}.git")
    _git(repo, "fetch", "--quiet", "--depth", "1", "origin", rubric.commit)
    _git(repo, "checkout", "--quiet", "--force", rubric.commit)


## @brief Read a built index's build_meta rows.
## @param db Path to the database.
## @return Mapping of key to value.
## @version 1
def read_build_meta(db: Path) -> dict:
    """Returns the nested `options` shape `check_declaration_applied` expects, built from the
    flat `key`/`value` rows the pipeline stamps.

    @brief Build metadata as a mapping.
    @return build_meta.
    @version 1
    """
    if not db.is_file():
        raise ProvisionError(f"{db}: no index was written")
    conn = sqlite3.connect(str(db))
    try:
        rows = dict(conn.execute("SELECT key, value FROM build_meta").fetchall())
    except sqlite3.Error as exc:
        raise ProvisionError(f"{db}: cannot read build_meta: {exc}") from exc
    finally:
        conn.close()
    options: dict = {}
    for key, value in rows.items():
        if key.startswith("options."):
            options.setdefault(key.split(".")[1], {})
    return {"rows": rows, "options": options}


## @brief Build the index for a provisioned target.
## @param rubric The rubric, for its declaration.
## @param repo The checked-out tree.
## @param db Where to write the index.
## @param declare_file Path to write the rubric's declaration to, or None to skip.
## @return None.
## @version 1
def build_index(rubric: Rubric, repo: Path, db: Path, declare_file: Path | None) -> None:
    """IN-PROCESS, never through a running server. A server process older than the working tree
    runs old pipeline logic and re-stamps the index with it, which can drop whole layers and
    then report health.

    @brief Build the target's index.
    @return None.
    @version 1
    """
    argv = [
        sys.executable,
        "-m",
        "clew",
        "--output",
        str(db),
        "--repo-root",
        str(repo),
        "--rebuild",
    ]
    if declare_file is not None:
        argv += ["--declare", str(declare_file)]
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=BUILD_TIMEOUT, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError(f"index build could not run: {exc}") from exc
    if done.returncode != 0:
        raise ProvisionError(
            f"index build failed (rc={done.returncode}): {done.stderr.strip()[-600:]}"
        )


## @brief Write the MCP config the index arm needs.
## @param db The built index.
## @param repo The target tree.
## @param path Where to write the config.
## @return None.
## @version 1
def write_mcp_config(db: Path, repo: Path, path: Path) -> None:
    """WRITTEN LAST, so it cannot exist before the index it points at. A config naming a database
    that was never built sends the index arm to an empty index, which answers — badly — rather
    than refusing.

    @brief Write the index arm's MCP config.
    @return None.
    @version 1
    """
    if not db.is_file():
        raise ProvisionError(
            f"{db}: refusing to write an MCP config for an index that does not exist"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "clew": {
                        "command": sys.executable,
                        "args": ["-m", "clew.mcp_server.server", "--repo", str(repo)],
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


## @brief Provision one target end to end.
## @param rubric The validated rubric.
## @param root Directory to hold the checkout, index and config.
## @return Provisioned.
## @version 1
def provision(rubric: Rubric, root: Path) -> Provisioned:
    """Every step refuses rather than degrades, and the order is what makes the refusals mean
    something — see the module docstring.

    @brief Provision a target.
    @return Provisioned.
    @version 1
    """
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repo"
    db = root / "clew.db"

    fetch_pinned(rubric, repo)
    try:
        check_revision(rubric, repo)
    except ValueError as exc:
        raise ProvisionError(str(exc)) from exc

    declare_file: Path | None = None
    if rubric.declare:
        import yaml

        declare_file = root / "declaration.yaml"
        declare_file.write_text(yaml.safe_dump(rubric.declare, sort_keys=False), encoding="utf-8")

    build_index(rubric, repo, db, declare_file)
    meta = read_build_meta(db)
    try:
        check_declaration_applied(rubric, meta)
    except ValueError as exc:
        raise ProvisionError(str(exc)) from exc

    config = root / "mcp.json"
    write_mcp_config(db, repo, config)
    return Provisioned(
        repo=repo,
        db=db,
        mcp_config=config,
        build_version=str(meta["rows"].get("build_version", "")),
    )


## @brief CLI entry point.
## @return Exit code.
## @version 1
def main() -> int:
    """@brief Provision a target from its rubric.
    @return Exit code.
    @version 1
    """
    parser = argparse.ArgumentParser(prog="acceptance.provision", description=__doc__)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        rubric = load(args.rubric)
    except RubricError as exc:
        print(f"REFUSED — {exc}", file=sys.stderr)
        return 1
    try:
        out = provision(rubric, args.root)
    except ProvisionError as exc:
        print(f"REFUSED — {exc}", file=sys.stderr)
        return 1
    print(f"{rubric.target} @ {rubric.commit[:10]}")
    print(f"  repo   {out.repo}")
    print(f"  index  {out.db}  (build {out.build_version})")
    print(f"  mcp    {out.mcp_config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
