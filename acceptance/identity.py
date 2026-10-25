# SPDX-License-Identifier: MIT
"""What produced a number, recorded beside the number.

WHY THIS EXISTS. A grid's artifacts named the target commit, the rubric version and digest, the
seed, the models and the replicate count — every INPUT to the measurement and nothing about the
thing being measured. A published score was therefore attributable to a repository and a rubric
but not to a version of clew, and a reader could not tell a number produced by 1.1.0 from one
produced by 1.0.39. `provision` read `build_version` out of the index it had just built and only
printed it; the database that carries it is gitignored.

THE LANGUAGE SET IS THE LOAD-BEARING FIELD, not the substrate version. 1.1.0's five
configuration grammars live in a fork of lang-parsing-substrate whose wheel reports **the same
version string as the published one**, because the pull request carries no bump — which is the
entire reason `clew.substrate` asks what is compiled in rather than what is installed. A record
holding only `substrate_version` cannot say which wheel answered the questions.

AN UNREADABLE FIELD IS ABSENT, NEVER BLANK. An empty sha or an empty list in a published record
reads as a finding; a missing key reads as a gap, which is what it is. The same rule
`clew/mcp_server/emptiness.py` applies to the served scope applies here, and for the same
reason: "nothing was missed" and "nobody measured" must not look alike.

@brief The identity of the tool under test.
@version 1
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from clew.signature import CLEW_BUILD_VERSION

GIT_TIMEOUT = 30


## @brief The git facts about a checkout, or nothing when it is not one.
## @param repo Directory expected to be inside a git working tree.
## @return Mapping with `clew_commit` and `clew_dirty`, or empty when git could not answer.
## @version 1
def _checkout(repo: Path) -> dict:
    """BOTH FACTS OR NEITHER. A commit without a dirty flag is the failure `check_revision`
    documents on the target side: HEAD is not the tree, and a recorded sha beside an unrecorded
    working state invites a reader to assume the second.

    THE FULL SHA. A short one is ambiguous across a fork, and this record exists to be resolved
    by someone who has only the record.

    @brief Commit and cleanliness.
    @return Git fields, or an empty mapping.
    @version 1
    """
    try:
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
        if head.returncode != 0:
            return {}
        dirty = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
        if dirty.returncode != 0:
            return {}
    except (OSError, subprocess.TimeoutExpired):
        return {}
    sha = head.stdout.strip()
    if len(sha) != 40:
        return {}
    ## `clew_dirty` IS ALWAYS PRESENT ONCE GIT ANSWERED, including when False. False here is a
    ## measurement — the tree was checked and was clean — and dropping it would make a clean
    ## tree indistinguishable from an unchecked one.
    return {"clew_commit": sha, "clew_dirty": bool(dirty.stdout.strip())}


## @brief Which lang-parsing-substrate is installed, by version and by capability.
## @return Mapping with `substrate_version` and `substrate_languages`, each omitted if unreadable.
## @version 1
def _substrate() -> dict:
    """THE VERSION IS THE WEAKER HALF and is recorded anyway, because it is what a bug report
    will quote. The capability set is what actually identifies the wheel.

    @brief Substrate version and language keys.
    @return Substrate fields.
    @version 1
    """
    out: dict = {}
    try:
        from importlib.metadata import PackageNotFoundError, version

        out["substrate_version"] = version("lang-parsing-substrate")
    except (ImportError, PackageNotFoundError):
        pass
    try:
        from clew.substrate import compiled_languages

        langs = sorted(compiled_languages())
    except ImportError:
        langs = []
    ## SORTED, so two runs diff rather than reorder; and absent when empty, because an empty
    ## language set means the substrate could not be read, not that it parses nothing.
    if langs:
        out["substrate_languages"] = langs
    return out


## @brief Everything a reader needs to attribute a score to a build of clew.
## @param repo The clew checkout to describe; defaults to the installed package's own tree.
## @return A mapping of identity fields, each omitted when it could not be read.
## @version 1
def tool_identity(repo: Path | None = None) -> dict:
    """DERIVED FROM THE INSTALLED PACKAGE, not from the current working directory. The grid is
    driven from the repository today, but the harness is an entry point like any other and a
    `cwd` is not evidence of which clew answered — `clew.signature`'s own location is.

    @brief The identity of the clew under test.
    @return Identity fields.
    @version 1
    """
    import clew

    if repo is None:
        repo = Path(clew.__file__).resolve().parent.parent
    out: dict = {"clew_build_version": str(CLEW_BUILD_VERSION)}
    try:
        from importlib.metadata import PackageNotFoundError, version

        out["clew_version"] = version("clew-trace")
    except (ImportError, PackageNotFoundError):
        pass
    out.update(_checkout(repo))
    out.update(_substrate())
    return out
