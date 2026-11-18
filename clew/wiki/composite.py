# SPDX-License-Identifier: MIT
"""The composite requirement tree: a product's requirements and every pinned dependency's (GH #68).

OWNER 2026-11-16: composite a complete project's requirements from all its dependencies. This
repository's catalogue is the ROOT. Each dependency catalogue — `wiki.catalogs`, read AT ITS PIN —
contributes the requirements whose `satisfies` reaches the ones above it, transitively: a
dependency's own `.clew.yaml` is read at that same pin, so its `wiki.catalogs` and pinned
`impact.requirements.external` entries are followed too. Every id is namespaced
`<catalog>:<id>`; a bare `satisfies` id resolves in the catalogue that pulled this one in, then
the root, then its own.

THE PIN RULE (owner, revised 2026-11-16 — "better to state unknown than show old/stale code by a
bad ref"): a dependency's implementers and tests are read from ITS index only when that index
describes the pinned code — checkout AT the pin, no uncommitted changes, index current. Otherwise
the row is UNKNOWN with the reason and a link to the local checkout; with no index at all it is
ABSENT. Unknown and absent rows carry no evidence fields (None, never an empty tuple, which would
read as "nothing implements this").

Reported, never merged or silently dropped: dangling links, one repository pinned at two
revisions (the first read wins and the second is named), and requirements nothing on the root's
tree reaches. A repository already read at its pin is not read again, so a cycle terminates.

@brief Compose the requirement tree across pinned dependency catalogues.
@version 1
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..requirements import git_text, read_catalog_at, satisfies_ids
from .config import CatalogSpec

## (state, note, index path or None) — what is known about one dependency's index.
Probe = Callable[[Path, str, "str | None"], tuple[str, str, "Path | None"]]
## (implementers, tests) of one requirement in one index.
Trace = Callable[[Path, str], tuple[tuple[str, ...], tuple[str, ...]]]


## @brief One requirement on the composite tree.
## @version 1
@dataclass(frozen=True)
class Node:
    """`evidence` is "indexed" | "unknown" | "absent"; implementers/tests are None unless indexed.

    @brief A namespaced requirement with its evidence state.
    """

    ref: str
    catalog: str
    req_id: str
    title: str
    pin: str
    evidence: str
    note: str
    link: str
    implementers: tuple[str, ...] | None
    tests: tuple[str, ...] | None
    satisfied_by: tuple[str, ...] = ()


## @brief The composed tree and what it found wrong.
## @version 1
@dataclass(frozen=True)
class Composite:
    """@brief Roots, nodes by ref, and the reported problems."""

    roots: tuple[str, ...]
    nodes: dict[str, Node]
    unreached: tuple[str, ...]
    dangling: tuple[tuple[str, str], ...]
    conflicts: tuple[str, ...]
    ## Dependency requirements this repository's own code tags (the W8 direction): served here.
    implemented_here: tuple[str, ...] = ()


## @brief One catalogue read into the walk.
## @version 1
@dataclass
class _Source:
    """@brief A catalogue, where it lives, who pulled it in, and its evidence state."""

    name: str
    repo: Path
    pin: str
    parent: str
    rows: dict[str, dict[str, str]]
    state: tuple[str, str, Path | None]
    links: dict[str, list[str]] = field(default_factory=dict)
    ## The root's own catalogue ids (the rest of its rows come from its index's tags).
    declared: set[str] = field(default_factory=set)


## @brief Whether a dependency's index describes its pinned code.
## @param dep The dependency checkout.
## @param pin The pin as written.
## @param pin_sha The pin resolved to a commit, or None.
## @param locate Checkout -> its index path, or None.
## @param is_stale (index, checkout) -> whether the index is older than the checkout.
## @return (state, note, index path or None).
## @version 1
## @req REQ-DDB-WIKI-040
def probe_index(
    dep: Path,
    pin: str,
    pin_sha: str | None,
    *,
    locate: Callable[[Path], Path | None] | None = None,
    is_stale: Callable[[Path, Path], bool] | None = None,
) -> tuple[str, str, Path | None]:
    """FIRST FAILING CHECK WINS, each named, so the page says exactly why evidence is withheld.

    @brief Probe a dependency's index against its pin.
    @return State, note, index.
    """
    db = (locate or _locate)(dep)
    if db is None:
        return ("absent", f"{dep.name} is not indexed on this machine", None)
    head = (git_text(dep, "rev-parse", "HEAD") or "").strip()
    checks = (
        (lambda: pin_sha is None, f"pin {pin} does not resolve in {dep.name}"),
        (lambda: head != pin_sha, f"not indexed at pin {pin[:12]}; checkout is at {head[:12]}"),
        (
            lambda: bool(
                (git_text(dep, "status", "--porcelain", "--untracked-files=no") or "").strip()
            ),
            f"{dep.name} has uncommitted changes, so its index is not the pinned code",
        ),
        (lambda: (is_stale or _stale)(db, dep), f"{dep.name}'s index is older than its checkout"),
    )
    note = next((msg for failed, msg in checks if failed()), "")
    return ("unknown" if note else "indexed", note, db)


## @brief The index registered for a checkout, if one was built.
## @param dep The checkout.
## @return Its database path, or None.
## @version 1
## @dg_internal
def _locate(dep: Path) -> Path | None:
    """@brief Locate. @return Path or None."""
    from ..mcp_server.state import target_for

    db = Path(target_for(dep).db_path)
    return db if db.is_file() else None


## @brief Whether an index is stale against its checkout.
## @param db The index.
## @param dep The checkout.
## @return True when stale.
## @version 1
## @dg_internal
def _stale(db: Path, dep: Path) -> bool:
    """@brief Stale. @return Bool."""
    from ..mcp_server.state import db_status, target_for

    target = target_for(dep)
    if Path(target.db_path) != db:
        return True
    return bool(db_status(target).get("stale", True))


## @brief A requirement's implementers and tests in one index.
## @param db The index.
## @param req_id The requirement.
## @return (implementer names, test names).
## @version 1
## @dg_internal
def _trace(db: Path, req_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """@brief Trace. @return Names."""
    from ..query.symbols import req_trace

    found = req_trace(db, req_id)
    return tuple(i.name for i in found.implementers), tuple(found.tests)


## @brief Compose the requirement tree rooted at this repository's catalogue.
## @param repo_root This repository.
## @param root_name The root catalogue's namespace.
## @param specs This repository's pinned dependency catalogues.
## @param probe Dependency evidence probe (default: `probe_index` on the registered index).
## @param trace Requirement trace reader (default: the index's `req_trace`).
## @param root_db This repository's own index, for the root rows' evidence.
## @return The composite.
## v2: roots include ids the index knows from tags; dependency rows tagged here are served here,
## carrying this repository's evidence; a tagged id a dependency catalogue holds is not a root.
## @version 2
## @req REQ-DDB-WIKI-040
def compose(
    repo_root: Path,
    root_name: str,
    specs: list[CatalogSpec],
    *,
    probe: Probe | None = None,
    trace: Trace | None = None,
    root_db: Path | None = None,
) -> Composite:
    """AN ID A DEPENDENCY'S CATALOGUE HOLDS IS THAT CATALOGUE'S: tagged here without a local
    catalogue entry, it is not also a root — it is listed as implemented here, with THIS
    repository's functions and tests rather than the dependency's index state.

    @brief Read every catalogue, link, mark reach.
    @return Composite.
    """
    trace = trace or _trace
    root = _root_source(Path(repo_root), root_name, root_db)
    sources, conflicts = _walk(Path(repo_root), root_name, specs, probe or _probe_default)
    dep_ids = {rid for s in sources for rid in s.rows}
    root.rows = {k: v for k, v in root.rows.items() if k in root.declared or k not in dep_ids}
    sources.insert(0, root)
    nodes, dangling = _nodes(sources, trace)
    roots = tuple(f"{root_name}:{rid}" for rid in sorted(root.rows))
    tagged = _tagged(root_db)
    here = tuple(
        sorted(r for r, n in nodes.items() if n.catalog != root_name and n.req_id in tagged)
    )
    for ref in here:
        nodes[ref] = _served_here(nodes[ref], root.state, trace)
    reached = _reach(roots, nodes) | set(here)
    unreached = tuple(sorted(r for r in nodes if r not in reached))
    return Composite(roots, nodes, unreached, tuple(dangling), tuple(conflicts), here)


## @brief The default probe: `probe_index` with the registered index.
## @param dep Checkout.
## @param pin Pin.
## @param sha Resolved pin.
## @return Probe result.
## @version 1
## @dg_internal
def _probe_default(dep: Path, pin: str, sha: str | None) -> tuple[str, str, Path | None]:
    """@brief Probe. @return State."""
    return probe_index(dep, pin, sha)


## @brief The root catalogue as a source.
## @param repo_root This repository.
## @param name Its namespace.
## @param db Its index, if any.
## @return The source.
## v2: plus every requirement the index knows, tagged-only ones included.
## @version 2
## @dg_internal
def _root_source(repo_root: Path, name: str, db: Path | None) -> _Source:
    """@brief Root. @return Source."""
    from .catalogs import declared_catalog

    _path, entries = declared_catalog(repo_root)
    rows = {rid: {k: v for k, v in e.items()} for rid, e in entries.items()}
    # THE REQUIREMENTS PAGE'S SET: catalogue entries and every id the index knows (tags too).
    for rid, title in _indexed_requirements(db).items():
        rows.setdefault(rid, {"title": title})
    state = ("indexed", "", db) if db else ("absent", "this repository's index was not given", None)
    return _Source(name, repo_root, "", "", rows, state, declared=set(entries))


## @brief Every requirement id this repository's index knows, with its title.
## @param db The index, or None.
## @return {id: title}; {} without an index.
## @version 1
## @dg_internal
def _indexed_requirements(db: Path | None) -> dict[str, str]:
    """@brief Catalogue table plus tagged ids. @return Ids."""
    out = {rid: "" for rid in _tagged(db)}
    for rid, title in _rows(db, "SELECT id, COALESCE(title, '') FROM requirements"):
        out[str(rid)] = str(title)
    return out


## @brief The requirement ids this repository's code tags (`@req`).
## @param db The index, or None.
## @return Ids.
## @version 1
## @dg_internal
def _tagged(db: Path | None) -> set[str]:
    """@brief Tagged ids. @return Set."""
    return {str(r[0]) for r in _rows(db, "SELECT DISTINCT req_id FROM req_edges")}


## @brief Rows of a read-only query, or none when the index or table is missing.
## @param db The index, or None.
## @param sql The query.
## @return Rows.
## @version 1
## @dg_internal
def _rows(db: Path | None, sql: str) -> list[tuple]:
    """ABSENT IS NOT AN ERROR here: an index without the table simply contributes no ids.

    @brief Query.
    @return Rows.
    """
    import sqlite3

    if db is None or not Path(db).is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []


## @brief Read every dependency catalogue reachable from the root's specs.
## @param repo_root This repository.
## @param root_name Its namespace.
## @param specs Its pinned catalogues.
## @param probe Evidence probe.
## @return (sources, conflict messages).
## @version 1
## @dg_internal
def _walk(
    repo_root: Path, root_name: str, specs: list[CatalogSpec], probe: Probe
) -> tuple[list[_Source], list[str]]:
    """A REPOSITORY READ ONCE PER PIN: a second pin of the same checkout is a conflict, a second
    sight at the same pin is a cycle or diamond and is skipped.

    @brief Breadth-first walk.
    @return Sources and conflicts.
    """
    queue = [(repo_root, root_name, s) for s in specs]
    seen: dict[Path, str] = {}
    sources: list[_Source] = []
    conflicts: list[str] = []
    while queue:
        base, parent, spec = queue.pop(0)
        dep = (base / spec.repo).resolve()
        if dep in seen:
            if seen[dep] != spec.pin:
                conflicts.append(
                    f"{dep.name} is pinned at {seen[dep][:12]} and at {spec.pin[:12]} "
                    f"(via {parent}); the first is used"
                )
            continue
        seen[dep] = spec.pin
        source = _read_source(base, parent, spec, probe, conflicts)
        if source is not None:
            sources.append(source)
            queue += [(dep, spec.name, s) for s in _nested_specs(dep, spec.pin)]
    return sources, conflicts


## @brief Read one dependency catalogue at its pin.
## @param base The checkout the spec is relative to.
## @param parent The catalogue that named it.
## @param spec The spec.
## @param probe Evidence probe.
## @param problems Collector for an unreadable catalogue.
## @return The source, or None when unreadable.
## @version 1
## @dg_internal
def _read_source(
    base: Path, parent: str, spec: CatalogSpec, probe: Probe, problems: list[str]
) -> _Source | None:
    """@brief Read. @return Source or None."""
    dep = (base / spec.repo).resolve()
    try:
        rows = read_catalog_at(base, {"repo": spec.repo, "rev": spec.pin, "path": spec.catalog})
    except ValueError as exc:
        problems.append(f"catalog {spec.name!r}: {exc}")
        return None
    sha = (
        git_text(dep, "rev-parse", "--verify", "--quiet", f"{spec.pin}^{{commit}}") or ""
    ).strip()
    return _Source(spec.name, dep, spec.pin, parent, rows, probe(dep, spec.pin, sha or None))


## @brief The pinned catalogues a dependency itself names, read from its `.clew.yaml` at the pin.
## @param dep The dependency checkout.
## @param pin Its pin.
## @return Specs relative to `dep`.
## v2: reads requirements.external; 1.x locations only at a pinned dependency (2.0.0)
## @version 2
## @dg_internal
def _nested_specs(dep: Path, pin: str) -> list[CatalogSpec]:
    """The PINNED `requirements.external` entries (a path-only external is the dependency's own
    file and adds no repository).

    A DEPENDENCY IS READ AT ITS PIN, so its `.clew.yaml` may predate 2.0.0: the 1.x locations —
    `wiki.catalogs` and `guard.impact.requirements.external` — are still read here, and only
    here. This repository's own file refuses them (R5-CFG F6/F7); a pinned dependency cannot be
    asked to migrate a revision that is already history.

    @brief Nested specs.
    @return Specs.
    """
    import yaml

    text = git_text(dep, "show", f"{pin}:.clew.yaml")
    try:
        doc = yaml.safe_load(text or "") or {}
    except yaml.YAMLError:
        return []
    doc = doc if isinstance(doc, dict) else {}
    wiki = doc.get("wiki") or {}
    guard = doc.get("guard") or {}
    top = doc.get("requirements") if isinstance(doc.get("requirements"), dict) else {}
    legacy = ((guard.get("impact") or {}).get("requirements") or {}).get("external") or []
    specs = [
        CatalogSpec(str(c["name"]), str(c["repo"]), str(c["pin"]), str(c["catalog"]))
        for c in wiki.get("catalogs") or []
        if isinstance(c, dict) and {"name", "repo", "pin", "catalog"} <= set(c)
    ]
    specs += [
        CatalogSpec(
            str(e.get("name") or Path(str(e["repo"])).name),
            str(e["repo"]),
            str(e["rev"]),
            str(e["path"]),
        )
        for e in [*(top.get("external") or []), *legacy]
        if isinstance(e, dict) and {"repo", "rev", "path"} <= set(e)
    ]
    return specs


## @brief Build every node and link it to what it satisfies.
## @param sources Every catalogue read.
## @param trace Requirement trace reader.
## @return (nodes by ref, dangling (ref, target) pairs).
## @version 1
## @dg_internal
def _nodes(sources: list[_Source], trace: Trace) -> tuple[dict[str, Node], list[tuple[str, str]]]:
    """@brief Nodes and links. @return Nodes, dangling."""
    by_name = {s.name: s for s in sources}
    root = sources[0].name
    edges: dict[str, list[str]] = {}
    dangling: list[tuple[str, str]] = []
    for s in sources:
        for rid, row in s.rows.items():
            ref = f"{s.name}:{rid}"
            for target in satisfies_ids(row.get("satisfies")):
                hit = _resolve(target, (s.parent, root, s.name), by_name)
                if hit:
                    edges.setdefault(hit, []).append(ref)
                else:
                    dangling.append(
                        (ref, target if ":" in target else f"{s.parent or root}:{target}")
                    )
    nodes = {
        f"{s.name}:{rid}": _node(
            s, rid, row, trace, tuple(sorted(edges.get(f"{s.name}:{rid}", [])))
        )
        for s in sources
        for rid, row in s.rows.items()
    }
    return nodes, dangling


## @brief Resolve a `satisfies` id to a node ref.
## @param target `<catalog>:<id>` or a bare id.
## @param order Namespaces a bare id is looked up in.
## @param by_name Sources by namespace.
## @return The ref, or "" when it resolves nowhere.
## @version 1
## @dg_internal
def _resolve(target: str, order: tuple[str, ...], by_name: dict[str, _Source]) -> str:
    """@brief Resolve. @return Ref or ''."""
    if ":" in target:
        ns, rid = target.split(":", 1)
        return target if ns in by_name and rid in by_name[ns].rows else ""
    return next(
        (f"{ns}:{target}" for ns in order if ns in by_name and target in by_name[ns].rows), ""
    )


## @brief One node, with evidence only when its index describes the pinned code.
## @param s Its source.
## @param rid Its id.
## @param row Its catalogue row.
## @param trace Trace reader.
## @param satisfied_by Refs that satisfy it.
## @return The node.
## @version 1
## @dg_internal
def _node(s: _Source, rid: str, row: dict, trace: Trace, satisfied_by: tuple[str, ...]) -> Node:
    """@brief Node. @return Node."""
    state, note, db = s.state
    impl, tests = trace(db, rid) if state == "indexed" and db is not None else (None, None)
    title = str(row.get("title") or row.get("name") or "")
    link = "" if not s.pin else str(s.repo)
    return Node(
        f"{s.name}:{rid}", s.name, rid, title, s.pin, state, note, link, impl, tests, satisfied_by
    )


## @brief A dependency requirement this repository implements, with this repository's evidence.
## @param node The dependency's node.
## @param state This repository's index state.
## @param trace Trace reader.
## @return The node, re-evidenced from here.
## @version 1
## @dg_internal
def _served_here(node: Node, state: tuple[str, str, Path | None], trace: Trace) -> Node:
    """@brief Re-evidence. @return Node."""
    import dataclasses

    ev, note, db = state
    impl, tests = trace(db, node.req_id) if ev == "indexed" and db is not None else (None, None)
    return dataclasses.replace(
        node,
        evidence=ev,
        note=note or "implemented in this repository",
        link="",
        implementers=impl,
        tests=tests,
    )


## @brief Every ref reachable from the roots through `satisfied_by`.
## @param roots Root refs.
## @param nodes Nodes by ref.
## @return Reached refs (a cycle is visited once).
## @version 1
## @dg_internal
def _reach(roots: tuple[str, ...], nodes: dict[str, Node]) -> set[str]:
    """@brief Reach. @return Refs."""
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        ref = stack.pop()
        if ref in seen or ref not in nodes:
            continue
        seen.add(ref)
        stack += nodes[ref].satisfied_by
    return seen


## @brief The composite's problems, for `clew wiki check`.
## @param repo_root This repository.
## @param specs Its pinned catalogues.
## @param probe Evidence probe (check needs none; the default skips index lookups).
## @return Problems: dangling links and pin conflicts, each named.
## @version 1
## @req REQ-DDB-WIKI-040
def composite_problems(
    repo_root: Path, specs: list[CatalogSpec], *, probe: Probe | None = None
) -> list[str]:
    """CHEAP: the default probe reads no index — check is about the catalogues, not evidence.

    @brief Check the composite.
    @return Problems.
    """
    tree = compose(Path(repo_root), Path(repo_root).name, specs, probe=probe or _no_probe)
    return [
        f"{ref} satisfies {target}, which no catalogue on the composite holds"
        for ref, target in tree.dangling
    ] + list(tree.conflicts)


## @brief A probe that looks at no index.
## @param dep Checkout.
## @param pin Pin.
## @param sha Resolved pin.
## @return An absent state.
## @version 1
## @dg_internal
def _no_probe(dep: Path, pin: str, sha: str | None) -> tuple[str, str, Path | None]:
    """@brief No probe. @return Absent."""
    return ("absent", "", None)
