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
  * a mutation record that cannot be read, or names a mechanism the index does not hold (W9);
  * a result report, mapping file, gcov or feature glob that is missing or matches nothing, an
    undeclared result format, or a mapping row naming an unknown requirement (W15/W16);
  * a theme stylesheet, logo or roadmap that does not exist, or an unknown palette token (W13/W17).

An empty list is a clean check. This module imports nothing from Sphinx or MyST, and a test pins
that.

@brief Validate a repository's wiki configuration against its index.
@version 3
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
## v3: theme files and the roadmap (W13/W17).
## v4: `before_tests` — reports a test run produces are not yet required (round 3, P6c).
## @param before_tests True in a hook that runs before the tests write their reports.
## @version 4
## @req REQ-DDB-WIKI-003
def check_wiki(
    repo_root: Path, db: Path, config_path: Path | None = None, *, before_tests: bool = False
) -> list[str]:
    """@brief Run every check. @return Problems."""
    repo_root = Path(repo_root)
    config, problems = load_wiki_config(repo_root, config_path)
    problems += _docs_problems(repo_root, config)
    problems += _flow_problems(db, config)
    problems += _evidence_problems(repo_root, config, before_tests)
    if config.link_template and "{file}" not in config.link_template:
        problems.append("`wiki.links.template` has no `{file}` placeholder")
    problems += trace_problems(repo_root, db, config)
    return problems + _site_problems(repo_root, config)


## @brief A problem for each theme file or roadmap the section names that does not exist.
## @param repo_root The repository.
## @param config The section.
## @return Problems.
## @version 1
## @utility
def _site_problems(repo_root: Path, config: WikiConfig) -> list[str]:
    """@brief Check theme and roadmap paths. @return Problems."""
    named = [
        *(("stylesheet", c) for c in config.theme.css),
        *((("logo", config.theme.logo),) if config.theme.logo else ()),
        *((("roadmap", config.roadmap),) if config.roadmap else ()),
    ]
    return [
        f"{what} {rel!r} does not exist" for what, rel in named if not (repo_root / rel).is_file()
    ]


## @brief Problems with the trace targets: nodes, catalogs, rules and mutation records.
## @param repo_root The repository.
## @param db Its index.
## @param config The section.
## @return Problems.
## v2: the mapping file's requirement ids (W16).
## v3: the composite requirement tree's dangling links and pin conflicts (GH #68).
## @version 3
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
    if config.catalogs:
        from .composite import composite_problems

        # GH #68: the composite's dangling links and pin conflicts; a catalogue that cannot be
        # read is already reported above, by the same reader, so it is not repeated.
        problems += [
            p for p in composite_problems(repo_root, list(config.catalogs)) if p not in problems
        ]
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
    return (
        problems
        + _mutation_problems(repo_root, db, config)
        + _mapping_problems(repo_root, config, known)
    )


## @brief Problems with the requirement → test mapping file (W16).
## @param repo_root The repository.
## @param config The section.
## @param known Every requirement id declared or tagged.
## @return Problems; [] when no mapping is declared or it does not exist (reported elsewhere).
## @version 1
## @utility
def _mapping_problems(repo_root: Path, config: WikiConfig, known: set[str]) -> list[str]:
    """@brief Check mapping ids. @return Problems."""
    from .imports import parse_mapping

    path = repo_root / config.inputs.mapping if config.inputs.mapping else None
    if path is None or not path.is_file():
        return []
    try:
        mapping = parse_mapping(path)
    except (ValueError, OSError) as exc:
        return [f"mapping file {config.inputs.mapping!r} cannot be read: {exc}"]
    return [
        f"mapping file {config.inputs.mapping!r} names requirement {r!r}, which nothing declares"
        for r in mapping
        if r not in known
    ]


## @brief Every requirement id the index declares or tags.
## @param db The index.
## @return Ids.
## @version 1
## @utility
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
## @utility
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
## v2: only declared globs are checked (2.0.0)
## @version 2
## @utility
def _docs_problems(repo_root: Path, config: WikiConfig) -> list[str]:
    """ONLY A DECLARED GLOB (2.0.0, consumer finding): a repository with Markdown prose and no
    `wiki:` section was told the built-in default `docs/**/*.rst` "matches no file", a glob it
    never wrote. @brief Check prose globs. @return Problems.
    """
    if not config.docs_declared:
        return []
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
## @utility
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
## v3: the W15/W16 imports: result reports, gcov and feature globs, the mapping file.
## v4: `before_tests` drops the reports a test run produces (round 3, P6c).
## @param before_tests True when the tests have not run yet.
## v5: names the top-level tests: section (2.0.0, R5-CFG F20)
## @version 5
## @utility
def _evidence_problems(
    repo_root: Path, config: WikiConfig, before_tests: bool = False
) -> list[str]:
    """A GLOB THAT MATCHES NOTHING IS A PROBLEM: a misspelled gcov or feature glob would yield a
    trace that reads as "nothing measured".

    BEFORE THE TESTS, only what the repository HOLDS is required: JUnit, coverage, result
    reports and gcov are what the run writes, so a pre-commit hook cannot see them. The full
    check — after the tests, in CI — still names every missing one.

    @brief Check report paths.
    @return Problems.
    """
    inputs = config.inputs
    produced = [
        *config.junit,
        *([config.coverage] if config.coverage else []),
        *(path for _fmt, path in inputs.results),
    ]
    reports = [
        *([] if before_tests else produced),
        *([config.mutations] if config.mutations else []),
        *([inputs.mapping] if inputs.mapping else []),
    ]
    problems = [
        f"test report {r!r} does not exist" for r in reports if not (repo_root / r).is_file()
    ]
    globbed = (
        (("features", inputs.features),)
        if before_tests
        else (
            ("gcov", inputs.gcov),
            ("features", inputs.features),
        )
    )
    for key, globs in globbed:
        problems += [
            f"`tests.{key}` glob {g!r} matches no file"
            for g in globs
            if not any(p.is_file() for p in repo_root.glob(g))
        ]
    return problems
