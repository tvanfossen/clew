# SPDX-License-Identifier: MIT
"""The composite requirement tree across pinned dependencies (GH #68, P6b-3a).

OWNER 2026-11-16: composite a product's complete requirements from all its dependencies. The
product catalogue is the root; each dependency catalogue (`wiki.catalogs`, read AT ITS PIN) adds
the requirements that `satisfies` the ones above it, transitively through each dependency's own
`.clew.yaml` read at that same pin. Ids are namespaced `<catalog>:<id>`.

THE PIN RULE (owner, revised the same day): evidence — implementers, tests — is shown only when
the dependency's index describes the pinned code: its checkout is AT the pin, has no uncommitted
changes, and its index is current. Otherwise the row says UNKNOWN and why, and links to the local
checkout; never evidence from other code. A dependency with no index is ABSENT. "Better to state
unknown than show old/stale code by a bad ref."

Reported, never merged or dropped: a `satisfies` id that resolves nowhere (dangling), one
repository pinned at two revisions (conflict), and requirements nothing on the product's tree
reaches (unreached).

@brief Tests for the composite requirement tree.
@version 1
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from clew.wiki.composite import compose, probe_index


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _repo(path: Path, catalog: str, clew_yaml: str = "") -> str:
    """@brief A git repo with a catalogue (and a .clew.yaml); returns its HEAD sha."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "requirements.yaml").write_text(catalog)
    if clew_yaml:
        (path / ".clew.yaml").write_text(clew_yaml)
    if not (path / ".git").exists():
        _git(path, "init", "-q")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "c")
    return _git(path, "rev-parse", "HEAD")


def _catalogs(*rows: tuple[str, str, str]) -> str:
    body = "".join(
        f"    - {{name: {n}, repo: {r}, pin: {p}, catalog: requirements.yaml}}\n"
        for n, r, p in rows
    )
    return f"wiki:\n  catalogs:\n{body}"


def _fixture(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """product -> lib -> hal, each pinned."""
    hal = _repo(
        tmp_path / "hal",
        "requirements:\n  REQ-HAL-001:\n    name: Timer fires\n    satisfies: lib:REQ-LIB-001\n",
    )
    lib = _repo(
        tmp_path / "lib",
        "requirements:\n"
        "  REQ-LIB-001:\n    name: Bounded retry\n    satisfies: [product:REQ-PRD-001]\n"
        "  REQ-LIB-002:\n    name: Unused by the product\n",
        _catalogs(("hal", "../hal", hal)),
    )
    product = tmp_path / "product"
    product.mkdir()
    (product / "requirements.yaml").write_text(
        "requirements:\n  REQ-PRD-001:\n    name: Survives a dropped link\n"
        "  REQ-PRD-002:\n    name: Reports a dropped link\n"
    )
    return product, {"lib": lib, "hal": hal}


def _specs(product: Path, pins: dict[str, str]):
    from clew.wiki.config import CatalogSpec

    return [CatalogSpec("lib", "../lib", pins["lib"], "requirements.yaml")]


def _no_index(_dep: Path, _pin: str, _sha: str | None):
    return ("absent", "not indexed on this machine", None)


def test_the_tree_is_composed_transitively_and_namespaced(tmp_path: Path) -> None:
    """@brief PRD-001 <- lib:REQ-LIB-001 <- hal:REQ-HAL-001; PRD-002 has no satisfier."""
    product, pins = _fixture(tmp_path)
    tree = compose(product, "product", _specs(product, pins), probe=_no_index)
    assert tree.roots == ("product:REQ-PRD-001", "product:REQ-PRD-002")
    assert tree.nodes["product:REQ-PRD-001"].satisfied_by == ("lib:REQ-LIB-001",)
    assert tree.nodes["lib:REQ-LIB-001"].satisfied_by == ("hal:REQ-HAL-001",)
    assert tree.nodes["product:REQ-PRD-002"].satisfied_by == ()
    assert tree.nodes["hal:REQ-HAL-001"].pin == pins["hal"]


def test_a_dependency_catalogue_is_read_at_its_pin(tmp_path: Path) -> None:
    """@brief hal gains REQ-HAL-002 after the pin: not in the tree."""
    product, pins = _fixture(tmp_path)
    _repo(
        tmp_path / "hal",
        "requirements:\n  REQ-HAL-001:\n    name: Timer fires\n    satisfies: lib:REQ-LIB-001\n"
        "  REQ-HAL-002:\n    name: Later\n    satisfies: lib:REQ-LIB-001\n",
    )
    tree = compose(product, "product", _specs(product, pins), probe=_no_index)
    assert "hal:REQ-HAL-002" not in tree.nodes


def test_unreached_and_dangling_are_reported(tmp_path: Path) -> None:
    """@brief LIB-002 reaches nothing on the product's tree; a link to PRD-999 dangles."""
    product, pins = _fixture(tmp_path)
    pins["lib"] = _repo(
        tmp_path / "lib",
        "requirements:\n"
        "  REQ-LIB-001:\n    name: Bounded retry\n    satisfies: [product:REQ-PRD-001]\n"
        "  REQ-LIB-002:\n    name: Unused\n"
        "  REQ-LIB-003:\n    name: Broken\n    satisfies: product:REQ-PRD-999\n",
    )
    tree = compose(product, "product", _specs(product, pins), probe=_no_index)
    assert "lib:REQ-LIB-002" in tree.unreached
    assert ("lib:REQ-LIB-003", "product:REQ-PRD-999") in tree.dangling


def test_one_repository_pinned_twice_is_a_conflict(tmp_path: Path) -> None:
    """@brief The product pins hal at a newer commit than lib does: reported, the first kept."""
    product, pins = _fixture(tmp_path)
    newer = _repo(tmp_path / "hal", "requirements:\n  REQ-HAL-001:\n    name: Timer v2\n")
    from clew.wiki.config import CatalogSpec

    specs = [*_specs(product, pins), CatalogSpec("hal2", "../hal", newer, "requirements.yaml")]
    tree = compose(product, "product", specs, probe=_no_index)
    assert any("hal" in c and newer[:12] in c for c in tree.conflicts), tree.conflicts


def test_a_repository_cycle_terminates(tmp_path: Path) -> None:
    """@brief hal names lib back: the walk stops at a repository it has already read at that pin."""
    product, pins = _fixture(tmp_path)
    hal = _repo(
        tmp_path / "hal",
        "requirements:\n  REQ-HAL-001:\n    name: Timer fires\n    satisfies: lib:REQ-LIB-001\n",
        _catalogs(("lib", "../lib", pins["lib"])),
    )
    pins["lib"] = _repo(
        tmp_path / "lib",
        "requirements:\n  REQ-LIB-001:\n    name: Bounded retry\n    satisfies: product:REQ-PRD-001\n",
        _catalogs(("hal", "../hal", hal)),
    )
    tree = compose(product, "product", _specs(product, pins), probe=_no_index)
    assert "hal:REQ-HAL-001" in tree.nodes


def test_evidence_is_withheld_unless_the_index_is_at_the_pin(tmp_path: Path) -> None:
    """THE PIN RULE, each refusal named: no index -> absent; checkout moved past the pin, or
    uncommitted changes, or a stale index -> unknown with the reason; all clear -> indexed.

    @brief probe_index states.
    """
    _, pins = _fixture(tmp_path)
    lib = tmp_path / "lib"
    db = tmp_path / "lib.db"
    db.write_text("")
    pin = pins["lib"]

    def probe(locate, stale):
        return probe_index(lib, pin, pin, locate=locate, is_stale=stale)

    assert probe(lambda _p: None, lambda *_: False)[0] == "absent"
    assert probe(lambda _p: db, lambda *_: False)[0] == "indexed"
    state, note, _ = probe(lambda _p: db, lambda *_: True)
    assert state == "unknown" and "older than" in note
    (lib / "requirements.yaml").write_text("requirements: {}\n")
    state, note, _ = probe(lambda _p: db, lambda *_: False)
    assert state == "unknown" and "uncommitted" in note
    _git(lib, "commit", "-qam", "moved")
    state, note, _ = probe(lambda _p: db, lambda *_: False)
    assert state == "unknown" and pin[:12] in note


def test_an_unknown_dependency_carries_no_evidence_and_links_its_checkout(tmp_path: Path) -> None:
    """@brief Unknown rows: implementers and tests None (absent, not empty), link = checkout."""
    product, pins = _fixture(tmp_path)

    def unknown(dep: Path, pin: str, sha: str | None):
        return ("unknown", f"not indexed at pin {pin[:12]}", Path("/nonexistent.db"))

    tree = compose(product, "product", _specs(product, pins), probe=unknown)
    node = tree.nodes["lib:REQ-LIB-001"]
    assert node.evidence == "unknown" and node.implementers is None and node.tests is None
    assert node.link == str((tmp_path / "lib").resolve())


def test_an_indexed_dependency_carries_its_trace(tmp_path: Path) -> None:
    """@brief Indexed: implementers and tests come from that dependency's index."""
    product, pins = _fixture(tmp_path)

    def indexed(dep: Path, pin: str, sha: str | None):
        return ("indexed", "", Path(f"/{dep.name}.db"))

    def trace(db: Path, req_id: str):
        return (("retry_send",), ("test_retry",)) if req_id == "REQ-LIB-001" else ((), ())

    tree = compose(product, "product", _specs(product, pins), probe=indexed, trace=trace)
    node = tree.nodes["lib:REQ-LIB-001"]
    assert node.evidence == "indexed"
    assert node.implementers == ("retry_send",) and node.tests == ("test_retry",)


# --- P6b-3b: the page and `check` ------------------------------------------------------------------


def _tree(tmp_path: Path, probe=_no_index):
    product, pins = _fixture(tmp_path)
    pins["lib"] = _repo(
        tmp_path / "lib",
        "requirements:\n"
        "  REQ-LIB-001:\n    name: Bounded retry\n    satisfies: [product:REQ-PRD-001]\n"
        "  REQ-LIB-002:\n    name: Unused\n"
        "  REQ-LIB-003:\n    name: Broken\n    satisfies: product:REQ-PRD-999\n",
        _catalogs(("hal", "../hal", pins["hal"])),
    )
    return compose(product, "product", _specs(product, pins), probe=probe), pins


def test_the_page_draws_the_tree_with_each_rows_evidence_state(tmp_path: Path) -> None:
    """UNKNOWN SAYS WHY AND WHERE: the note and the local checkout, and no evidence columns.

    @brief Product trace HTML.
    """
    from clew.wiki.productpage import product_html
    from clew.wiki.config import Audience

    def unknown(dep: Path, pin: str, sha: str | None):
        return ("unknown", f"not indexed at pin {pin[:12]}; checkout is at 0000", Path("/x.db"))

    tree, pins = _tree(tmp_path, probe=unknown)
    html = product_html(tree, Audience())
    assert "REQ-PRD-001" in html and "lib:REQ-LIB-001" in html and "hal:REQ-HAL-001" in html
    assert html.index("REQ-PRD-001") < html.index("lib:REQ-LIB-001") < html.index("hal:REQ-HAL-001")
    assert "not indexed at pin" in html and str((tmp_path / "lib").resolve()) in html
    assert "Bounded retry" in html
    assert "REQ-PRD-999" in html, "a dangling link is listed"
    assert '<details class="unreached"' in html and "lib:REQ-LIB-002" in html


def test_the_page_obeys_the_audience(tmp_path: Path) -> None:
    """@brief exclude_requirement_text: ids stay, titles go."""
    from clew.wiki.productpage import product_html
    from clew.wiki.config import Audience

    tree, _ = _tree(tmp_path)
    html = product_html(tree, Audience(exclude_requirement_text=True))
    assert "lib:REQ-LIB-001" in html and "Bounded retry" not in html


def test_check_reports_dangling_links_and_pin_conflicts(tmp_path: Path) -> None:
    """@brief `clew wiki check`'s composite problems: the dangling id and the double pin, by name."""
    from clew.wiki.composite import composite_problems
    from clew.wiki.config import CatalogSpec

    product, pins = _fixture(tmp_path)
    pins["lib"] = _repo(
        tmp_path / "lib",
        "requirements:\n  REQ-LIB-003:\n    name: Broken\n    satisfies: product:REQ-PRD-999\n",
        _catalogs(("hal", "../hal", pins["hal"])),
    )
    newer = _repo(tmp_path / "hal", "requirements:\n  REQ-HAL-001:\n    name: Timer v2\n")
    specs = [
        CatalogSpec("hal2", "../hal", newer, "requirements.yaml"),
        *_specs(product, pins),
    ]
    problems = composite_problems(product, specs, probe=_no_index)
    assert any("REQ-PRD-999" in p and "lib:REQ-LIB-003" in p for p in problems), problems
    assert any("pinned at" in p for p in problems), problems


def _root_db(path: Path, tagged: tuple[str, ...]) -> Path:
    """@brief A minimal index: the tables the composite reads for the root's own requirements."""
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE requirements (id TEXT, block TEXT, title TEXT, acceptance TEXT, priority TEXT)"
    )
    conn.execute("CREATE TABLE req_edges (req_id TEXT)")
    conn.executemany("INSERT INTO req_edges VALUES (?)", [(t,) for t in tagged])
    conn.commit()
    conn.close()
    return path


def test_a_tagged_requirement_without_a_catalogue_entry_is_a_root(tmp_path: Path) -> None:
    """THE ROOT IS THIS REPOSITORY'S REQUIREMENTS, the set its Requirements page shows: catalogue
    entries AND ids its code tags. A repository with no catalogue still has a tree.

    @brief REQ-PRD-003 is tagged only: a root.
    """
    product, pins = _fixture(tmp_path)
    db = _root_db(tmp_path / "root.db", ("REQ-PRD-003",))

    def trace(_db: Path, _rid: str):
        return ((), ())

    tree = compose(
        product, "product", _specs(product, pins), probe=_no_index, trace=trace, root_db=db
    )
    assert "product:REQ-PRD-003" in tree.roots


def test_a_dependency_requirement_implemented_here_is_served_not_unreached(tmp_path: Path) -> None:
    """A pinned catalogue's requirement this repository's own code tags is SERVED HERE — the W8
    direction (a library implementing its product's catalogue) — never reported as unreached.

    @brief lib:REQ-LIB-002 tagged in the root's index: implemented_here.
    """
    product, pins = _fixture(tmp_path)
    db = _root_db(tmp_path / "root.db", ("REQ-LIB-002",))

    def trace(_db: Path, _rid: str):
        return ((), ())

    tree = compose(
        product, "product", _specs(product, pins), probe=_no_index, trace=trace, root_db=db
    )
    assert "lib:REQ-LIB-002" in tree.implemented_here
    assert "lib:REQ-LIB-002" not in tree.unreached
