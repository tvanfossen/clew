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

WHAT IS ACTUALLY POPULATED. `tests/richdb.py`'s synthetic fixture — built to
describe exactly what a real `doxygen` run for a plain-C target produces that
clew itself cannot derive — hand-makes only `path`, `refid`, `memberdef`, and
inline `xrefs`; every other doxygen table either goes unused or is read
through an explicit `_table_exists` guard. This module populates those same
three required tables, PLUS `compounddef`/`member`/`reimplements` (v2) for
structs, enums, traits and their impl blocks — the data `dispatch_edges.py`'s
`_matching_compounds`/`_class_functions`/`_override_targets` need to resolve a
DECLARED interface binding (`.clew.yaml`'s `dispatch:` section naming a
`trait Foo` / `impl Foo for Bar` pairing), exactly as they already do for a
declared C++ interface/implementor pair. This is still a purely mechanical
translation of what rustdoc's JSON states, not automatic virtual-dispatch
discovery — a Rust repo gets the SAME "nothing resolves until an owner
declares it" behaviour C++ already has, not a new capability.

`xrefs` is skipped: rustdoc's JSON is a documentation index (items,
signatures, docs), not a call graph, so it carries no in-body reference data
to translate. Call/thread/lock edges for Rust come entirely from the
tree-sitter layer (`clew/harvest.py`'s `_TS_GRAMMARS`, and the Rust branches in
`call_edges.py`/`threads.py`/`locks.py`) — the same split Python already has,
where doxygen's `xrefs` layer contributes nothing and `build_call_edges` runs
on the tree-sitter layer alone.

SCOPE: free functions, inherent/trait-impl methods, module-level
`static`/`const` items, and struct/enum/trait declarations with their impl
relationships. NOT modeled: generic impls' type parameters, trait default
method bodies inherited (rather than overridden) by an implementor, and
`compoundref` (base/derived inheritance) — Rust has no class inheritance, so
that table stays empty by construction, not by gap.

TARGET SELECTION. A package's lib and every bin target are BOTH documented
(v3) — a `main.rs` binary is not reliably a thin wrapper around a sibling lib
of the same name; `knots` and `tools_sqc` both pair a `[lib]` with a
same-named `[[bin]]` where the bin owns real modules (CLI parsing, config
loading, output formatting) that a lib-only pass silently dropped from the
index with no error. See `_discover_targets`.

@brief Synthesize a doxygen-shaped SQLite database from rustdoc JSON.
@version 3
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


## @brief Whether `repo_root`'s build routes through rustdoc instead of doxygen.
## @param repo_root Candidate repository root.
## @return True when `repo_root` has a Cargo.toml and no discoverable Doxyfile.
## @version 1
## @utility
def uses_rustdoc(repo_root: Path) -> bool:
    """Doxygen has no Rust parser, so a cargo repo's structural index comes from
    this module instead — UNLESS the repo already ships its own Doxyfile, which
    means an owner deliberately configured a doxygen build (a C/C++ project
    that happens to vendor a small Rust tool, say) and that configuration
    should win rather than being silently overridden by Cargo.toml's mere
    presence. Shared by `cli.py`'s build-routing decision and `init_command.py`'s
    doxygen doctor check — both need the same answer to "will this repo ever
    invoke doxygen at all", so it lives once, here, rather than being
    reimplemented per caller.

    @brief Decide whether this repo's build uses rustdoc instead of doxygen.
    @return True when `repo_root` has a Cargo.toml and no discoverable Doxyfile.
    @version 1
    """
    from .doxygen import discover_doxyfile

    return has_cargo_manifest(repo_root) and discover_doxyfile(repo_root) is None


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


## @brief The lib and bin targets `cargo metadata` reports for this repo.
## @param repo_root Repository root (a package or a workspace).
## @return One target per package lib (if any) plus one per bin target.
## @version 2
## @dg_internal
def _discover_targets(repo_root: Path) -> list[_CargoTarget]:
    """Only `--no-deps` packages — the workspace's OWN crates, never a
    dependency — matching doxygen's own INPUT scoping, which never reaches into
    a vendored/`cargo`-fetched tree either.

    A package's lib AND every bin target are BOTH documented — a `main.rs`
    binary is not reliably a thin wrapper around its sibling lib (`knots` and
    `tools_sqc` both pair a `[lib]` with a same-named `[[bin]]` where the bin
    owns real, non-reexported modules — CLI arg parsing, config loading,
    output formatting — that a lib-only pass silently drops from the index
    with no error, since `cargo metadata` succeeds either way). rustdoc JSON
    numbers items per-invocation, so the caller prefixes ids per target to
    avoid collisions; a bin's rows never collide with its sibling lib's rows
    in the shared `path`/`refid`/`memberdef` tables.

    @brief Resolve which cargo targets to run rustdoc against.
    @return One `_CargoTarget` per package target (lib and/or bins).
    @raises RustdocUnavailableError when `cargo metadata` itself fails.
    @version 2
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
## @version 2
@dataclass(frozen=True)
class _Symbol:
    """@brief A rustdoc item resolved to doxygen's memberdef shape."""

    item_id: str  # globally unique across every target's JSON — see run_rustdoc
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


## Doxygen kind for a Rust compound item. `trait` maps to 'interface' — the
## closest existing doxygen kind, and the one dispatch_edges.py's
## `_matching_compounds` already expects for an "interface" binding.
_COMPOUND_KIND_MAP = {
    "struct": "struct",
    "enum": "enum",
    "trait": "interface",
}


## @brief One row this module will insert into `compounddef`.
## @version 1
@dataclass(frozen=True)
class _Compound:
    """@brief A Rust struct/enum/trait resolved to doxygen's compounddef shape."""

    item_id: str
    name: str
    kind: str  # doxygen kind: 'struct', 'enum' or 'interface'
    file: str
    line: int
    column: int
    brief: str
    detailed: str


## @brief One `impl Type` or `impl Trait for Type` block.
## @version 1
@dataclass(frozen=True)
class _Impl:
    """Resolved just enough to write `member` (every impl's own methods belong
    to the type it's on) and `reimplements` (a trait impl's methods override
    the trait's own declarations) rows — see `_write_compounds`.

    @brief One impl block's target type, trait (if any), and member item ids.
    """

    for_item_id: str | None  # None when the target type isn't in this crate
    trait_item_id: str | None  # None for an inherent impl, or an external trait
    member_item_ids: tuple[str, ...]


## @brief Extract this module's v1 symbol set from one rustdoc JSON document.
## @param doc Parsed rustdoc JSON (one `cargo +nightly rustdoc` invocation's output).
## @param doc_prefix Prefix making this document's item ids globally unique once
##        merged with other targets' documents (each target's JSON has its own,
##        independent item-id numbering).
## @return Every function/static/constant item with a real source span.
## @version 2
## @dg_internal
def _symbols_from_json(doc: dict[str, Any], doc_prefix: str) -> list[_Symbol]:
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

    A trait's OWN method declarations (`trait Greet { fn hello(&self); }`) are
    ordinary `inner.function` items too — rustdoc gives each one its own id and
    span — so they are picked up here exactly like a free function, and
    `_write_compounds` links them to their trait's `compounddef` via `member`.

    @brief Resolve one rustdoc document's function/static/constant items.
    @return The extracted symbol rows.
    @version 2
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
                item_id=f"{doc_prefix}:{item_id}",
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


## @brief Extract this document's struct/enum/trait compounds.
## @param doc Parsed rustdoc JSON.
## @param doc_prefix Prefix making this document's item ids globally unique.
## @return Every struct/enum/trait item with a real source span.
## @version 1
## @dg_internal
def _compounds_from_json(doc: dict[str, Any], doc_prefix: str) -> list[_Compound]:
    """@brief Resolve one rustdoc document's struct/enum/trait items to compounds."""
    compounds: list[_Compound] = []
    for item_id, item in doc.get("index", {}).items():
        span = item.get("span")
        inner = item.get("inner") or {}
        name = item.get("name")
        if span is None or name is None:
            continue
        item_kind = next(iter(inner), None)
        doxygen_kind = _COMPOUND_KIND_MAP.get(item_kind)
        if doxygen_kind is None:
            continue
        docs = item.get("docs")
        compounds.append(
            _Compound(
                item_id=f"{doc_prefix}:{item_id}",
                name=name,
                kind=doxygen_kind,
                file=span["filename"].replace("\\", "/"),
                line=span["begin"][0],
                column=span["begin"][1],
                brief=_brief(docs),
                detailed=docs or "",
            )
        )
    return compounds


## @brief Extract this document's real (non-synthetic, non-blanket) impl blocks.
## @param doc Parsed rustdoc JSON.
## @param doc_prefix Prefix making this document's item ids globally unique.
## @return Every impl block whose target type is defined in this crate.
## @version 1
## @dg_internal
def _impls_from_json(doc: dict[str, Any], doc_prefix: str) -> list[_Impl]:
    """`is_synthetic`/`blanket_impl` filter out the auto-generated impls rustdoc
    reports for every type regardless of what the crate wrote (`impl Send for
    Counter`, `impl<T> From<T> for T`, ...) — real user code never sets either.
    `span: null` catches the same set a second way (belt-and-braces: both were
    observed set together on every synthetic/blanket impl checked), and is kept
    as the primary filter for consistency with `_symbols_from_json`.

    The target type is resolved to OUR item id only when it is a
    `resolved_path` pointing at a `struct`/`enum` item THIS crate defines —
    `for` can equally be a primitive, a tuple, or an external type impl'd via a
    trait *this* crate declares, none of which `_compounds_from_json` captured,
    and `_write_compounds` silently drops a `member`/`reimplements` row whose
    target never resolves rather than guessing one.

    @brief Resolve one rustdoc document's real impl blocks.
    @return The extracted impl records.
    @version 1
    """
    impls: list[_Impl] = []
    for item in doc.get("index", {}).values():
        inner = item.get("inner") or {}
        impl = inner.get("impl")
        if impl is None or item.get("span") is None:
            continue
        if impl.get("is_synthetic") or impl.get("blanket_impl") is not None:
            continue
        for_path = (impl.get("for") or {}).get("resolved_path")
        trait_path = impl.get("trait")
        member_ids = tuple(f"{doc_prefix}:{i}" for i in impl.get("items") or ())
        if not member_ids:
            continue
        impls.append(
            _Impl(
                for_item_id=f"{doc_prefix}:{for_path['id']}" if for_path else None,
                trait_item_id=f"{doc_prefix}:{trait_path['id']}" if trait_path else None,
                member_item_ids=member_ids,
            )
        )
    return impls


## @brief A trait's own declared methods, as membership of the trait's own compound.
## @param doc Parsed rustdoc JSON.
## @param doc_prefix Prefix making this document's item ids globally unique.
## @return One `_Impl`-shaped record per trait, so `_write_compounds` needs no
##         separate trait-membership code path.
## @version 1
## @dg_internal
def _trait_self_membership(doc: dict[str, Any], doc_prefix: str) -> list[_Impl]:
    """`trait Greet { fn hello(&self); }` needs `hello` linked to `Greet`'s own
    `compounddef` — the same `member` relationship an impl block's methods get
    to their target type — but a trait declaration is not itself shaped like an
    `impl`, so it gets its own tiny extraction rather than a special case
    inside `_impls_from_json`.

    @brief Resolve each trait's own methods as membership of itself.
    @return One synthetic `_Impl` per trait with a real span.
    @version 1
    """
    records: list[_Impl] = []
    for item_id, item in doc.get("index", {}).items():
        inner = item.get("inner") or {}
        trait = inner.get("trait")
        if trait is None or item.get("span") is None:
            continue
        member_ids = tuple(f"{doc_prefix}:{i}" for i in trait.get("items") or ())
        if member_ids:
            records.append(
                _Impl(
                    for_item_id=f"{doc_prefix}:{item_id}",
                    trait_item_id=None,
                    member_item_ids=member_ids,
                )
            )
    return records


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


## @brief Rowid bookkeeping shared by symbol and compound insertion.
## @version 1
@dataclass
class _WriteState:
    """One `refid`/`path` rowid space shared by `_write_symbols` and
    `_write_compounds` — doxygen's schema ties BOTH `memberdef.rowid` and
    `compounddef.rowid` to the same `refid` table via foreign key, so they
    must never collide, and a file referenced by both a symbol and a compound
    must resolve to one `path` row, not two.

    @brief Shared path/refid rowid allocator and rustdoc-item-id resolver.
    """

    path_rowids: dict[str, int]
    next_path_id: int
    next_refid: int
    ## rustdoc item id (globally unique per run_rustdoc call — see its
    ## doc_prefix) -> the refid/rowid this module assigned it, for EITHER a
    ## memberdef or a compounddef row. One namespace is safe because a single
    ## rustdoc document's own ids never collide between item kinds.
    item_to_rowid: dict[str, int]
    item_to_name: dict[str, str]
    ## compounddef item id -> its doxygen kind, so `_write_compounds` can tell
    ## "this impl's target is a trait" (kind == 'interface') from "...a struct"
    ## without a second lookup table.
    compound_kind: dict[str, str]


## @brief A file's `path` rowid, inserting the row on first use.
## @param conn Open connection.
## @param state Shared rowid allocator.
## @param file Repo-relative POSIX path.
## @return The file's `path.rowid`.
## @version 1
## @dg_internal
def _path_id(conn: sqlite3.Connection, state: _WriteState, file: str) -> int:
    """@brief Resolve (or create) one file's `path` row."""
    if file not in state.path_rowids:
        state.path_rowids[file] = state.next_path_id
        conn.execute(
            "INSERT INTO path (rowid, type, local, found, name) VALUES (?, ?, 1, 1, ?)",
            (state.next_path_id, _TYPE_FILE, file),
        )
        state.next_path_id += 1
    return state.path_rowids[file]


## @brief Write one repository's symbols into a fresh doxygen-shaped database.
## @param conn Open connection to a database already carrying doxygen's schema.
## @param symbols Every symbol collected across every target's rustdoc JSON.
## @return Shared rowid state, continued by `_write_compounds`.
## @version 2
## @dg_internal
def _write_symbols(conn: sqlite3.Connection, symbols: list[_Symbol]) -> _WriteState:
    """De-duplicates on `(file, line, name)`: a package's lib and bin targets can
    both re-document a shared module (a `bin` that is a thin `fn main` calling
    into the lib re-exports the lib's own public items in its own crate root),
    which would otherwise double the symbol's row and everything counted from it.
    A duplicate's item id still resolves to the FIRST occurrence's rowid, so an
    impl block discovered on either target's JSON links to the same row.

    @brief Insert `path`, `refid` and `memberdef` rows for every distinct symbol.
    @return Shared rowid state (path rowids, next ids, item-id resolution).
    @version 2
    """
    state = _WriteState(
        path_rowids={},
        next_path_id=1,
        next_refid=1,
        item_to_rowid={},
        item_to_name={},
        compound_kind={},
    )
    seen: dict[tuple[str, int, str], int] = {}
    for symbol in symbols:
        key = (symbol.file, symbol.line, symbol.name)
        state.item_to_name[symbol.item_id] = symbol.name
        if key in seen:
            state.item_to_rowid[symbol.item_id] = seen[key]
            continue
        file_id = _path_id(conn, state, symbol.file)
        rowid = state.next_refid
        state.next_refid += 1
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
        seen[key] = rowid
        state.item_to_rowid[symbol.item_id] = rowid
    conn.commit()
    return state


## @brief Insert one `compounddef` row per struct/enum/trait, if not already seen.
## @param conn Open connection.
## @param state Shared rowid state from `_write_symbols` (mutated in place).
## @param compounds Every struct/enum/trait collected across every target's JSON.
## @return None.
## @version 1
## @dg_internal
def _write_compound_rows(
    conn: sqlite3.Connection, state: _WriteState, compounds: list[_Compound]
) -> None:
    """@brief Insert `path`/`refid`/`compounddef` rows for every distinct compound."""
    for compound in compounds:
        if compound.item_id in state.item_to_rowid:
            continue  # a name collision across targets; keep the first seen
        file_id = _path_id(conn, state, compound.file)
        rowid = state.next_refid
        state.next_refid += 1
        conn.execute("INSERT INTO refid (rowid, refid) VALUES (?, ?)", (rowid, f"rustdoc_{rowid}"))
        conn.execute(
            "INSERT INTO compounddef (rowid, name, kind, file_id, line, column, "
            "briefdescription, detaileddescription) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rowid,
                compound.name,
                compound.kind,
                file_id,
                compound.line,
                compound.column,
                compound.brief,
                compound.detailed,
            ),
        )
        state.item_to_rowid[compound.item_id] = rowid
        state.compound_kind[compound.item_id] = compound.kind


## @brief Link every impl's methods to its target compound, qualifying their `definition`.
## @param conn Open connection.
## @param state Shared rowid state (mutated in place: nothing, read only here).
## @param compounds Every struct/enum/trait — for resolving a compound's own name.
## @param impls Every impl block (plus each trait's own self-membership).
## @return A trait's item id -> {method name: memberdef rowid}, for `_write_reimplements`.
## @version 1
## @dg_internal
def _write_member_rows(
    conn: sqlite3.Connection,
    state: _WriteState,
    compounds: list[_Compound],
    impls: list[_Impl],
) -> dict[str, dict[str, int]]:
    """rustdoc's own `paths` mapping never covers a trait/impl method (only
    top-level importable items), so `_symbols_from_json` wrote a BARE
    `definition` ("String hello") with no owning-type qualifier at all.
    `dispatch_edges._class_functions`/`_qualified_at_boundary` need
    "Owner::member" to appear in `definition` — the same contract a real
    doxygen C++ build satisfies — so it is patched in here, the first point
    this module actually KNOWS the owning type.

    Also returns each TRAIT's own method-name -> rowid map (`compound_kind ==
    'interface'`), which `_write_reimplements` needs to pair a concrete impl's
    methods against by name.

    @brief Insert `member` rows and qualify each member's `definition`.
    @return Trait item id -> {method name: rowid}.
    @version 1
    """
    compound_name = {c.item_id: c.name for c in compounds}
    trait_methods_by_name: dict[str, dict[str, int]] = {}
    for impl in impls:
        scope_rowid = state.item_to_rowid.get(impl.for_item_id or "")
        if scope_rowid is None:
            continue
        if state.compound_kind.get(impl.for_item_id or "") == "interface":
            trait_methods_by_name[impl.for_item_id] = {}
        owner = compound_name.get(impl.for_item_id or "", "")
        for member_id in impl.member_item_ids:
            member_rowid = state.item_to_rowid.get(member_id)
            member_name = state.item_to_name.get(member_id)
            if member_rowid is None or member_name is None:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO member (scope_rowid, memberdef_rowid, prot, virt) "
                "VALUES (?, ?, 0, 0)",
                (scope_rowid, member_rowid),
            )
            if owner:
                conn.execute(
                    "UPDATE memberdef SET definition = "
                    "REPLACE(definition, ?, ? || '::' || ?) WHERE rowid = ?",
                    (member_name, owner, member_name, member_rowid),
                )
            if impl.for_item_id in trait_methods_by_name:
                trait_methods_by_name[impl.for_item_id][member_name] = member_rowid
    return trait_methods_by_name


## @brief Insert `reimplements` rows pairing a trait impl's methods to the trait's own.
## @param conn Open connection.
## @param state Shared rowid state (read only here).
## @param impls Every impl block.
## @param trait_methods_by_name From `_write_member_rows`: trait item id -> {name: rowid}.
## @return None.
## @version 1
## @dg_internal
def _write_reimplements_rows(
    conn: sqlite3.Connection,
    state: _WriteState,
    impls: list[_Impl],
    trait_methods_by_name: dict[str, dict[str, int]],
) -> None:
    """@brief Pair each trait impl's methods against the trait's own by name."""
    for impl in impls:
        if impl.trait_item_id is None:
            continue
        trait_methods = trait_methods_by_name.get(impl.trait_item_id)
        if not trait_methods:
            continue
        for member_id in impl.member_item_ids:
            member_rowid = state.item_to_rowid.get(member_id)
            reimplemented = trait_methods.get(state.item_to_name.get(member_id, ""))
            if member_rowid is None or reimplemented is None:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO reimplements (memberdef_rowid, reimplemented_rowid) "
                "VALUES (?, ?)",
                (member_rowid, reimplemented),
            )


## @brief Write struct/enum/trait compounds and their member/override relations.
## @param conn Open connection.
## @param state Shared rowid state from `_write_symbols`.
## @param compounds Every struct/enum/trait collected across every target's JSON.
## @param impls Every impl block (plus each trait's own self-membership) collected.
## @return None.
## @version 3
## @dg_internal
def _write_compounds(
    conn: sqlite3.Connection,
    state: _WriteState,
    compounds: list[_Compound],
    impls: list[_Impl],
) -> None:
    """Three passes, in order, because `reimplements` resolution needs EVERY
    trait's own methods already linked before a concrete impl's methods can be
    paired against them by name — the same build-then-resolve order
    `_write_symbols`'s de-dup already follows.

    A `for_item_id`/`trait_item_id`/member id that never resolved to a rowid
    (the target type isn't one of THIS crate's own compounds, or the member
    had no captured span) is silently skipped rather than guessed at — the
    same fail-closed rule `dispatch_edges._matching_compounds` already
    applies one layer up.

    @brief Insert `compounddef`, `member` and `reimplements` rows.
    @version 3
    """
    _write_compound_rows(conn, state, compounds)
    trait_methods_by_name = _write_member_rows(conn, state, compounds, impls)
    _write_reimplements_rows(conn, state, impls, trait_methods_by_name)
    conn.commit()


## @brief Synthesize a doxygen-shaped SQLite database for a Rust repository.
## @param repo_root Repository root (a cargo package or workspace).
## @param db_path Where to write the resulting database.
## @return `db_path`, for symmetry with `doxygen.run_doxygen`'s return contract.
## @version 2
## @utility
def run_rustdoc(repo_root: Path, db_path: Path) -> Path:
    """The Rust analog of `doxygen.run_doxygen`: same contract (a Path to a
    finished database in place of a Doxyfile-driven `doxygen` invocation), so a
    caller downstream of either — `copy_database`, then every `_build_stages`
    harvester — cannot tell which front end produced its input.

    Every target's rustdoc JSON is generated into ONE scratch `--target-dir`
    outside the repo (never inside it, matching `_doxygen_out_dir`'s rule), torn
    down when this function returns.

    Also writes `compounddef`/`member`/`reimplements` rows for structs, enums,
    traits and their impl blocks (v2) — the data `dispatch_edges.py`'s declared
    interface-binding producer needs to resolve a `trait Foo` / `impl Foo for
    Bar` pairing for a Rust repo exactly as it already does for a declared C++
    interface/implementor pair.

    @brief Build a Rust repo's structural index via rustdoc JSON.
    @return Path to the generated database (`db_path`).
    @raises RustdocUnavailableError when cargo/nightly rustdoc is unusable, or no
        lib/bin target is found.
    @version 2
    """
    repo_root = Path(repo_root).resolve()
    _require_nightly_rustdoc()
    targets = _discover_targets(repo_root)
    if not targets:
        raise RustdocUnavailableError(
            f"no cargo lib or bin target found under {repo_root} — nothing to document."
        )
    symbols: list[_Symbol] = []
    compounds: list[_Compound] = []
    impls: list[_Impl] = []
    with tempfile.TemporaryDirectory(prefix="clew-rustdoc-") as scratch:
        scratch_dir = Path(scratch)
        for index, target in enumerate(targets):
            json_path = _run_rustdoc_json(repo_root, target, scratch_dir)
            doc = json.loads(json_path.read_text(encoding="utf-8"))
            # Each target's rustdoc JSON numbers its own items from scratch, so
            # a bare item id from target 0 and target 1 can collide — prefixed
            # here, once, rather than in every extraction function.
            prefix = str(index)
            symbols.extend(_symbols_from_json(doc, prefix))
            compounds.extend(_compounds_from_json(doc, prefix))
            impls.extend(_impls_from_json(doc, prefix))
            impls.extend(_trait_self_membership(doc, prefix))
    conn = _create_schema(Path(db_path))
    try:
        state = _write_symbols(conn, symbols)
        _write_compounds(conn, state, compounds, impls)
    finally:
        conn.close()
    logger.info(
        "rustdoc: indexed %d symbol(s), %d compound(s) across %d target(s) into %s",
        len(symbols),
        len(compounds),
        len(targets),
        db_path,
    )
    return Path(db_path)
