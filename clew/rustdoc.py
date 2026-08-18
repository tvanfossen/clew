# SPDX-License-Identifier: MIT
"""rustdoc JSON ingestion — the Rust analog of `doxygen.py`'s `run_doxygen`.

WHY THIS MODULE EXISTS. Doxygen has no Rust parser: a `.rs` file fed to it
with `EXTRACT_ALL=YES` produces zero `memberdef`/`path` rows, silently, the
same failure mode `DoxygenUnavailableError` exists to make loud for a missing
binary — except there is no missing-binary message to print, because the tool
being missing isn't the problem; the *language* is unsupported. So a Rust repo
gets structural data from a different front end entirely: `cargo +nightly
rustdoc -- -Z unstable-options --output-format json`, still nightly-gated as
of the toolchain this was written against (checked empirically, not assumed —
see `RustdocUnavailableError`).

THERE IS NO NORMALIZATION LAYER TO TARGET INSTEAD. `clew/declaration.py` and
`clew/datamodel.py` are both repo-declared-convention readers, not a
doxygen-schema abstraction — every downstream harvester (`ast_symbols.py`,
`call_edges.py`, `callback_edges.py`, `threads.py`, `locks.py`,
`critical_sections.py`, `dispatch_edges.py`, `requirements.py`,
`reachability.py`, `coverage.py`, ...) reads doxygen's OWN `memberdef`/`path`/
`refid`/`xrefs` tables directly by name. So the only way to make a Rust repo
legible to all of that unchanged is to populate the SAME tables, in the SAME
shape, from rustdoc's JSON — not to invent a parallel schema.

WHAT IS ACTUALLY POPULATED, and what is not. `tests/richdb.py`'s synthetic
fixture — built to describe exactly what a real `doxygen` run for a plain-C
target produces that clew itself cannot derive — hand-makes only `path`,
`refid`, `memberdef`, and inline `xrefs`. Every other doxygen table
(`compounddef`, `member`, `param`, `compoundref`, ...) either goes unused or
is read through an explicit `_table_exists` guard (`dispatch_edges.py`'s
class-scope resolution). This module therefore populates the same three
required tables — `path`, `refid`, `memberdef` — and nothing else. `xrefs` is
skipped: rustdoc's JSON is a documentation index (items, signatures, docs), not
a call graph, so it carries no in-body reference data to translate. Call
edges for Rust come entirely from the tree-sitter layer (`clew/rustast.py`,
a later increment) — the same split Python already has, where doxygen's
`xrefs` layer contributes nothing and `build_call_edges` runs on the
tree-sitter layer alone.

SCOPE (v1): free functions, inherent/trait-impl methods, and module-level
`static`/`const` items — the callable and stateful surface the thread/lock/
call-graph harvesters actually key off. Structs, enums, traits and modules are
not written as `compounddef` rows; `dispatch_edges.py`'s class-scope query
degrades to an empty result for a database with no `compounddef` table
(guarded by `_table_exists`), which is the correct behaviour for a codebase
this module does not model rather than a silent gap.

@brief Synthesize a doxygen-shaped SQLite database from rustdoc JSON.
@version 1
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._common import clean_subprocess_env, logger
from .errors import RustdocUnavailableError

## Doxygen's own schema (see clew/data/doxygen_schema.sql for provenance) — the
## exact DDL `tests/richdb.py` loads for the C/C++/Python fixture, so a Rust-sourced
## database has the identical table set every downstream stage already expects.
DOXYGEN_SCHEMA_PATH = Path(__file__).resolve().parent / "data" / "doxygen_schema.sql"

## doxygen's `path.type` discriminator — only files are ever written here (Rust
## has no separate "directory" concept this module needs to record).
_TYPE_FILE = 1

## rustdoc `inner` keys this module turns into a `memberdef` row, and the doxygen
## `kind` each maps to. Everything else (`struct`, `enum`, `trait`, `module`,
## `impl`, `assoc_type`, ...) is read and skipped — see the module docstring.
_ITEM_KIND_MAP = {
    "function": "function",
    "static": "variable",
    "constant": "variable",
}


## @brief One cargo build target this module will run rustdoc against.
## @version 1
@dataclass(frozen=True)
class _CargoTarget:
    """@brief A package's lib (preferred) or bin target, as `cargo metadata` reports it."""

    package: str
    name: str
    kind: str  # "lib" or "bin"


## @brief True when `repo_root` is a cargo package or workspace.
## @param repo_root Candidate repository root.
## @return Whether `repo_root/Cargo.toml` exists.
## @version 1
## @utility
def has_cargo_manifest(repo_root: Path) -> bool:
    """@brief Cheap, no-subprocess check for "is this a Rust repo"."""
    return (Path(repo_root) / "Cargo.toml").is_file()


## @brief Refuse before spawning cargo, naming exactly what is missing.
## @version 1
## @dg_internal
def _require_nightly_rustdoc() -> None:
    """rustdoc's JSON output has required `-Z unstable-options` (nightly-only)
    since the format was introduced, and still does as of the toolchain this was
    verified against — checked empirically (`cargo +nightly rustdoc --lib --
    -Z unstable-options --output-format json` against a scratch crate), not
    assumed from documentation that might be stale by the time this runs.

    Probed with `cargo +nightly --version`, which reports cargo's own toolchain
    version and fails cleanly ("toolchain 'nightly' is not installed") when it
    is absent — `cargo +nightly rustc --version` was tried first and rejected:
    cargo's `rustc` subcommand treats a bare `--version` as one of ITS OWN
    positional args rather than forwarding it, so it fails with a usage error
    on a perfectly good nightly toolchain and never reaches rustc at all.

    @brief Verify cargo and a nightly toolchain are both usable.
    @raises RustdocUnavailableError when cargo or a nightly toolchain is unusable.
    @version 1
    """
    if shutil.which("cargo") is None:
        raise RustdocUnavailableError(
            "the 'cargo' binary is not on PATH — install Rust (https://rustup.rs) "
            "to index a Rust repository."
        )
    proc = subprocess.run(
        ["cargo", "+nightly", "--version"],
        capture_output=True,
        text=True,
        env=clean_subprocess_env(),
    )
    if proc.returncode != 0:
        raise RustdocUnavailableError(
            "rustdoc's JSON output (needed to index a Rust repository — doxygen has no "
            "Rust parser) is nightly-only, and no nightly toolchain is installed.\n"
            "  rustup toolchain install nightly\n"
            "Then re-run this build.\n"
            f"(cargo +nightly --version said: {proc.stderr.strip()})"
        )


## @brief The lib-or-bin targets `cargo metadata` reports for this repo.
## @param repo_root Repository root (a package or a workspace).
## @return One target per package: its lib target if it has one, else every bin target.
## @version 1
## @dg_internal
def _discover_targets(repo_root: Path) -> list[_CargoTarget]:
    """Only `--no-deps` packages — the workspace's OWN crates, never a
    dependency — matching doxygen's own INPUT scoping, which never reaches into
    a vendored/`cargo`-fetched tree either.

    A package's LIB TARGET IS PREFERRED over its bins: a lib is a package's
    public surface and a `main.rs` binary is usually a thin wrapper around it
    (`windchill-connector` is exactly this shape — one lib, two bins). A
    package with no lib (a pure CLI crate) gets every bin target instead, so
    a repo like `todo-sqlite-cli` still gets indexed.

    @brief Resolve which cargo targets to run rustdoc against.
    @return One `_CargoTarget` per package.
    @raises RustdocUnavailableError when `cargo metadata` itself fails.
    @version 1
    """
    proc = subprocess.run(
        ["cargo", "metadata", "--no-deps", "--format-version", "1"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=clean_subprocess_env(),
    )
    if proc.returncode != 0:
        raise RustdocUnavailableError(
            f"'cargo metadata' failed under {repo_root}:\n{proc.stderr.strip()}"
        )
    data = json.loads(proc.stdout)
    targets: list[_CargoTarget] = []
    for pkg in data.get("packages", []):
        pkg_targets = pkg.get("targets", [])
        lib = next((t for t in pkg_targets if "lib" in t.get("kind", ())), None)
        if lib is not None:
            targets.append(_CargoTarget(pkg["name"], lib["name"], "lib"))
            continue
        for bin_target in (t for t in pkg_targets if "bin" in t.get("kind", ())):
            targets.append(_CargoTarget(pkg["name"], bin_target["name"], "bin"))
    return targets


## @brief Run rustdoc for one target and return its JSON output path.
## @param repo_root Repository root — also the subprocess cwd, so rustdoc's
##        recorded spans come back repo-relative (verified empirically: a
##        workspace member's spans are relative to the invocation cwd, not the
##        member's own manifest directory).
## @param target The package/target to document.
## @param scratch_dir A `--target-dir` outside the repo, so a build never writes
##        into the tree it is indexing (mirrors `_doxygen_out_dir`'s rule for doxygen).
## @return Path to the generated `<target>.json`.
## @version 1
## @dg_internal
def _run_rustdoc_json(repo_root: Path, target: _CargoTarget, scratch_dir: Path) -> Path:
    """Invoke `cargo +nightly rustdoc --output-format json` for one target.

    @brief Invoke `cargo +nightly rustdoc --output-format json` for one target.
    @raises RustdocUnavailableError when the invocation fails or the expected
        file is absent.
    @version 1
    """
    kind_flag = "--lib" if target.kind == "lib" else f"--bin={target.name}"
    cmd = [
        "cargo",
        "+nightly",
        "rustdoc",
        "-p",
        target.package,
        kind_flag,
        "--target-dir",
        str(scratch_dir),
        "--",
        "-Z",
        "unstable-options",
        "--output-format",
        "json",
        "--document-private-items",
    ]
    logger.info("Running rustdoc: %s (cwd: %s)", " ".join(cmd), repo_root)
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=clean_subprocess_env(),
    )
    if proc.returncode != 0:
        raise RustdocUnavailableError(
            f"'cargo +nightly rustdoc' failed for package {target.package!r} "
            f"({target.kind} {target.name!r}):\n{proc.stderr.strip()}"
        )
    json_name = target.name.replace("-", "_")
    json_path = scratch_dir / "doc" / f"{json_name}.json"
    if not json_path.exists():
        raise RustdocUnavailableError(f"expected rustdoc JSON output not found: {json_path}")
    return json_path


## @brief Render a rustdoc type descriptor as a best-effort argument type string.
## @param ty A rustdoc JSON `Type` value, or None for a unit/void type.
## @return An approximate Rust-syntax rendering. Never raises on an unrecognized shape.
## @version 1
## @dg_internal
def _render_type(ty: dict[str, Any] | None) -> str:
    """Best-effort only: doxygen's `argsstring`/`type` columns exist for a reader
    to skim, not for anything downstream to parse structurally (call edges come
    from the tree-sitter layer, not this text). An unrecognized rustdoc `Type`
    shape (a raw pointer, an `impl Trait`, a higher-ranked trait bound, ...)
    renders as `?` rather than raising, so one exotic signature never fails an
    entire crate's ingestion.

    @brief Approximate a rustdoc type as Rust syntax.
    @version 1
    """
    if ty is None:
        return "()"
    if "primitive" in ty:
        return str(ty["primitive"])
    if "generic" in ty:
        return str(ty["generic"])
    if "resolved_path" in ty:
        return str(ty["resolved_path"].get("path", "?"))
    if "borrowed_ref" in ty:
        ref = ty["borrowed_ref"]
        mut = "mut " if ref.get("is_mutable") else ""
        return f"&{mut}{_render_type(ref.get('type'))}"
    if "tuple" in ty:
        return "(" + ", ".join(_render_type(t) for t in ty["tuple"]) + ")"
    if "slice" in ty:
        return f"[{_render_type(ty['slice'])}]"
    if "array" in ty:
        return f"[{_render_type(ty['array'].get('type'))}; {ty['array'].get('len', '?')}]"
    if "qualified_path" in ty:
        return str(ty["qualified_path"].get("name", "?"))
    return "?"


## @brief Render a function/method's parameter list as doxygen's `argsstring` would.
## @param sig A rustdoc JSON function `sig` object.
## @return A parenthesized, comma-separated parameter list.
## @version 1
## @dg_internal
def _render_argsstring(sig: dict[str, Any]) -> str:
    """@brief Best-effort `(type name, type name)` rendering of a function signature."""
    parts = [f"{_render_type(param_ty)} {name}" for name, param_ty in sig.get("inputs", [])]
    return "(" + ", ".join(parts) + ")"


## @brief The first line of a rustdoc `docs` string, doxygen's brief-description role.
## @param docs Raw markdown docs text, or None.
## @return The first non-blank line, or "" when there are no docs.
## @version 1
## @dg_internal
def _brief(docs: str | None) -> str:
    """Plain text, not `<para>`-wrapped: `query/_common.py`'s tag-stripping regex
    (`re.sub(r"<[^>]+>", " ", ...)`) already treats untagged text as a no-op, so
    there is nothing this module gains by imitating doxygen's XML wrapping — see
    the module docstring.

    @brief First line of a rustdoc docstring.
    @version 1
    """
    if not docs:
        return ""
    for line in docs.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


## @brief One row this module will insert into `path` and `memberdef`.
## @version 1
@dataclass(frozen=True)
class _Symbol:
    """@brief A rustdoc item resolved to doxygen's memberdef shape."""

    name: str
    kind: str  # doxygen kind: 'function' or 'variable'
    file: str  # repo-relative POSIX path
    line: int
    column: int
    end_line: int
    static: int  # 0/1 — mapped from Rust visibility, see _symbols_from_json
    argsstring: str
    definition: str
    brief: str
    detailed: str
    initializer: str


## @brief Extract this module's v1 symbol set from one rustdoc JSON document.
## @param doc Parsed rustdoc JSON (one `cargo +nightly rustdoc` invocation's output).
## @return Every function/static/constant item with a real source span.
## @version 1
## @dg_internal
def _symbols_from_json(doc: dict[str, Any]) -> list[_Symbol]:
    """An item with `span: null` is either external (a blanket `impl<T> From<T>
    for T`, a trait default method inherited from `core`/`std`) or otherwise not
    rooted in this repo's own source — verified empirically: every item observed
    with a null span belonged to a dependency or the language's own prelude, and
    every item genuinely defined in the crate under documentation carried a real
    span. Filtering on that alone (rather than `crate_id`, which rustdoc does not
    document as stable) is what keeps this module from writing a `memberdef` row
    for `core::convert::From::from`.

    `static` (the column) is approximated from Rust's own visibility rather than
    a storage-class keyword Rust doesn't have: a private/`pub(crate)` item is the
    closest analog to C's internal linkage, so it is recorded `static=1` there and
    `static=0` for anything `pub`. Nothing downstream branches on this column in a
    load-bearing way today (grep confirms only `ast_symbols.py` writes it), so the
    mapping is a reasonable best effort rather than a verified equivalence.

    @brief Resolve one rustdoc document's function/static/constant items.
    @return The extracted symbol rows.
    @version 1
    """
    paths = doc.get("paths", {})
    symbols: list[_Symbol] = []
    for item_id, item in doc.get("index", {}).items():
        span = item.get("span")
        inner = item.get("inner") or {}
        name = item.get("name")
        if span is None or name is None:
            continue
        item_kind = next(iter(inner), None)
        doxygen_kind = _ITEM_KIND_MAP.get(item_kind)
        if doxygen_kind is None:
            continue
        visibility = item.get("visibility")
        is_public = visibility == "public" or (
            isinstance(visibility, dict) and "public" in visibility
        )
        docs = item.get("docs")
        qualified = "::".join(paths.get(item_id, {}).get("path", [])) or name
        if item_kind == "function":
            sig = inner["function"]["sig"]
            argsstring = _render_argsstring(sig)
            output = _render_type(sig.get("output"))
            definition = f"{output} {qualified}"
            initializer = ""
        else:
            argsstring = ""
            type_info = inner.get(item_kind, {})
            type_text = _render_type(type_info.get("type"))
            definition = f"{type_text} {qualified}"
            initializer = str(type_info.get("expr") or "")
        symbols.append(
            _Symbol(
                name=name,
                kind=doxygen_kind,
                file=span["filename"].replace("\\", "/"),
                line=span["begin"][0],
                column=span["begin"][1],
                end_line=span["end"][0],
                static=0 if is_public else 1,
                argsstring=argsstring,
                definition=definition,
                brief=_brief(docs),
                detailed=docs or "",
                initializer=initializer,
            )
        )
    return symbols


## @brief Create the doxygen-shaped tables in a fresh database.
## @param db_path Database file to create (overwritten if it already exists).
## @return An open connection to the new database.
## @version 1
## @dg_internal
def _create_schema(db_path: Path) -> sqlite3.Connection:
    """@brief Load doxygen's own schema (clew/data/doxygen_schema.sql) into a fresh db."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(DOXYGEN_SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


## @brief Write one repository's symbols into a fresh doxygen-shaped database.
## @param conn Open connection to a database already carrying doxygen's schema.
## @param symbols Every symbol collected across every target's rustdoc JSON.
## @version 1
## @dg_internal
def _write_symbols(conn: sqlite3.Connection, symbols: list[_Symbol]) -> None:
    """De-duplicates on `(file, line, name)`: a package's lib and bin targets can
    both re-document a shared module (a `bin` that is a thin `fn main` calling
    into the lib re-exports the lib's own public items in its own crate root),
    which would otherwise double the symbol's row and everything counted from it.

    @brief Insert `path`, `refid` and `memberdef` rows for every distinct symbol.
    @version 1
    """
    path_rowids: dict[str, int] = {}
    next_path_id = 1
    next_member_id = 1
    seen: set[tuple[str, int, str]] = set()
    for symbol in symbols:
        key = (symbol.file, symbol.line, symbol.name)
        if key in seen:
            continue
        seen.add(key)
        if symbol.file not in path_rowids:
            path_rowids[symbol.file] = next_path_id
            conn.execute(
                "INSERT INTO path (rowid, type, local, found, name) VALUES (?, ?, 1, 1, ?)",
                (next_path_id, _TYPE_FILE, symbol.file),
            )
            next_path_id += 1
        file_id = path_rowids[symbol.file]
        rowid = next_member_id
        next_member_id += 1
        conn.execute(
            "INSERT INTO refid (rowid, refid) VALUES (?, ?)",
            (rowid, f"rustdoc_{rowid}"),
        )
        conn.execute(
            "INSERT INTO memberdef (rowid, name, definition, argsstring, kind, static, "
            "bodystart, bodyend, bodyfile_id, file_id, line, column, "
            "briefdescription, detaileddescription, initializer) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rowid,
                symbol.name,
                symbol.definition,
                symbol.argsstring,
                symbol.kind,
                symbol.static,
                symbol.line,
                symbol.end_line,
                file_id,
                file_id,
                symbol.line,
                symbol.column,
                symbol.brief,
                symbol.detailed,
                symbol.initializer,
            ),
        )
    conn.commit()


## @brief Synthesize a doxygen-shaped SQLite database for a Rust repository.
## @param repo_root Repository root (a cargo package or workspace).
## @param db_path Where to write the resulting database.
## @return `db_path`, for symmetry with `doxygen.run_doxygen`'s return contract.
## @version 1
## @utility
def run_rustdoc(repo_root: Path, db_path: Path) -> Path:
    """The Rust analog of `doxygen.run_doxygen`: same contract (a Path to a
    finished database in place of a Doxyfile-driven `doxygen` invocation), so a
    caller downstream of either — `copy_database`, then every `_build_stages`
    harvester — cannot tell which front end produced its input.

    Every target's rustdoc JSON is generated into ONE scratch `--target-dir`
    outside the repo (never inside it, matching `_doxygen_out_dir`'s rule), torn
    down when this function returns.

    @brief Build a Rust repo's structural index via rustdoc JSON.
    @return Path to the generated database (`db_path`).
    @raises RustdocUnavailableError when cargo/nightly rustdoc is unusable, or no
        lib/bin target is found.
    @version 1
    """
    repo_root = Path(repo_root).resolve()
    _require_nightly_rustdoc()
    targets = _discover_targets(repo_root)
    if not targets:
        raise RustdocUnavailableError(
            f"no cargo lib or bin target found under {repo_root} — nothing to document."
        )
    symbols: list[_Symbol] = []
    with tempfile.TemporaryDirectory(prefix="clew-rustdoc-") as scratch:
        scratch_dir = Path(scratch)
        for target in targets:
            json_path = _run_rustdoc_json(repo_root, target, scratch_dir)
            doc = json.loads(json_path.read_text(encoding="utf-8"))
            symbols.extend(_symbols_from_json(doc))
    conn = _create_schema(Path(db_path))
    try:
        _write_symbols(conn, symbols)
    finally:
        conn.close()
    logger.info(
        "rustdoc: indexed %d symbol(s) across %d target(s) into %s",
        len(symbols),
        len(targets),
        db_path,
    )
    return Path(db_path)
