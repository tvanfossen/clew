# SPDX-License-Identifier: MIT
"""A target repo's own `.clew.yaml` — its declared indexing conventions.

clew's central mandate is built-in defaults plus a DECLARED override, never a
hardcoded assumption about a repo's shape. Every override was a CLI flag —
`--shared-key-patterns`, `--thread-patterns`, `--mqtt-dispatch`, `--data-model` —
and the MCP server passes none of them. So through the MCP server, which is the
primary surface, the built-in defaults WERE the whole policy: the one thing the
mandate exists to prevent. It also explains measured emptiness that reads as a
finding — a C/POSIX library's `shared_key_edges=0` is called a correct negative
for an undeclared DCI convention, but via MCP there was no way to declare it even
if the owner wanted to.

A repo now states its conventions in-tree and BOTH entry points pick them up with
no per-section plumbing at all, because both already supply the repo root. That
also closes the CLI-vs-MCP divergence class that #49 (only MCP discovered the
repo's Doxyfile) and #53 (output written into the repo) were instances of: there
is one discovery path, not two.

Each section holds EXACTLY what the corresponding standalone manifest holds, so
a repo can move an existing file's contents in verbatim and there is one format
to learn rather than two::

    # <repo>/.clew.yaml
    shared_key_patterns:          # as --shared-key-patterns
      writers:
        - name_prefix: "Store_Set"
      readers:
        - name_prefix: "Store_Get"
    thread_patterns:              # as --thread-patterns
      spawns:
        - name: "osThreadNew"
          entry_arg_index: 0
    mqtt_dispatch:                # as --mqtt-dispatch
      ...

An explicit CLI flag always WINS over the declaration: the file is the repo's
standing statement, the flag is a deliberate one-off override.

@brief Load a target repo's declared clew conventions.
@version 3
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._common import logger

## The two event ROLES, imported rather than restated: `event_edges` defines them and
## this module validates against them, so the spellings cannot drift. Safe in this
## direction only — `event_edges` imports nothing from the package, so there is no
## cycle, and it is the one section owner whose section NAME lives here rather than
## with the owner (its vocabulary is a declaration format, not an internal constant).
from .event_edges import CONSUMER, PRODUCER
from .precommit import (
    GUARD_CONFIG_NAME as GUARD_CONFIG_NAME,
)
from .precommit import discover_guard_config
from .vocabulary import DeclarationError

## The conventional filename. clew's OWN interface — not an assumption about
## any target's layout — in the same spirit as `.doxygen-guard.yaml`.
DECLARATION_NAME = ".clew.yaml"

## How `stated_document_meta` joins the section names. A COMMA-SPACE, matching `scope.py`'s
## separator rather than `tiers.py`'s newline, and safe here for the reason `tiers` is not:
## these are section names drawn from `KNOWN_SECTIONS`, every one of which is a bare
## lowercase identifier, so no value can contain the separator.
SECTION_SEPARATOR = ", "

## The file a target repo already maintains for the GATE. Its `x-` passthrough is the
## second place a declaration may live, so a repo needs no file that exists only for us.
##
## RE-EXPORTED from `precommit`, which owns discovery, rather than declared twice.
## The duplicate literal was one of gh#16's three independent hardcodings of the repo
## root, and the passthrough was the consumer that `--guard-config` could not reach.

## The tool name the passthrough key is suffixed with: `x-clew`. Matches the
## distribution name, so a reader seeing it in someone else's config knows what owns it.
PASSTHROUGH_TOOL = "clew"

## Sections that mirror a standalone manifest's whole document.
SECTION_SHARED_KEY = "shared_key_patterns"
SECTION_THREADS = "thread_patterns"
SECTION_MQTT = "mqtt_dispatch"
## Sections naming a repo-relative PATH, for formats this tool does not own.
SECTION_DATA_MODEL = "data_model"
## The target's requirements catalog, and its architecture-topics enrichment document.
##
## THESE TWO ARE HERE BECAUSE THE CLI COLLAPSED (22 build arguments to 6). Both were
## argparse flags and NOTHING ELSE — statable only by an operator with a shell, which is the
## precise shape CLAUDE.md names "a declaration reachable only from argv is not a
## declaration". An agent refreshing an index through MCP could not name either document,
## so a repo whose catalog is not at the conventional path had no route to it at all.
##
## A PATH AND NEVER A STRUCTURE, for both, and that is not laziness. There is no universal
## requirements.yaml shape — one target uses a flat `{id,title,...}` list, another a nested
## `domains:` tree read by its own generator, and `requirements._first` reads both
## additively — so a section accepting the catalog INLINE would force this tool to assume the
## shape the no-hardcoding mandate forbids it to assume. `resolve_catalog_path` keeps the
## whole precedence order (stated > this section > the guard's own
## `impact.requirements.file` > convention > nothing), so declaring this displaces neither
## the gate's declaration nor the convention — it inserts one tier above them.
SECTION_REQUIREMENTS = "requirements"
SECTION_ENRICH = "enrich"
## Lock primitives and repo-specific guard wrappers (R1 lock layer).
SECTION_LOCKS = "locks"
## The reachability entry-point patterns this repo uses. A repo whose handlers are
## reached only through indirect dispatch has no static caller for them, so liveness
## marks them orphan; naming that convention here reclaims them. Kept a DECLARATION
## rather than a built-in default because `%trampoline%`/`on_%` are repo-shaped —
## seeding a genuinely dead handler as live is a worse error than reporting a false
## orphan.
##
## A CITED FIGURE WAS DELETED HERE (2026-08-07), not corrected. It read "on a real
## C++ codebase, declaring its dispatch naming takes orphans from 61 to 17", and it
## fails MEASUREMENT PROVENANCE twice over: the target is unnamed, so no reader can
## reproduce it, and it was taken under the EXTEND semantics the tier rule below
## retired. It could not be re-measured either — the substitution attempt is itself
## the finding. NEITHER PUBLIC TARGET DECLARES THIS SECTION: entropic and mbedtls
## both resolve `entry_patterns` at tier 5, to the identical built-in ten, and both
## carry `options.entry_patterns.tier=heuristic` in `build_meta` to say so. Their
## orphan counts at build 30 are 0 of 1,999 and 4 of 5,788, so there is nothing for
## a declaration to reclaim on either. The rule is deliberately left stated as a
## MECHANISM, which needs no repo attached; a number here would need a public
## target that declares, and none exists yet.
##
## A TIER-2 STATEMENT (gh#319), so it REPLACES the built-in name-shape guesses
## (`reachability.ENTRY_PATTERN_HEURISTICS`) rather than extending them, and the
## language/platform entry points (`ENTRY_PATTERN_FACTS`) accumulate beneath it
## whatever it says. This used to MERGE over the whole default set, which made a repo
## stating its own vocabulary keep `%handler%` and `%task%` as well — and, worse, made
## the same values mean something different when moved onto `--entry-patterns`, which
## replaced everything including `main`.
SECTION_ENTRY_PATTERNS = "entry_patterns"
## Which paths hold TEST code, so a bare ambiguous name prefers the library definition.
## Declared rather than hardcoded because `tests/` is a convention: repos use `test/`,
## `spec/`, `t/` or colocate `foo_test.cpp` beside the code. A declaration DISPLACES the
## built-in guesses rather than extending them, per the layered rule.
SECTION_TEST_PATHS = "test_paths"
## VENDORED THIRD-PARTY PATHS — a plain list of repo-relative directories the repository did
## not write but DOES own, because it committed them.
##
## THIS IS NOT `external` AND MUST NOT BE FOLDED INTO IT (D4, owner 2026-08-13). `external` is
## a GIT TREE — a submodule or nested clone — and that definition is deliberate and recorded:
## `vendor/` and `third_party/` are conventions, while a copied-in third-party header with no
## git tree of its own IS first party by the only test that cannot be argued with, namely that
## the repo committed it and ships it. Redefining `external` to mean "looks vendored" would
## move `coverage`, `graph_stats` and every orphan count for a naming fashion.
##
## So this is a SEPARATE, DECLARED signal, and it has to be declared rather than inferred for
## the reason the no-hardcoding mandate gives: Mbed-TLS keeps its at `3rdparty/`, another repo
## at `external/`, another at `deps/`, and one directory named `3rdparty` full of first-party
## glue is a real thing. Measured on Mbed-TLS: `3rdparty/` (holding `everest` and `p256-m`) is
## COMMITTED, not a submodule — the only submodule there is `framework` — so
## `dg_external_root` is correctly NULL across all 570 rows and no git-tree test will ever
## find it. That is what makes the separate signal necessary rather than a relabelling.
SECTION_VENDORED = "vendored"
## Indirect-dispatch bindings: which concrete type backs an injected interface,
## where function-pointer handlers are registered and invoked, and which generic
## helpers take a shared key as an ARGUMENT. All three hide one endpoint of a
## relationship behind an indirection, so the static graph cannot see it — and
## all three are conventions, so the recovery has to be declared rather than
## inferred (a C++ codebase's broker fan-out, an RTOS repo's queue-of-callbacks and
## a C library's dispatch tables are three different shapes of one problem).
SECTION_DISPATCH = "dispatch"
## The PREPROCESSOR CONFIGURATION this index represents (gh#17): a `predefined:` macro
## list and/or a `config_header:` to harvest one from. Owned by `preprocessor.py`, which
## does not import this module and is not imported by it — the section name is repeated
## there as a literal and `tests/test_declaration.py` pins the two spellings together,
## the same trade `index_scope` already makes below.
##
## A DECLARATION rather than a default, and emphatically not a guess: doxygen evaluates
## `#if defined(X)` as it parses, so supplying the wrong macros does not merely widen or
## narrow an index — it makes the index describe a DIFFERENT VARIANT of the same code,
## while every count taken from it still looks legitimate.
SECTION_PREPROCESSOR = "preprocessor"
## The top-level `Kconfig` whose CONFIGURATION SPACE this index should describe
## (gh#18): `kconfig: {root: <repo-relative path>}`. Owned by `kconfig.py`, which does
## not import this module and is not imported by it — the section name is repeated
## there as a literal and `tests/test_declaration.py` pins the two spellings together,
## the same trade `index_scope` and `preprocessor` already make.
##
## Needed only when the top of the tree is somewhere `discover_kconfig`'s convention
## does not reach, or when convention is AMBIGUOUS and therefore refuses. Distinct
## from `preprocessor:` on purpose and the distinction is the whole of gh#18:
## `preprocessor:` says which variant this index IS, `kconfig:` says which variants
## EXIST. Conflating them would let a consumer read a `default` as a fact about the
## build.
SECTION_KCONFIG = "kconfig"
## The target's OWN Doxyfile, repo-relative, when `discover_doxyfile`'s conventions cannot
## reach it (gh#420): `doxyfile: doxygen/mbedtls.doxyfile`.
##
## WHY A DECLARATION AND NOT A WIDER SEARCH. Discovery matches the NAME `Doxyfile` in the repo
## root, `docs/` and `doc/`, and refuses to guess further because it once took
## `sorted(repo.glob("*/Doxyfile"))[0]` and chose a test FIXTURE's Doxyfile to index a whole
## project. Mbed-TLS/mbedtls ships `doxygen/mbedtls.doxyfile` — wrong directory AND wrong
## filename — so it was unreachable from BOTH routes: discovery would not look there, and no key
## existed to say so. `--doxyfile` could name it on one command line, which is precisely the
## shape the mandate calls not-a-declaration: unreachable from the MCP surface, unrecorded, and
## not replayed onto a later build.
##
## IT DOES NOT CHOOSE WHAT IS INDEXED. Since gh#333 a Doxyfile's `INPUT`, `EXCLUDE*` and
## `FILE_PATTERNS` are all replaced — honouring them punished a repo for documenting itself, and
## mbedtls's own file sets `FILE_PATTERNS = *.h` and `INPUT = ../include`, which indexes 1,571
## header declarations and zero of 108 `library/*.c` implementations. What it supplies is
## ALIASES, PREDEFINED and filters, which synthesis cannot reconstruct — and, for gh#420, the
## fact that the repository HAS a documentation target with a scope of its own to report.
SECTION_DOXYFILE = "doxyfile"
## The author-facing TAG NAMES this repo documents its event bus with, as
## `tag: producer|consumer` (`event_edges.DEFAULT_EVENT_TAGS` is the built-in list).
## REPLACES that vocabulary rather than extending it, which is the parameter contract
## it feeds and is also the only fix for a real collision: `raises` is a default
## PRODUCER verb and an EXCEPTION verb nearly everywhere else, so a repo aliasing
## `raises=@xrefitem exceptions ...` has its exception documentation read as event
## production until it can say the whole vocabulary itself.
SECTION_EVENT_TAGS = "event_tags"


## Every section name this file format accepts. A DOCUMENT-level allow-list, and
## the reason it exists is the reason `dispatch.py::_reject_unknown` exists one
## level down: a singular/plural slip (`shared_key_pattern`, `thread_pattern`,
## `lock`) parses to a perfectly valid YAML mapping that NO consumer reads, so the
## build runs entirely on built-in defaults — while `load_declaration` logs
## "declares shared_key_pattern" and tells the owner their file was honoured.
##
## That is the no-hardcoding mandate's worst case: the tool silently substituting
## its own assumptions for a declaration the author did write, and reporting
## success. Measured on a probe with singular section names: every accessor
## returned None/[] and the log claimed all four sections were read.
##
## `index_scope` is owned by `scope.py` (INDEX_SCOPE_SECTION), which does not
## import this module and is not imported by it. It is repeated here as a literal
## rather than imported to avoid coupling the two, and
## `tests/test_declaration.py` pins the two spellings together so the duplication
## cannot drift — the same trade `vocabulary.py` made for the DDL CHECKs.
KNOWN_SECTIONS = frozenset(
    {
        SECTION_SHARED_KEY,
        SECTION_THREADS,
        SECTION_MQTT,
        SECTION_DATA_MODEL,
        SECTION_REQUIREMENTS,
        SECTION_ENRICH,
        SECTION_LOCKS,
        SECTION_ENTRY_PATTERNS,
        SECTION_TEST_PATHS,
        SECTION_VENDORED,
        SECTION_DISPATCH,
        SECTION_PREPROCESSOR,
        SECTION_KCONFIG,
        SECTION_DOXYFILE,
        SECTION_EVENT_TAGS,
        "index_scope",
    }
)


## @brief Load a repo's `.clew.yaml`, or an empty mapping when it has none.
## @param repo_root Repo root to look in.
## @param guard_config Explicit guard-config path overriding discovery, or None.
## @return The parsed declaration; empty when absent, unreadable, or not a mapping.
##         Raises DeclarationError when the document names an unknown section.
## @version 6
## @req REQ-DDB-CONFIG-001
def load_declaration(
    repo_root: Path | str | None, guard_config: Path | str | None = None
) -> dict[str, Any]:
    """@brief Read the target's declared conventions, discarding their provenance.
    @return Parsed mapping, or {} when there is nothing usable.
    @version 6
    """
    return load_declaration_located(repo_root, guard_config)[0]


## @brief A repo's declaration AND the file it was read from.
## @param repo_root Repo root to look in.
## @param guard_config Explicit guard-config path overriding discovery, or None.
## @return (declaration, source path) — the path is None when nothing was declared.
##         Raises DeclarationError when the document names an unknown section.
## @version 1
## @req REQ-DDB-CONFIG-001
def load_declaration_located(
    repo_root: Path | str | None, guard_config: Path | str | None = None
) -> tuple[dict[str, Any], Path | None]:
    """THE PATH TRAVELS WITH THE DATA (gh#20). A declaration may live in the dedicated
    `.clew.yaml` or in the guard config's `x-` passthrough, and `scope.py` reports
    WHERE it read the index scope from — it used to state `<root>/.clew.yaml`
    unconditionally, naming a file that need not exist. A provenance string that is
    checkable and wrong is worse than none: it sends an owner to edit nothing, which is
    `discover_doxyfile`'s lesson about a wrong answer beating no answer.

    Absent is the norm, not an error: most repos declare nothing and run
    entirely on built-in defaults. An unreadable or malformed file is reported
    at WARNING and treated as absent, so a broken file degrades to defaults rather
    than failing a build that would otherwise succeed.

    An UNKNOWN SECTION NAME is treated differently, and the distinction is
    deliberate. Unparseable YAML is an accident with nothing recoverable in it. A
    misspelled section is a document that parses, where the author plainly
    intended something — and degrading there means running on built-in defaults
    while reporting that the declaration was read. So this REFUSES, matching
    `dispatch.py::_reject_unknown`, which closed exactly this failure mode one
    level down and whose lesson was that entry-level slips are worse than
    document-level ones because they are quieter.

    @brief Read the target's declared conventions and their source file.
    @return (parsed mapping, source path) — ({}, None) when there is nothing usable.
    @version 1
    """
    if repo_root is None:
        return {}, None
    root = Path(repo_root).expanduser()
    path = root / DECLARATION_NAME
    data = _read_mapping(path) if path.is_file() else {}
    if not data:
        ## THE PASSTHROUGH. doxygen-guard reserves the `x-` prefix for consumers
        ## (`config --schema` reports `passthrough_prefix: "x-"`, contract_version 2) and
        ## `load_config` preserves such keys verbatim. So a target repo can declare
        ## everything in the ONE config file it already maintains for the gate, instead of
        ## carrying a second file that exists only for this tool.
        ##
        ## Read only when there is no `.clew.yaml`, so a repo that has both gets
        ## the dedicated file — the more specific declaration wins, matching every other
        ## precedence rule here (CLI flag > declaration > guard > Doxyfile).
        ## The path travels back with the data because it is what the unknown-section
        ## refusal below NAMES. It used to be re-derived as `root / GUARD_CONFIG_NAME`,
        ## which was correct only while discovery could not look anywhere else; with a
        ## config in `conf/` that literal would have blamed a file that does not exist.
        data, path = _passthrough_declaration(root, guard_config)
    if data:
        unknown = sorted(str(key) for key in data if key not in KNOWN_SECTIONS)
        if unknown:
            raise DeclarationError(
                f"{path}: unknown section(s) {', '.join(repr(k) for k in unknown)} "
                f"— allowed: {', '.join(sorted(KNOWN_SECTIONS))}. Nothing reads an "
                f"unknown section, so the build would have used built-in defaults "
                f"while reporting that your declaration was honoured."
            )
        logger.info("declaration: %s declares %s", path, ", ".join(sorted(data)))
    return data, (path if data else None)


## @brief Parse a YAML file expected to hold a mapping.
## @param path File to read.
## @return The mapping, or {} when unreadable, malformed, or not a mapping.
## @version 1
## @dg_internal
def _read_mapping(path: Path) -> dict[str, Any]:
    """@brief Read a YAML mapping, warning and degrading to {} on any problem."""
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("%s is unreadable (%s) — ignoring it, using defaults", path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("%s does not contain a mapping — ignoring it, using defaults", path)
        return {}
    return data


## @brief Identify a STATED declaration document for the build record.
## @param raw The document's bytes exactly as read from disk.
## @param document The parsed mapping (already validated by the caller).
## @return build_meta values for the `declaration.` section — never a path.
## @version 1
## @req REQ-DDB-CONFIG-001
def stated_document_meta(raw: bytes, document: dict[str, Any]) -> dict[str, str]:
    """WHAT WAS STATED, recorded so a later reader can check it was applied.

    `options.*` records which TIER won for each option and cannot answer this question.
    Only a tier-1 statement replays onto a later build, so a section added to a stated
    document AFTER the build that last stated it never lands — while the sections that
    did still report `explicit`. Measured on the mbedtls acceptance target: one document
    declaring `locks`, `vendored` and `preprocessor` produced an index with
    `options.locks.tier=explicit`, `options.predefined.tier=heuristic` and no vendored
    row at all, and every reader reported health. It invalidated a graded run.

    CONTENT-ADDRESSED, WITH NO SECTION-TO-EVIDENCE MAP. The sha identifies the document
    and the section list names its top-level keys, so a checker compares the file it holds
    against the build without knowing that `preprocessor:` lands as `options.predefined.*`
    or that `vendored:` leaves no `options.*` row. Such a map would be a second vocabulary
    free to drift as sections are added, and the section it forgot would be the silent one.

    NO PATH IS RECORDED. A stated document lives in the CONSUMER'S tree, not the target's,
    so storing its path would publish the builder's machine layout through every MCP reply —
    the disclosure that forced the build-version-9 bump. A sha plus a section list
    identifies the document exactly and says nothing about where it sat.

    @brief build_meta identification of a stated declaration document.
    @return {stated_sha256, stated_sections} — sections empty-string-free.
    @version 1
    """
    import hashlib

    ## SORTED, so two spellings of one document produce one row. `build_meta` is compared
    ## verbatim by the determinism test, and a YAML parser's key order is whatever the file
    ## happened to use — the same reason `tiers.DOCUMENT_SEPARATORS` canonicalises.
    sections = SECTION_SEPARATOR.join(sorted(str(key) for key in document))
    return {
        "stated_sha256": hashlib.sha256(raw).hexdigest(),
        ## An EMPTY document states nothing, and the falsy-drop rule in `write_build_signature`
        ## then writes no section row — which is correct rather than lossy: `--declare` on an
        ## empty file is the withdrawal spelling, so "nothing was stated" and "no document was
        ## given" genuinely are the same build. The sha still records that a file was read.
        "stated_sections": sections,
    }


## @brief One declaration section, as a mapping.
## @param declaration Parsed declaration from load_declaration.
## @param section Section name (e.g. SECTION_SHARED_KEY).
## @return The section mapping, or None when absent or not a mapping.
## @version 2
## @req REQ-DDB-CONFIG-001
def section(declaration: dict[str, Any], name: str) -> dict[str, Any] | None:
    """@brief Return a mapping-valued section, or None."""
    value = declaration.get(name)
    return value if isinstance(value, dict) else None


## @brief A declaration section holding a list of strings.
## @param declaration Parsed declaration from load_declaration.
## @param name Section name (e.g. SECTION_ENTRY_PATTERNS).
## @return The declared strings, or [] when the section is absent or malformed.
## @version 1
## @req REQ-DDB-CONFIG-001
def string_list(declaration: dict[str, Any], name: str) -> list[str]:
    """Some sections are a flat list rather than a mapping — reachability entry
    patterns, for instance. A non-list value is ignored with a warning rather
    than coerced, so a malformed section degrades to "declared nothing" instead
    of silently seeding something unintended.

    @brief Read a list-valued declaration section.
    @return List of declared strings.
    @version 1
    """
    value = declaration.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        logger.warning("declaration: %s must be a list — ignoring it", name)
        return []
    return [str(v) for v in value if str(v)]


## @brief The declared event-tag vocabulary, role-validated.
## @param declaration Parsed declaration from load_declaration.
## @return Lower-cased tag name → PRODUCER/CONSUMER, or None to keep the built-in
##         vocabulary. Raises DeclarationError when a role is neither of those two.
## @version 1
## @req REQ-DDB-CONFIG-001
def declared_event_tags(declaration: dict[str, Any]) -> dict[str, str] | None:
    """REPLACE, never merge — see SECTION_EVENT_TAGS on the `raises` collision that
    makes replacing the only available fix. None (not `{}`) is what "undeclared"
    returns, because the importer's parameter distinguishes the two and `None` is
    its "use the defaults" value; an empty or non-mapping section is undeclared.

    AN UNRECOGNISED ROLE IS REFUSED, matching `dispatch.py::_reject_unknown` and the
    unknown-section refusal above. Degrading a misspelled `producers:` to a default
    would silently file an emitter as a handler, and a reversed edge is worse than a
    missing one: `chain_trace` would report causality flowing the wrong way with the
    `declared=1`, `confidence='high'` grading these edges carry precisely because an
    author asserted them.

    The two roles are validated against `event_edges`' own constants rather than a
    `vocabulary.py` entry: they never reach the database as a value — the role
    chooses which COLUMN a rowid lands in (`writer_rowid` vs `reader_rowid`) — so
    there is no DDL CHECK for `vocabulary.py` to be the source of.

    @brief Read and validate the repo's declared event-tag vocabulary.
    @return Tag → role mapping, or None when nothing usable is declared.
    @version 1
    """
    declared = section(declaration, SECTION_EVENT_TAGS)
    if not declared:
        return None
    vocabulary: dict[str, str] = {}
    for tag, role in declared.items():
        normalised = str(role).strip().lower()
        if normalised not in (PRODUCER, CONSUMER):
            raise DeclarationError(
                f"{SECTION_EVENT_TAGS}: tag {str(tag)!r} declares role {role!r} "
                f"— allowed: {PRODUCER}, {CONSUMER}"
            )
        vocabulary[str(tag).strip().lower()] = normalised
    return vocabulary


## @brief Resolve a repo-relative path declared in a section.
## @param declaration Parsed declaration.
## @param name Section name holding a path string.
## @param repo_root Root the declared path is relative to.
## @return Absolute path, or None when undeclared or missing on disk.
## @version 2
## @req REQ-DDB-CONFIG-001
def declared_path(
    declaration: dict[str, Any], name: str, repo_root: Path | str | None
) -> Path | None:
    """For manifests that are not YAML (the ingot data-model TOML), the section
    names a file instead of inlining it. Resolved relative to the repo so the
    declaration stays portable, and a declared-but-missing file warns rather
    than failing the build.

    @brief Resolve a declared repo-relative manifest path.
    @return Absolute path, or None.
    @version 2
    """
    value = declaration.get(name)
    if not isinstance(value, str) or repo_root is None:
        return None
    path = (Path(repo_root).expanduser() / value).resolve()
    if not path.is_file():
        logger.warning("declaration: %s names %s, which does not exist — ignoring", name, path)
        return None
    return path


## @brief The `x-clew` section of a repo's .doxygen-guard.yaml, if present.
## @param repo_root Repo root to look in.
## @param guard_config Explicit guard-config path overriding discovery, or None.
## @return (passthrough mapping, the config path it was read from or would have been).
## @version 3
## @dg_internal
def _passthrough_declaration(
    repo_root: Path, guard_config: Path | str | None = None
) -> tuple[dict[str, Any], Path]:
    """Read this tool's config out of the file the repo ALREADY maintains.

    doxygen-guard reserves the `x-` prefix for consumers — `config --schema` reports
    `passthrough_prefix: "x-"` at `contract_version: 2`, and `load_config` preserves such
    keys verbatim rather than rejecting them as unknown. Verified live before this was
    written, not taken from the schema alone.

    WHY THIS EXISTS. The alternative shapes were all rejected on their own merits:
    args-only cannot work because the MCP server has no argv (that hole is exactly what
    `.clew.yaml` was created to close); a second checked-in file is maintenance the
    owner does not want; a file under our state directory is invisible, which is worse than
    maintained. A repo that runs the gate already maintains `.doxygen-guard.yaml`, so
    declaring here is the only option that adds no new artifact.

    The prefix is read from `doxygen_guard.config.PASSTHROUGH_PREFIX` rather than
    hardcoded, so if upstream changes it this follows — the same no-hardcoding rule applied
    to the mechanism that exists to carry our declarations.

    Degrades to {} when the guard config is absent or unreadable. Unknown SECTIONS inside
    the passthrough are still refused by the caller, because a misspelling is as quiet here
    as it is in the dedicated file.

    THE PATH IS DISCOVERED, not assumed to be at the root (gh#16). While it was
    `repo_root / GUARD_CONFIG_NAME`, a target that keeps its config in `conf/` and says
    so in its pre-commit hook's args had NO passthrough at all — so every section this
    mechanism exists to carry (`index_scope` among them) was unreachable for it, on both
    entry points, with no way to say otherwise. That is why the fix is discovery rather
    than a new flag: the MCP server passes no flags.

    THE LOAD IS PERMISSIVE (gh#32): a target pinning a different doxygen-guard release
    keeps its passthrough instead of losing the whole document to one key we never read.

    @brief Read the `x-<tool>` passthrough section from the discovered guard config.
    @return (declared mapping or {}, the config path).
    @version 3
    """
    location = discover_guard_config(repo_root, guard_config)
    path = location.path or (repo_root / GUARD_CONFIG_NAME)
    if location.path is None or not path.is_file():
        return {}, path
    cfg, prefix = _guard_config_and_prefix(path, repo_root)
    section_key = f"{prefix}{PASSTHROUGH_TOOL}"
    data = cfg.get(section_key)
    if not isinstance(data, dict) or not data:
        return {}, path
    logger.info(
        "declaration: reading %r from %s (found via %s)", section_key, path, location.source
    )
    return data, path


## @brief A parsed guard config and the passthrough prefix it reserves.
## @param path Path to the repo's .doxygen-guard.yaml.
## @param repo_root Repo root, so a version skew can name the rev the target pins.
## @return (config mapping, prefix); ({}, 'x-') when the config is unusable.
## @version 3
## @dg_internal
def _guard_config_and_prefix(
    path: Path, repo_root: Path | str | None = None
) -> tuple[dict[str, Any], str]:
    """Split out to keep `_passthrough_declaration` inside the max-3-returns standard.

    The prefix comes from `doxygen_guard.config.PASSTHROUGH_PREFIX` rather than a literal,
    so if upstream moves it this follows — the no-hardcoding rule applied to the very
    mechanism that carries our declarations. The `'x-'` fallback covers a guard old enough
    not to export it.

    A broken guard config degrades to `({}, 'x-')` rather than raising: the gate will
    already have told the owner their config is invalid, and failing the INDEX for it as
    well would take a doxygen run with it.

    THE LOAD IS PERMISSIVE (gh#32) and shared with `requirements.load_guard_config`. It
    was `dg_config.load_config` here, so a target pinning an older doxygen-guard than we
    import lost its ENTIRE passthrough — every section this mechanism exists to carry —
    over one key we never read. A target's pin and ours are independent decisions, so
    that is the normal case at scale, not an authoring error.

    @brief Load the guard config and its passthrough prefix, tolerating skew and failure.
    @return (config, prefix).
    @version 3
    """
    from .guardconfig import read_guard_config

    try:
        from doxygen_guard import config as dg_config

        prefix = str(getattr(dg_config, "PASSTHROUGH_PREFIX", "x-"))
    except Exception as exc:
        logger.warning("declaration: %s is unusable (%s) — no passthrough read", path, exc)
        return {}, "x-"
    return read_guard_config(path, repo_root).config, prefix
