# SPDX-License-Identifier: MIT
"""`clew wiki check`: everything the `wiki:` section points at exists — cheap, and Sphinx-free.

1.4.0 Track 4, W5 (#67's fifth consumer: `check` must run in a pre-commit / CI static stage, with
no Sphinx import; `build` is a separate stage). Every problem is NAMED, one line each:

  * a key the section does not know;
  * a `docs` glob that matches no file;
  * a flow entry (or qualified identity) the index does not hold, or an unknown lane strategy;
  * a JUnit or Cobertura report that does not exist;
  * a link template with no `{file}` placeholder.

An empty list is a clean check. This module imports nothing from Sphinx or MyST, and a test pins
that.

@brief Validate a repository's wiki configuration against its index.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from .config import WikiConfig, load_wiki_config


## @brief Every problem with a repository's wiki configuration, against its index.
## @param repo_root The repository.
## @param db Its index.
## @return Problems, one sentence each; [] when clean.
## @version 1
## @req REQ-DDB-WIKI-003
def check_wiki(repo_root: Path, db: Path) -> list[str]:
    """@brief Run every check. @return Problems."""
    config, problems = load_wiki_config(Path(repo_root))
    problems += _docs_problems(Path(repo_root), config)
    problems += _flow_problems(db, config)
    problems += _evidence_problems(Path(repo_root), config)
    if config.link_template and "{file}" not in config.link_template:
        problems.append("`wiki.links.template` has no `{file}` placeholder")
    return problems


## @brief A problem for each docs glob that matches nothing.
## @param repo_root The repository.
## @param config The section.
## @return Problems.
## @version 1
## @dg_internal
def _docs_problems(repo_root: Path, config: WikiConfig) -> list[str]:
    """@brief Check prose globs. @return Problems."""
    return [
        f"`wiki.docs` entry {pattern!r} matches no file"
        for pattern in config.docs
        if not any(repo_root.glob(pattern))
    ]


## @brief A problem for each flow whose entry or lanes cannot be derived.
## @param db The index.
## @param config The section.
## @return Problems.
## @version 1
## @dg_internal
def _flow_problems(db: Path, config: WikiConfig) -> list[str]:
    """@brief Check flows against the index. @return Problems."""
    from ..query._common import connect, identity_rowids
    from .flow import LANES

    problems = []
    with connect(db) as conn:
        for spec in config.flows:
            if spec.lanes not in LANES:
                problems.append(
                    f"flow {spec.entry!r}: unknown lanes {spec.lanes!r} ({', '.join(LANES)})"
                )
            if not identity_rowids(conn, spec.entry, spec.qualified):
                problems.append(
                    f"flow entry {spec.entry!r} (qualified={spec.qualified!r}) is not in the index"
                )
    return problems


## @brief A problem for each evidence report that does not exist.
## @param repo_root The repository.
## @param config The section.
## @return Problems.
## @version 1
## @dg_internal
def _evidence_problems(repo_root: Path, config: WikiConfig) -> list[str]:
    """@brief Check report paths. @return Problems."""
    reports = [*config.junit, *([config.coverage] if config.coverage else [])]
    return [f"test report {r!r} does not exist" for r in reports if not (repo_root / r).is_file()]
