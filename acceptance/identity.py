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


## @brief The version the installed distribution's metadata claims, or None.
## @return Version string, or None when the distribution cannot be read.
## @version 1
def _installed_version() -> str | None:
    """SEPARATE FROM `tool_identity` SO A TEST CAN REPLACE IT. The staleness this guards against
    is a property of the operator's environment, which a test cannot create without an install.

    @brief Installed distribution version.
    @return Version, or None.
    @version 1
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("clew-trace")
    except (ImportError, PackageNotFoundError):
        return None


## @brief The version the checkout's own pyproject declares, or None.
## @param repo Directory expected to hold `pyproject.toml`.
## @return Version string, or None when it cannot be read.
##
## v2: routed through `clew.tomlcompat` rather than a local fallback, which the gate refused.
## @version 2
def _checkout_version(repo: Path) -> str | None:
    """READ WITH A TOML PARSER rather than a regex, because `version = "1.1.3"` also appears in
    this file's dependency pins and a regex that found the wrong one would be a silent misreport
    — the exact failure class this function exists to close.

    @brief Declared version from the tree.
    @return Version, or None.
    @version 2
    """
    ## `clew.tomlcompat` IS THE ONLY TOML IMPORT IN THIS TREE, and a test enforces it. The first
    ## version of this function hand-rolled the `tomllib`/`tomli` fallback and the gate refused
    ## the commit — which is exactly the divergence `tomlcompat`'s own docstring describes, where
    ## one of two copies of a shim ends up without the compatibility. `toml_module` rather than
    ## `require_toml_module`: this function is probing, and an unreadable version is ABSENT by
    ## this module's rule, not an error that should stop a grid.
    from clew.tomlcompat import toml_module

    parser = toml_module()
    if parser is None:  # pragma: no cover - requires an interpreter with no TOML parser
        return None
    try:
        data = parser.loads((repo / "pyproject.toml").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    declared = data.get("project", {}).get("version")
    return str(declared) if declared else None


## @brief Everything a reader needs to attribute a score to a build of clew.
## @param repo The clew checkout to describe; defaults to the installed package's own tree.
## @return A mapping of identity fields, each omitted when it could not be read.
##
## v2: the recorded version comes from the checkout rather than the installed metadata, because
## an editable install's metadata goes stale at the first version bump and was misstating it.
## @version 2
def tool_identity(repo: Path | None = None) -> dict:
    """DERIVED FROM THE INSTALLED PACKAGE, not from the current working directory. The grid is
    driven from the repository today, but the harness is an entry point like any other and a
    `cwd` is not evidence of which clew answered — `clew.signature`'s own location is.

    @brief The identity of the clew under test.
    @return Identity fields.
    @version 2
    """
    import clew

    if repo is None:
        repo = Path(clew.__file__).resolve().parent.parent
    out: dict = {"clew_build_version": str(CLEW_BUILD_VERSION)}
    ## THE CHECKOUT WINS OVER THE INSTALL. `pip install -e .` stamps the version into
    ## `.dist-info` once and never again, so a bumped `pyproject.toml` leaves the metadata behind
    ## — three 1.2.0 pre-flight records stamped `clew_version: 1.1.0` onto a 1.1.3 tree. The tree
    ## describes the code that will answer the questions; the metadata describes an install event
    ## that is over. Disagreement is KEPT rather than corrected away, because an operator whose
    ## environment lags the tree is a fact a reader of a published number wants, and absent when
    ## they agree, so the key means something every time it appears.
    installed = _installed_version()
    declared = _checkout_version(repo)
    if declared:
        out["clew_version"] = declared
        if installed and installed != declared:
            out["clew_version_installed"] = installed
    elif installed:
        out["clew_version"] = installed
    out.update(_checkout(repo))
    out.update(_substrate())
    return out
