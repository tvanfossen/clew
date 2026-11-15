# SPDX-License-Identifier: MIT
"""`clew wiki check`: everything the `wiki:` section points at exists — cheap, and Sphinx-free.

1.4.0 Track 4, W5 (#67's fifth consumer: `check` must run in a pre-commit / CI static stage, with
no Sphinx import; `build` is a separate stage). Every problem is NAMED, one line each:

  * a key the section does not know;
  * a `docs` glob that matches no file;
  * a flow entry (or qualified identity) the index does not hold, or an unknown lane strategy;
  * a JUnit or Cobertura report that does not exist;
  * a link template with no `{file}` placeholder;
  * an external node source that cannot be read, or a `@node` tag naming a node no source
    declares (W7);
  * a sub-catalog pin that does not resolve, or a catalog that moved since its pin (W8);
  * a rule, or a node, naming a requirement nothing declares or tags (W8);
  * a mutation record that cannot be read, or names a mechanism the index does not hold (W9).

An empty list is a clean check. This module imports nothing from Sphinx or MyST, and a test pins
that.

@brief Validate a repository's wiki configuration against its index.
@version 2
"""

from __future__ import annotations

from pathlib import Path

from .config import WikiConfig, load_wiki_config


## @brief Every problem with a repository's wiki configuration, against its index.
## @param repo_root The repository.
## @param db Its index.
## @param config_path A file whose `wiki:` section applies instead of the repository's.
## @return Problems, one sentence each; [] when clean.
## v2: nodes, catalogs, rules, mutations; `config_path`.
## @version 2
## @req REQ-DDB-WIKI-003
def check_wiki(repo_root: Path, db: Path, config_path: Path | None = None) -> list[str]:
    """@brief Run every check. @return Problems."""
    repo_root = Path(repo_root)
    config, problems = load_wiki_config(repo_root, config_path)
    problems += _docs_problems(repo_root, config)
    problems += _flow_problems(db, config)
    problems += _evidence_problems(repo_root, config)
    if config.link_template and "{file}" not in config.link_template:
        problems.append("`wiki.links.template` has no `{file}` placeholder")
    problems += trace_problems(repo_root, db, config)
    return problems


## @brief Problems with the trace targets: nodes, catalogs, rules and mutation records.
## @param repo_root The repository.
## @param db Its index.
## @param config The section.
## @return Problems.
## @version 1
## @req REQ-DDB-WIKI-005
def trace_problems(repo_root: Path, db: Path, config: WikiConfig) -> list[str]:
    """@brief Check W7–W9 targets. @return Problems."""
    from .catalogs import catalog_requirements, pin_problems
    from .sources import load_nodes, node_references

    nodes, problems = load_nodes(repo_root, config.sources)
    declared = {n.ref for n in nodes}
    for ref, names in node_references(db).items():
        if config.sources and ref not in declared:
            problems.append(f"`@node {ref}` on {', '.join(names)} names a node no source declares")
    known = _known_requirements(db)
    for spec in config.catalogs:
        pins = pin_problems(repo_root, spec)
        problems += pins
        if not pins:
            rows, more = catalog_requirements(repo_root, spec)
            problems += more
            known |= {r.req_id for r in rows}
    for rule in config.rules:
        problems += [
            f"rule {rule.id!r} names requirement {r!r}, which nothing declares or tags"
            for r in rule.requirements
            if r not in known
        ]
    for node in nodes:
        problems += [
            f"node {node.ref!r} serves requirement {r!r}, which nothing declares or tags"
            for r in node.requirements
            if r not in known
        ]
    return problems + _mutation_problems(repo_root, db, config)


## @brief Every requirement id the index declares or tags.
## @param db The index.
## @return Ids.
## @version 1
## @dg_internal
def _known_requirements(db: Path) -> set[str]:
    """@brief Collect ids. @return Ids."""
    from ..query._common import connect
    from .evidence import _requirement_ids

    with connect(db) as conn:
        return {i for i, _t in _requirement_ids(conn)}


## @brief Problems with the mutation record.
## @param repo_root The repository.
## @param db The index.
## @param config The section.
## @return Problems.
## @version 1
## @dg_internal
def _mutation_problems(repo_root: Path, db: Path, config: WikiConfig) -> list[str]:
    """A MECHANISM THE INDEX DOES NOT HOLD attaches to no requirement, so the record's strongest
    evidence would silently vanish from the trace — named instead.

    @brief Check mutation records.
    @return Problems.
    """
    from ..query._common import connect, identity_rowids
    from .evidence import parse_mutations

    if not config.mutations or not (repo_root / config.mutations).is_file():
        return []
    try:
        records = parse_mutations(repo_root / config.mutations)
    except (OSError, ValueError) as exc:
        return [f"mutation record: {exc}"]
    with connect(db) as conn:
        return [
            f"mutation record names mechanism {m!r}, which the index does not hold"
            for m in sorted({m for m, _t, _k in records})
            if not identity_rowids(conn, m, None)
        ]


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
## v2: the mutation record too.
## @version 2
## @dg_internal
def _evidence_problems(repo_root: Path, config: WikiConfig) -> list[str]:
    """@brief Check report paths. @return Problems."""
    reports = [
        *config.junit,
        *([config.coverage] if config.coverage else []),
        *([config.mutations] if config.mutations else []),
    ]
    return [f"test report {r!r} does not exist" for r in reports if not (repo_root / r).is_file()]
