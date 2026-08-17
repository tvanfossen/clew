# SPDX-License-Identifier: MIT
"""The CONFIGURATION SPACE a repo declares in Kconfig — structure and help text.

gh#18. Kconfig is the configuration system of most of the embedded C world this
tool targets (Zephyr, Linux, U-Boot, Buildroot, ESP-IDF), and the pipeline read
none of it while reading `.doxygen-guard.yaml`, `.pre-commit-config.yaml` and a
Doxyfile. Kconfig *is* a declaration — a formal, parseable one — so ignoring it
was the no-hardcoding mandate's own omission.

## STRUCTURE vs INSTANCE, and why they are two separate features

gh#17 (`preprocessor.py`) records WHICH configuration an index was built in. This
module records WHAT CONFIGURATIONS EXIST. Conflating them is the failure this file
is arranged to prevent: nothing here stores a symbol's RESOLVED value, because a
resolved value belongs to one build and would read as a property of the
repository. A `default` is part of the space and is stored; `y` for this build is
not, and lives in `preprocessor.*` / `kconfig.*` `build_meta` rows instead.

## THE LOAD-BEARING PART IS THE HELP TEXT

The argument for this is not that structure is nice to have. A `help` block is a
documentation surface with no equivalent anywhere else in a repository, and it
routinely carries the only statement of a known limitation — a variant whose
overcurrent thresholds are placeholders reused from a sibling variant pending real
measurements, documented in Kconfig and in no comment, doc or requirement. An
engineer asking "are these limits real?" gets the answer there or from nobody.

So `ingest_kconfig_prose` is the part with the highest value per line: it needs no
new table, and it makes that note answer `search_prose("overcurrent threshold")`.

## THE DEPENDENCY IS HARD, DELIBERATELY

`kconfiglib` is a REQUIRED dependency, not an extra, and the reasoning is this
project's own history rather than a preference:

  - `pyproject`'s abolition of the `mcp` extra recorded the cost of optionality:
    "a plain install produced a tool whose `init` cheerfully registered a server
    that could not start". That argument was about the core product and does not
    transfer on its own — Kconfig ingestion is a minority-target feature.
  - What DOES transfer is the standing lesson that **"no rows" is a claim about
    the detector until you have checked whether the detector could look.** It has
    been measured wrong three times here, most expensively when 1093 macro
    accessor call sites were written down as a correct negative. An optional
    `kconfiglib` gives `kconfig_symbols` two indistinguishable ways to be empty,
    which is exactly that defect installed on purpose.
  - `harvest._try_import_ts_module` swallows `ImportError` and returns None, and
    `pyproject` names that as the hazard a declared dependency avoids.
  - The COST of the hard dependency is near zero: `kconfiglib` is one pure-Python
    module with no transitive dependencies and an ISC licence.

Writing a minimal Kconfig parser was rejected by the issue and is rejected here
for the same reason: `source`/`rsource` path semantics, `$(VAR)` expansion,
`choice` scoping and `depends on` inheritance are a real grammar, and a bad
reimplementation produces plausible wrong structure.

**The dependency being present does NOT make the capability unconditionally
present**, and that is why every outcome is recorded. A Zephyr application's
top-level Kconfig `source`s the Zephyr tree's own; run outside a west workspace,
that parse FAILS. So `KconfigModel.error` is a first-class field, it is stamped
into `build_meta` as `kconfig.error`, and a build that found a Kconfig and could
not read it says so instead of shipping zero rows.

@brief Discover, parse and store a repo's Kconfig configuration space.
@version 1
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._common import logger
from .vocabulary import KCONFIG_TYPE, KCONFIG_TYPE_UNKNOWN, check

## The declaration section this module owns. Registered in
## `declaration.KNOWN_SECTIONS`, so a misspelling is REFUSED rather than parsed into a
## mapping nothing reads.
SECTION_KCONFIG = "kconfig"

## The one key inside it: the repo-relative path of the TOP-LEVEL Kconfig file.
KEY_ROOT = "root"

## Provenance values for `kconfig.source`. Per-module constants rather than
## `vocabulary.py` entries, matching `preprocessor.py`, `scope.py` and `precommit.py`:
## these are `build_meta` strings, and `vocabulary.py` is the source for values a DDL
## CHECK constrains.
SOURCE_NONE = "none"
SOURCE_DECLARED = "declared"
SOURCE_ROOT = "repo root"
SOURCE_CONVENTIONAL = "conventional directory"

## The conventional filename, at the repo root. This is THE convention — Linux,
## Zephyr, Buildroot and ESP-IDF all put the top of the tree here — so an
## unambiguous root `Kconfig` needs no declaration to be believed.
KCONFIG_NAME = "Kconfig"

## Conventional NON-ROOT locations, searched only after the root misses. Each is an
## application layout a build system defines rather than a pattern we invented:
## Zephyr and ESP-IDF applications keep the top of their own configuration under
## `app/` or `main/`. Deliberately a fixed tuple and NOT a `**/Kconfig` glob — a
## Zephyr tree contains hundreds of `Kconfig` files, all of them sourced from
## somewhere, and picking one alphabetically is how `discover_doxyfile` was caught
## selecting a test fixture's Doxyfile to index a whole project.
_CONVENTIONAL_DIRS = ("app", "main", "src")


## @brief Where a repo's top-level Kconfig is, and how that was determined.
## @version 1
@dataclass(frozen=True)
class KconfigLocation:
    """The discovered path (None when there is none), the provenance of that answer,
    and every location that was tried.

    `searched` is the load-bearing field, for the reason
    `precommit.GuardConfigLocation.searched` and `preprocessor.PreprocessorConfig.searched`
    both record: a capability that finds nothing and does not say where it looked
    leaves "this repo has no Kconfig" indistinguishable from "we looked in the wrong
    place", and the observable result of both is zero rows.

    Paths are REPO-RELATIVE. `build_meta` is published over MCP, and an absolute path
    here would reintroduce the machine-layout disclosure that forced the
    build-version-9 bump.

    @brief A located (or unlocated) top-level Kconfig with its provenance.
    @version 1
    """

    path: Path | None
    source: str = SOURCE_NONE
    searched: tuple[str, ...] = ()

    ## @brief Human-readable list of the locations that were tried.
    ## @return Comma-joined search locations, or a note that none were tried.
    ## @version 1
    ## @req REQ-DDB-CONFIG-005
    def describe_search(self) -> str:
        """@brief Render `searched` for a log line or a recorded reason.

        @return Comma-joined locations, or a note that none were tried.
        @version 1
        """
        return ", ".join(self.searched) if self.searched else "no locations searched"


## @brief One Kconfig symbol: its identity, its type, and the prose attached to it.
## @version 1
@dataclass(frozen=True)
class KconfigSymbol:
    """A symbol as DECLARED, never as resolved — see the module docstring on
    structure versus instance.

    `choice_key` is the synthetic identity of the `choice` group this symbol belongs
    to, or None. A synthetic key is necessary rather than tidy: a `choice` block is
    very often ANONYMOUS (both of them are, in the target this was first exercised
    on), so `name` cannot be the identity and the prompt alone is not unique across
    files.

    @brief One declared Kconfig symbol.
    @version 1
    """

    name: str
    type: str
    prompt: str = ""
    help: str = ""
    default: str = ""
    choice_key: int | None = None
    file_path: str = ""
    line: int = 0


## @brief One `choice` group: a set of MUTUALLY EXCLUSIVE symbols.
## @version 1
@dataclass(frozen=True)
class KconfigChoice:
    """`choice` semantics are the reason this is a table rather than a column. Exactly
    one member of a group is selected, so grouped symbols are ALTERNATIVES and not
    independent features — a consumer reasoning about reachability that misses this
    will happily describe two mutually exclusive variants as both present.

    `name` is empty for an anonymous `choice`, which is the common shape; `prompt` is
    then the only human identity it has, and `key` is what the symbol rows join on.

    @brief One Kconfig choice group.
    @version 1
    """

    key: int
    name: str = ""
    prompt: str = ""
    default: str = ""
    file_path: str = ""
    line: int = 0


## @brief A repo's parsed configuration space, plus how the parse went.
## @version 1
@dataclass(frozen=True)
class KconfigModel:
    """`error` is a FIRST-CLASS field, not an exception that got away.

    A hard dependency removes one of the two ways this layer can be silently empty;
    it does not remove the other. A Zephyr application's top-level Kconfig `source`s
    the Zephyr tree's own, so parsing it outside a west workspace raises — and a
    build that FOUND a Kconfig and could not read it must not look like a repo that
    has none. `as_meta` stamps the difference.

    @brief A parsed Kconfig space with its provenance and any parse error.
    @version 1
    """

    location: KconfigLocation
    symbols: tuple[KconfigSymbol, ...] = ()
    choices: tuple[KconfigChoice, ...] = ()
    error: str = ""
    warnings: tuple[str, ...] = field(default=())

    ## @brief Whether the repo has a top-level Kconfig at all.
    ## @return True when discovery found one, whether or not it parsed.
    ## @version 1
    ## @req REQ-DDB-CONFIG-005
    @property
    def found(self) -> bool:
        """NOT `bool(self.symbols)`. A Kconfig that was found and failed to parse is
        a FINDING, and it is the finding a Zephyr app indexed outside its workspace
        produces.

        @brief Did discovery find a Kconfig?
        @return True when a path was located.
        @version 1
        """
        return self.location.path is not None

    ## @brief How many symbols carry help text — the surface gh#18 exists for.
    ## @return Count of symbols with a non-empty help block.
    ## @version 1
    ## @req REQ-DDB-CONFIG-005
    @property
    def documented(self) -> int:
        """@brief Count symbols carrying a help block.

        @return Number of symbols with help text.
        @version 1
        """
        return sum(1 for sym in self.symbols if sym.help)

    ## @brief Flatten to string values for build_meta persistence.
    ## @return Mapping of unprefixed kconfig keys to string values.
    ## @version 1
    ## @req REQ-DDB-CONFIG-005
    def as_meta(self) -> dict[str, str]:
        """Counts are STRINGS because `write_build_signature` drops falsy values, and a
        measured zero must survive: `"0"` is truthy where `0` is not. That is the same
        rule `coverage.as_meta` and `preprocessor.as_meta` document, and here it is
        what makes "found a Kconfig, parsed it, it declares nothing" distinguishable
        from "no Kconfig".

        Returns {} — no `kconfig.*` rows at all — only when NOTHING was found, so an
        absent key honestly reads as "not recorded" and every existing target's
        `build_meta` is unchanged.

        @brief Kconfig provenance and counts as build_meta values.
        @return Unprefixed key -> string value.
        @version 1
        """
        if not self.found:
            return {}
        return {
            "source": self.location.source,
            "root": str(self.location.path),
            "symbol_count": str(len(self.symbols)),
            "choice_count": str(len(self.choices)),
            "documented_count": str(self.documented),
            "error": self.error,
        }


## @brief Locate a repo's top-level Kconfig: declared, root, then convention.
## @param repo_root Repo root to search.
## @param declaration The repo's parsed declaration (from load_declaration).
## @return A KconfigLocation whose `path` is None when nothing was found.
## @version 1
## @req REQ-DDB-CONFIG-005
def discover_kconfig(
    repo_root: Path | str | None, declaration: dict[str, Any] | None = None
) -> KconfigLocation:
    """Follows `precommit.discover_guard_config` exactly — explicit, then
    convention, then a REFUSAL when convention is ambiguous — because the wrong
    answer here has the same shape as the wrong answer there: a Kconfig belonging to
    a vendored subsystem describes a configuration space the repo does not ship,
    and every count taken from it looks legitimate.

    `path` on the returned location is REPO-RELATIVE, and that is not only a
    disclosure rule. kconfiglib resolves `source` paths against `$srctree`, so the
    parse is driven from a relative path anyway and every filename it reports comes
    back relative — one convention end to end rather than two that must be
    reconciled per row.

    @brief Discover the repo's top-level Kconfig with its provenance.
    @return The located Kconfig and how it was found.
    @version 1
    """
    if repo_root is None:
        return KconfigLocation(path=None)
    root = Path(repo_root).expanduser().resolve()
    declared = (declaration or {}).get(SECTION_KCONFIG)
    if isinstance(declared, dict) and declared.get(KEY_ROOT):
        return _declared_kconfig(root, str(declared[KEY_ROOT]))
    return _conventional_kconfig(root)


## @brief Resolve an explicitly declared Kconfig path, warning when it is missing.
## @param root Resolved repo root.
## @param declared The repo-relative path the declaration names.
## @return The location; `path` is None when the declared file does not exist.
## @version 1
## @dg_internal
def _declared_kconfig(root: Path, declared: str) -> KconfigLocation:
    """A declared-but-missing path WARNS rather than failing the build, matching
    `declaration.declared_path` and `preprocessor._named_config_header` — and the
    recorded `kconfig.source` is absent in that case, so the resulting zero rows
    are attributable to the typo by reading the warning rather than by guessing.

    @brief Resolve a declared Kconfig root.
    @return The located (or unlocated) Kconfig.
    @version 1
    """
    path = (root / declared).resolve()
    if not path.is_file():
        logger.warning(
            "kconfig: %s.%s names %s, which does not exist — no configuration space indexed",
            SECTION_KCONFIG,
            KEY_ROOT,
            declared,
        )
        return KconfigLocation(path=None, searched=(declared,))
    return KconfigLocation(path=Path(declared), source=SOURCE_DECLARED, searched=(declared,))


## @brief Find a conventionally-placed Kconfig: repo root, then a fixed set of dirs.
## @param root Resolved repo root.
## @return The location; `path` is None when nothing was found or convention was ambiguous.
## @version 1
## @dg_internal
def _conventional_kconfig(root: Path) -> KconfigLocation:
    """Root first, because an unambiguous root `Kconfig` is the convention every
    Kconfig-based build system shares and needs no declaration to be believed. Then
    the fixed application directories, which is the only step that CAN be ambiguous
    and therefore the only one that refuses.

    @brief Locate a conventional Kconfig, refusing to guess among several.
    @return The located (or unlocated) Kconfig.
    @version 1
    """
    candidates = [KCONFIG_NAME] + [f"{d}/{KCONFIG_NAME}" for d in _CONVENTIONAL_DIRS]
    searched = tuple(candidates)
    if (root / KCONFIG_NAME).is_file():
        return KconfigLocation(path=Path(KCONFIG_NAME), source=SOURCE_ROOT, searched=searched)
    found = [rel for rel in candidates[1:] if (root / rel).is_file()]
    if len(found) == 1:
        return KconfigLocation(path=Path(found[0]), source=SOURCE_CONVENTIONAL, searched=searched)
    if found:
        logger.warning(
            "kconfig: found %d candidates (%s) and is NOT guessing which configuration "
            "space this repo ships — declare it as %s.%s",
            len(found),
            ", ".join(found),
            SECTION_KCONFIG,
            KEY_ROOT,
        )
    return KconfigLocation(path=None, searched=searched)


## @brief Set `$srctree` for the duration of a kconfiglib parse, then restore it.
## @param root Absolute repo root kconfiglib should resolve `source` paths against.
## @return A context manager yielding nothing.
## @version 1
## @dg_internal
@contextlib.contextmanager
def _srctree(root: Path) -> Iterator[None]:
    """kconfiglib reads `$srctree` from the ENVIRONMENT — there is no constructor
    argument for it — so driving a parse rooted anywhere but the process's cwd means
    mutating `os.environ`. Restored in a `finally` because this runs inside a longer
    pipeline: leaking `srctree` would silently redirect any later Kconfig parse, and
    the MCP server is a long-lived process that builds several targets.

    The PREVIOUS value is put back rather than the key deleted, so a caller who set
    `srctree` deliberately (a Zephyr west environment does) still has it afterwards.

    @brief Temporarily point kconfiglib's `$srctree` at a repo root.
    @version 1
    """
    previous = os.environ.get("srctree")
    os.environ["srctree"] = str(root)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("srctree", None)
        else:
            os.environ["srctree"] = previous


## @brief Parse a located Kconfig into the configuration space it declares.
## @param location A KconfigLocation whose path is repo-relative.
## @param repo_root Repo root the location's path is relative to.
## @return The parsed model; carries `error` and no rows when the parse failed.
## @version 2
## @req REQ-DDB-CONFIG-005
def load_kconfig(location: KconfigLocation, repo_root: Path | str) -> KconfigModel:
    """DEGRADES TO A RECORDED ERROR, never to an exception. A configuration space is
    metadata about a repository; failing an index build over it would take a whole
    doxygen run with it, and the parse can fail for a completely ordinary reason —
    a Zephyr application's Kconfig `source`s the Zephyr tree's own, so it is
    unparseable outside a west workspace.

    kconfiglib's warnings are CAPTURED rather than printed (`warn_to_stderr=False`)
    and reported at INFO with a count. They are genuinely informative — an undefined
    symbol in a `select` is a real defect in the target — but they are the target's
    business and not a reason to make our build look broken.

    @brief Parse a repo's Kconfig, recording any failure instead of raising.
    @return The parsed configuration space.
    @version 2
    """
    if location.path is None:
        return KconfigModel(location=location)
    root = Path(repo_root).expanduser().resolve()
    try:
        with _srctree(root):
            import kconfiglib

            kconf = kconfiglib.Kconfig(str(location.path), warn_to_stderr=False)
    except Exception as exc:
        logger.warning("kconfig: %s could not be parsed (%s)", location.path, exc)
        return KconfigModel(location=location, error=f"{type(exc).__name__}: {exc}")
    return _model_from_kconf(kconf, location)


## @brief Build the stored model from a successfully parsed kconfiglib tree.
## @param kconf A parsed kconfiglib.Kconfig.
## @param location Where it was parsed from.
## @return The populated model.
## @version 1
## @dg_internal
def _model_from_kconf(kconf: Any, location: KconfigLocation) -> KconfigModel:
    """`unique_defined_syms` and `unique_choices` are kconfiglib's own de-duplicated
    views, so a symbol defined in two files yields ONE row. That matters for the same
    reason `_definition_preferring_name_index` does on the doxygen side: a consumer
    counting the variant space must not count a re-declaration twice.

    Choice keys are assigned by ENUMERATION ORDER over `unique_choices`, which is
    file order, so the same tree yields the same keys on every build — a key that
    moved between builds would make a stored `choice_key` meaningless across an
    incremental refresh.

    @brief Convert a parsed kconfiglib tree into stored rows.
    @return The model.
    @version 1
    """
    choice_keys = {id(choice): index for index, choice in enumerate(kconf.unique_choices, 1)}
    choices = tuple(
        _choice_row(choice, choice_keys[id(choice)], kconf) for choice in kconf.unique_choices
    )
    symbols = tuple(_symbol_row(sym, kconf, choice_keys) for sym in kconf.unique_defined_syms)
    warnings = tuple(str(w) for w in getattr(kconf, "warnings", ()))
    if warnings:
        logger.info(
            "kconfig: %s parsed with %d warning(s) from the target's own tree",
            location.path,
            len(warnings),
        )
    logger.info(
        "kconfig: %s declares %d symbol(s) in %d choice group(s); %d carry help text",
        location.path,
        len(symbols),
        len(choices),
        sum(1 for s in symbols if s.help),
    )
    return KconfigModel(location=location, symbols=symbols, choices=choices, warnings=warnings)


## @brief The first of a node list that satisfies a predicate, as text.
## @param nodes A symbol's or choice's MenuNode list.
## @param attribute The node attribute to read ('help' or 'prompt').
## @return The first non-empty value, or "".
## @version 1
## @dg_internal
def _first_text(nodes: Any, attribute: str) -> str:
    """A symbol may be declared in SEVERAL places, each with its own menu node, and
    only some of them carry the prose. Taking `nodes[0]` unconditionally therefore
    loses help text that is plainly in the tree — which is the one thing gh#18 exists
    to surface — so this takes the first node that HAS the field.

    `prompt` is a `(text, condition)` tuple while `help` is a plain string, so the
    tuple's head is unwrapped here rather than at both call sites.

    @brief First non-empty prose value across a symbol's menu nodes.
    @return The text, or "".
    @version 1
    """
    for node in nodes or ():
        value = getattr(node, attribute, None)
        text = value[0] if isinstance(value, tuple) and value else value
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


## @brief Render a `defaults` list as the Kconfig text it came from.
## @param defaults A kconfiglib `defaults` list of (value, condition) pairs.
## @param kconf The parsed Kconfig, whose `y` is the unconditional sentinel.
## @return One line per default, conditions included; "" when there are none.
## @version 2
## @dg_internal
def _defaults_text(defaults: Any, kconf: Any) -> str:
    """CONDITIONS ARE KEPT. `default FOO if BAR` and `default FOO` say different
    things about which variant is the unstated one, and dropping the `if` would turn
    a conditional default into an unconditional claim — a wrong answer wearing the
    shape of a right one.

    Rendered through kconfiglib's own `expr_str`, so what is stored is the Kconfig
    expression the author wrote rather than our paraphrase of it.

    The unconditional sentinel is `kconf.y` — an INSTANCE attribute, the parsed tree's
    own constant `y` symbol, not `kconfiglib.y`. Reading it off the module raises
    `AttributeError`, which is how the first version of this failed: every default in
    the fixture, conditional or not, went through the same branch.

    @brief Render a symbol's or choice's defaults, conditions and all.
    @return Newline-joined default expressions.
    @version 2
    """
    import kconfiglib

    lines = []
    for value, condition in defaults or ():
        text = kconfiglib.expr_str(value)
        if condition is not kconf.y:
            text = f"{text} if {kconfiglib.expr_str(condition)}"
        lines.append(text)
    return "\n".join(lines)


## @brief One symbol row from a kconfiglib Symbol.
## @param sym The kconfiglib Symbol.
## @param kconf The parsed Kconfig the symbol belongs to.
## @param choice_keys id(choice) -> synthetic choice key.
## @return The stored row.
## @version 2
## @dg_internal
def _symbol_row(sym: Any, kconf: Any, choice_keys: dict[int, int]) -> KconfigSymbol:
    """`orig_type` rather than `type`, deliberately. kconfiglib's `type` reports a
    `bool` for a symbol whose declared type is `tristate` once modules are disabled —
    the RESOLVED type under one configuration — and this table stores the space, not
    an instance.

    A type kconfiglib does not recognise is filed as 'unknown' rather than dropped,
    because that value is registered in the vocabulary precisely so a referenced-but-
    untyped symbol has a row: an absent row is indistinguishable from a symbol that
    does not exist.

    @brief Convert one kconfiglib Symbol to a stored row.
    @return The symbol row.
    @version 2
    """
    import kconfiglib

    node = sym.nodes[0] if sym.nodes else None
    declared = kconfiglib.TYPE_TO_STR.get(sym.orig_type, KCONFIG_TYPE_UNKNOWN)
    choice = getattr(sym, "choice", None)
    return KconfigSymbol(
        name=sym.name,
        type=declared if declared in KCONFIG_TYPE else KCONFIG_TYPE_UNKNOWN,
        prompt=_first_text(sym.nodes, "prompt"),
        help=_first_text(sym.nodes, "help"),
        default=_defaults_text(sym.defaults, kconf),
        choice_key=choice_keys.get(id(choice)) if choice is not None else None,
        file_path=str(node.filename) if node is not None else "",
        line=int(node.linenr) if node is not None else 0,
    )


## @brief One choice row from a kconfiglib Choice.
## @param choice The kconfiglib Choice.
## @param key The synthetic choice key symbols join on.
## @param kconf The parsed Kconfig the choice belongs to.
## @return The stored row.
## @version 2
## @dg_internal
def _choice_row(choice: Any, key: int, kconf: Any) -> KconfigChoice:
    """@brief Convert one kconfiglib Choice to a stored row.

    @return The choice row.
    @version 2
    """
    node = choice.nodes[0] if choice.nodes else None
    return KconfigChoice(
        key=key,
        name=choice.name or "",
        prompt=_first_text(choice.nodes, "prompt"),
        default=_defaults_text(choice.defaults, kconf),
        file_path=str(node.filename) if node is not None else "",
        line=int(node.linenr) if node is not None else 0,
    )


## @brief Idempotent creation of the kconfig_choices and kconfig_symbols tables.
## @param conn Open connection to the index being built.
## @version 1
## @req REQ-DDB-SCHEMA-013
def ensure_kconfig_tables(conn: sqlite3.Connection) -> None:
    """`kconfig_gates` is created by `kconfig_gates.py`, next to the harvest that
    fills it, for the same reason `lock_acquisitions` lives with the lock scan: the
    two layers fail independently — a repo can have a parseable Kconfig and no C
    sources, or gated C and an unparseable Kconfig — and a shared creator would make
    one layer's absence look like the other's.

    `choice_key` is a plain INTEGER rather than a foreign key into `kconfig_choices`,
    because it is a SYNTHETIC per-build ordinal, not a durable identity. Declaring a
    REFERENCES on it would suggest a stability across builds that the enumeration
    order does not promise for a tree whose files changed.

    @brief Create the Kconfig structure tables.
    @version 1
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kconfig_choices (
            key       INTEGER PRIMARY KEY,
            name      TEXT NOT NULL,
            prompt    TEXT NOT NULL,
            default_expr TEXT NOT NULL,
            file_path TEXT NOT NULL,
            line      INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS kconfig_symbols (
            name         TEXT NOT NULL,
            type         TEXT NOT NULL {check("kconfig_symbols", "type")},
            prompt       TEXT NOT NULL,
            help         TEXT NOT NULL,
            default_expr TEXT NOT NULL,
            choice_key   INTEGER,
            file_path    TEXT NOT NULL,
            line         INTEGER NOT NULL,
            UNIQUE(name)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kconfig_symbols_choice ON kconfig_symbols(choice_key)"
    )
    conn.commit()


## @brief Persist a parsed configuration space into the index.
## @param db_path Path to the index being built.
## @param model The parsed model.
## @return Number of symbol rows written.
## @version 1
## @req REQ-DDB-CONFIG-005
def store_kconfig(db_path: Path, model: KconfigModel) -> int:
    """CREATES THE TABLES EVEN WHEN THERE IS NOTHING TO PUT IN THEM, as long as a
    Kconfig was FOUND. An empty table and an absent table say different things: the
    first is "we looked and this repo declares nothing", the second is "this layer
    never ran". A consumer distinguishing a correct negative from a detector failure
    needs both, and this repo has recorded the wrong one three times.

    A repo with NO Kconfig gets no tables at all, so its schema and its query results
    are byte-identical to a build before this module existed.

    @brief Write the Kconfig structure tables.
    @return Symbol row count.
    @version 1
    """
    if not model.found:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_kconfig_tables(conn)
        conn.executemany(
            "INSERT OR REPLACE INTO kconfig_choices"
            "(key, name, prompt, default_expr, file_path, line) VALUES(?,?,?,?,?,?)",
            [(c.key, c.name, c.prompt, c.default, c.file_path, c.line) for c in model.choices],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO kconfig_symbols"
            "(name, type, prompt, help, default_expr, choice_key, file_path, line) "
            "VALUES(?,?,?,?,?,?,?,?)",
            [
                (s.name, s.type, s.prompt, s.help, s.default, s.choice_key, s.file_path, s.line)
                for s in model.symbols
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return len(model.symbols)


## @brief Feed every symbol's prompt and help text into the FTS5 prose corpus.
## @param db_path Path to the index being built.
## @param model The parsed model.
## @return Number of prose chunks inserted.
## @version 1
## @req REQ-DDB-CONFIG-005
def ingest_kconfig_prose(db_path: Path, model: KconfigModel) -> int:
    """THE HIGHEST-VALUE PART OF gh#18 PER LINE, and it needs no new table. A `help`
    block routinely carries the only statement of a known limitation in a whole
    repository — a variant whose current limits are placeholders reused from a
    sibling pending real measurements — and until this ran, `search_prose` could not
    reach a word of it.

    MUST RUN AFTER `prose.ingest_supplementary_docs`, which DROPs and recreates
    `supplementary_docs` on every build. Running before it would insert these rows
    and then delete them, and the observable result would be an empty search with no
    error anywhere — the quietest possible failure.

    The symbol NAME goes in the heading and is repeated in the content, because FTS5
    ranks over the columns it is given and an engineer searching for a limitation
    types words from the help text, while one auditing a symbol types its name. Both
    have to hit.

    @brief Insert Kconfig prompts and help blocks into the prose corpus.
    @return Chunk count.
    @version 1
    """
    rows = [
        (
            sym.file_path or str(model.location.path),
            f"CONFIG_{sym.name}" + (f" — {sym.prompt}" if sym.prompt else ""),
            "\n".join(part for part in (f"CONFIG_{sym.name}", sym.prompt, sym.help) if part),
        )
        for sym in model.symbols
        if sym.prompt or sym.help
    ]
    if not rows:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS supplementary_docs "
            "USING fts5(file_path, heading, content)"
        )
        conn.executemany(
            "INSERT INTO supplementary_docs (file_path, heading, content) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("kconfig: %d prompt/help chunk(s) ingested into the prose corpus", len(rows))
    return len(rows)


## @brief Discover, parse, store and index a repo's configuration space.
## @param db_path Path to the index being built.
## @param repo_root Repo root to discover the Kconfig under.
## @param declaration The repo's parsed declaration (from load_declaration).
## @return The parsed model, for the caller to stamp into build_meta.
## @version 2
## @req REQ-DDB-CONFIG-005
def import_kconfig(
    db_path: Path, repo_root: Path | str | None, declaration: dict[str, Any] | None = None
) -> KconfigModel:
    """The one entry point `cli._build_stages` calls. Returns the model rather than
    only counts, because the caller's `write_build_signature` needs the provenance —
    and because a stage that reports a number and discards the reason why it is that
    number is the defect persisting the scope decision fixed.

    Reachable with nothing but `repo_root` and the declaration, so the MCP server
    gets it with no per-section plumbing: CLAUDE.md's rule is that a declaration
    reachable only from an argument is not a declaration, and the MCP build passes
    no override arguments.

    @brief Run the whole Kconfig ingestion stage.
    @return The parsed configuration space.
    @version 2
    """
    location = discover_kconfig(repo_root, declaration)
    if location.path is None:
        logger.info("kconfig: none found — searched %s", location.describe_search())
        return KconfigModel(location=location)
    model = load_kconfig(location, repo_root or ".")
    store_kconfig(db_path, model)
    ingest_kconfig_prose(db_path, model)
    return model
