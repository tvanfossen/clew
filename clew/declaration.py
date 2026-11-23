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
from .guard.config import CONFIG_FILE_NAME, CONFIG_SECTION, LEGACY_CONFIG_NAME
from .vocabulary import DeclarationError

## The conventional filename. clew's OWN interface — not an assumption about any target's
## layout. One file for the index's declaration AND the gate's config: the gate reads its
## `guard:` section, and owns the name, so the two can never disagree about it.
DECLARATION_NAME = CONFIG_FILE_NAME

## The gate's section of the file (clew/guard/config.py). NOT a declaration section, so it is
## not in KNOWN_SECTIONS (whose every member is a build option too): the loader accepts it and
## drops it, because nothing on the index side reads it as a declaration. The index reads the
## gate's values through `guardconfig.read_guard_config`, with the gate's schema.
SECTION_GUARD = CONFIG_SECTION
## `clew wiki`'s section (1.4.0). NOT a declaration section either, for the same reason as
## `guard:` — the wiki generator reads it (`clew.wiki.config`), no build stage does — so the loader
## accepts it and drops it.
SECTION_WIKI = "wiki"
## The top-level keys the loader accepts and drops: other tools' sections in the shared file.
NON_DECLARATION_SECTIONS = frozenset({SECTION_GUARD, SECTION_WIKI})

## How `stated_document_meta` joins the section names. A COMMA-SPACE, matching `scope.py`'s
## separator rather than `tiers.py`'s newline, and safe here for the reason `tiers` is not:
## these are section names drawn from `KNOWN_SECTIONS`, every one of which is a bare
## lowercase identifier, so no value can contain the separator.
SECTION_SEPARATOR = ", "

## Scope a repository states for its OWN named sub-indexes (gh#39). Keyed by the derived
## sub-index name, so a parent can trim a vendored tree it does not own — the case a
## `.clew.yaml` inside that tree cannot serve, because declaration discovery is rooted at the
## parent and the tree belongs to somebody else.
SECTION_SUB_INDEXES = "sub_indexes"

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
##
## 2.0.0 (R5-CFG F7): `requirements:` is the CATALOG SECTION the index, the gate and the wiki all
## read — `{file, format, id_column, name_column, status_field, exempt_status, version_field,
## external, needs}`, or one path as the short form of `{file: <path>}`. It still never inlines
## the catalog itself, for the reason above. Its keys are validated by the gate's reader
## (`guard.config.REQUIREMENTS_SCHEMA`), so the two cannot disagree about what is allowed.
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
##
## 2.0.0 (R5-CFG F20): WHERE TESTS LIVE AND WHAT THEIR RUNS LEAVE ARE ONE SECTION, `tests:`. The
## paths were `test_paths:` (index) and again `wiki.tests.layers` (site), and the evidence a run
## leaves — JUnit, coverage, per-test contexts — describes the repository's tests yet only the
## wiki could read it. `tests.paths` is what `test_paths` was; `test_paths` is refused naming it.
SECTION_TESTS = "tests"
TESTS_PATHS = "paths"
TESTS_MACROS = "macros"
TESTS_FUNCTION_PREFIXES = "function_prefixes"
## The macro shapes `tests.macros` may name, as `wiki.frameworks` reads them.
TESTS_MACRO_SHAPES = frozenset({"named", "suite", "bare"})
## Every key `tests:` may carry: `paths` for the index, and the evidence inputs the wiki reads.
TESTS_KEYS = frozenset(
    {
        TESTS_PATHS,
        "junit",
        "coverage",
        "target_only",
        "mutations",
        "results",
        "gcov",
        "mapping",
        "features",
        "layers",
        "min_layers",
        "evidence_fields",
        "infer_depth",
        "contexts",
        "traces",
        ## R5-CFG C9 (2.0.0): the size cap on one report, in MiB (per-test LCOV grows with tests).
        "max_report_mb",
        ## P4 (2.0.0; C6, W2): test shapes beyond the built-ins, ADDED to them —
        ## `macros: {named|suite|bare: [MACRO, ...]}` and `function_prefixes: [prefix, ...]`.
        TESTS_MACROS,
        TESTS_FUNCTION_PREFIXES,
    }
)
## The 1.x name, kept only so the refusal can name where it went.
SECTION_TEST_PATHS = "test_paths"
## WHO OWNS A FILE (S2/S3, 2.0.0): the repository's own CODEOWNERS and MAINTAINERS, found at their
## conventional locations; this section only names them when they live elsewhere
## (`{codeowners: path, maintainers: path}`). Read by `clew/owners.py` into the `owners` layer.
SECTION_OWNERS = "owners"
## THE BLOCKING VOCABULARY (R5-CORE C1, 2.0.0): a repository's own blocking primitives
## (`{name, timeout_arg_index}`), ISR predicates and wait tokens (`{none, forever,
## bounded_prefixes}`), ADDED to the built-in Zephyr / FreeRTOS / RIOT / POSIX facts. Every
## sibling layer (locks, threads, shared keys) was declarable and this one was the exception.
SECTION_BLOCKING = "blocking"
## Sections that moved in 2.0.0, refused naming their new home (never as "unknown").
MOVED_SECTIONS = {SECTION_TEST_PATHS: f"`{SECTION_TESTS}.{TESTS_PATHS}`"}
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
        SECTION_TESTS,
        SECTION_OWNERS,
        SECTION_BLOCKING,
        SECTION_VENDORED,
        SECTION_DISPATCH,
        SECTION_PREPROCESSOR,
        SECTION_KCONFIG,
        SECTION_DOXYFILE,
        SECTION_EVENT_TAGS,
        "index_scope",
        SECTION_SUB_INDEXES,
    }
)

## Every top-level key `.clew.yaml` may carry: the declaration sections plus the gate's.
ACCEPTED_SECTIONS = KNOWN_SECTIONS | NON_DECLARATION_SECTIONS

## THE SHAPE OF EACH SECTION, ENFORCED BY THE LOADER (R5-CFG F1/F4/F5/F26, 2.0.0). Every section
## is one of four shapes, and a value of the wrong shape is REFUSED here rather than handed to a
## reader that would drop it (`section()` returns mapping-or-None, so a path string under
## `thread_patterns:` was ignored), iterate it (`vendored: extern` became `e, x, t, e, r, n`), or
## warn and ignore it — a warning is gone by the time anyone reads the index.
##
## A LIST section accepts one bare string as a one-item list, the precedent `wiki` already sets
## for `gcov` and `theme.css`; anything else that is not a list is refused.
LIST_SECTIONS = frozenset({SECTION_ENTRY_PATTERNS, SECTION_VENDORED})

## A PATH section names one repo-relative file.
PATH_SECTIONS = frozenset({SECTION_DATA_MODEL, SECTION_ENRICH, SECTION_DOXYFILE})

## A MANIFEST section is its document inline; its entries are checked against
## `buildoptions.MANIFEST_SCHEMAS`, the same schemas tier 1 is checked against.
MANIFEST_SECTIONS = frozenset(
    {SECTION_SHARED_KEY, SECTION_THREADS, SECTION_MQTT, SECTION_LOCKS, SECTION_DISPATCH}
)

## The keys a SECTION-DOCUMENT section may carry, where this loader is the only check. Restated
## rather than imported so this module stays free of its readers' imports;
## `tests/test_declaration_validated.py` pins each set to the reader's own constants.
## `index_scope` and `sub_indexes` are absent on purpose: `scope.py` already refuses their
## unknown keys by name (the model this follows).
SECTION_KEYS: dict[str, frozenset[str]] = {
    SECTION_PREPROCESSOR: frozenset({"predefined", "config_header"}),
    SECTION_KCONFIG: frozenset({"root"}),
    SECTION_TESTS: TESTS_KEYS,
    SECTION_OWNERS: frozenset({"codeowners", "maintainers"}),
    SECTION_BLOCKING: frozenset({"primitives", "isr_predicates", "wait_tokens"}),
}

## THE ESCAPE HATCH AN OLDER CLEW NEEDS (B5, 1.1.0 merge review). `guard:` is new in 1.1.0,
## so a `.clew.yaml` written for it is REFUSED outright by clew <= 1.0.39, which cannot know
## the name. Nothing shipped now can change what an already-released version does — but a
## section carrying this prefix is tolerated and ignored from here on, so the NEXT
## experimental key is a no-op on an older clew instead of a hard refusal that bricks its
## build. The prefix is the convention HTTP headers, YAML tooling and TOML tables all use for
## exactly this, so it needs no clew-specific documentation to be recognised.
##
## TOLERATED, NOT SILENT: the section is named at WARNING. `x-thread_patterns` is
## indistinguishable from a typo that happens to carry the prefix, and a quiet default is the
## failure mode the refusal below exists to prevent.
EXPERIMENTAL_PREFIX = "x-"


## @brief Load a repo's `.clew.yaml`, or an empty mapping when it has none.
## @param repo_root Repo root to look in.
## @return The parsed declaration; empty when absent, unreadable, or not a mapping.
##         Raises DeclarationError when the document names an unknown section.
## @version 7
## @req REQ-DDB-CONFIG-001
def load_declaration(repo_root: Path | str | None) -> dict[str, Any]:
    """@brief Read the target's declared conventions, discarding their provenance.
    @return Parsed mapping, or {} when there is nothing usable.
    @version 7
    """
    return load_declaration_located(repo_root)[0]


## @brief A repo's declaration AND the file it was read from.
## @param repo_root Repo root to look in.
## @return (declaration, source path) — the path is None when nothing was declared.
##         Raises DeclarationError when the document names an unknown section.
## v5 (1.4.0): the `wiki:` section is accepted and dropped, like `guard:`.
## v6 (2.0.0): every section's shape is checked (`_checked_sections`); manifest sections share
## tier 1's MANIFEST_SCHEMAS, so the in-tree file is no longer the least validated route.
## v7: a moved section is refused naming its new home (2.0.0)
## v8: hard cut of doxygen-guard priors (2.0.0, PG4)
## @version 8
## @req REQ-DDB-CONFIG-001
def load_declaration_located(
    repo_root: Path | str | None,
) -> tuple[dict[str, Any], Path | None]:
    """THE PATH TRAVELS WITH THE DATA (gh#20): `scope.py` reports WHERE it read the
    index scope from, and None when nothing was declared, rather than naming a file
    that need not exist.

    The `guard:` section is the gate's and is dropped from the result, so a file that
    configures only the gate declares nothing to the index.

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
    @version 3
    """
    if repo_root is None:
        return {}, None
    root = Path(repo_root).expanduser()
    path = root / DECLARATION_NAME
    data = _read_mapping(path) if path.is_file() else {}
    if data:
        experimental = sorted(str(key) for key in data if str(key).startswith(EXPERIMENTAL_PREFIX))
        if experimental:
            logger.warning(
                "declaration: %s carries experimental section(s) %s — tolerated and IGNORED, "
                "so nothing in them reaches this build. A misspelled section that happens to "
                "carry the `%s` prefix looks exactly like this.",
                path,
                ", ".join(experimental),
                EXPERIMENTAL_PREFIX,
            )
        moved = sorted(str(key) for key in data if key in MOVED_SECTIONS)
        if moved:
            raise DeclarationError(
                f"{path}: "
                + "; ".join(f"`{k}` moved in 2.0.0 to {MOVED_SECTIONS[k]}" for k in moved)
            )
        unknown = sorted(
            str(key)
            for key in data
            if key not in ACCEPTED_SECTIONS and not str(key).startswith(EXPERIMENTAL_PREFIX)
        )
        if unknown:
            raise DeclarationError(
                f"{path}: unknown section(s) {', '.join(repr(k) for k in unknown)} "
                f"— allowed: {', '.join(sorted(ACCEPTED_SECTIONS))}. Nothing reads an "
                f"unknown section, so the build would have used built-in defaults "
                f"while reporting that your declaration was honoured. If this file was "
                f"written for a newer clew than the one reading it — `guard:` is new in "
                f"1.1.0 — upgrade with `pip install -U clew-trace` and bump the `rev:` in "
                f"`.pre-commit-config.yaml` to match."
            )
        data = {
            key: value
            for key, value in data.items()
            if key not in NON_DECLARATION_SECTIONS and not str(key).startswith(EXPERIMENTAL_PREFIX)
        }
    ## BOTH SIDES OF THE DROPPED TOOL (group B, 1.1.0 merge review). The INDEX reads the
    ## gate's section too — the `@req` id pattern and the requirements catalog come from
    ## `guard:` — so a repository still carrying an inert `.doxygen-guard.yaml` has its
    ## requirement links defaulted in the graph for the same reason its gate stopped
    ## enforcing them. An owner who only runs `clew index` would otherwise never be told.
    ##
    ## The GATE'S OWN helper, not a copy: this module already imports the gate's config for
    ## the section name, and two descriptions of one migration is how they drift.
    ## 2.0.0 (PG4): the GATE refuses to run while a doxygen-guard leftover exists; the INDEX only
    ## says so, because clew indexes repositories it must not change (third-party trees included).
    if (path.parent / LEGACY_CONFIG_NAME).is_file():
        logger.warning(
            "%s is a doxygen-guard config: clew does not read it, and `clew guard` refuses to run "
            "while it exists. Move its contents under `guard:` in %s and delete it.",
            path.parent / LEGACY_CONFIG_NAME,
            path.name,
        )
    if data:
        data = _checked_sections(data, path)
        logger.info("declaration: %s declares %s", path, ", ".join(sorted(data)))
    return data, (path if data else None)


## @brief Check every declared section's shape, normalising a one-string list section.
## @param data The declaration, unknown sections already refused.
## @param path The file it was read from, for the message.
## @return The declaration with list sections as lists; raises DeclarationError on a wrong shape.
## @version 1
## @utility
def _checked_sections(data: dict[str, Any], path: Path) -> dict[str, Any]:
    """ONE VALIDATOR FOR BOTH ROUTES (R5-CFG F1): manifest sections go through
    `buildoptions.check_manifest_document`, the check tier 1 already had, so a key refused from
    `--declare` is refused from the checked-in file too.

    @brief Validate section shapes.
    @return Normalised declaration.
    @version 1
    """
    out = dict(data)
    for name, value in data.items():
        out[name] = _checked_section(name, value, path)
    return out


## @brief Check one section's shape.
## @param name Section name.
## @param value Its declared value.
## @param path The file it was read from.
## @return The (possibly normalised) value; raises DeclarationError on a wrong shape.
## v2: requirements: is checked against the gate's schema (2.0.0, R5-CFG F7)
## v3: tests.paths is a list section (2.0.0, R5-CFG F20)
## v4: tests.macros and tests.function_prefixes are checked too (2.0.0, P4)
## @version 4
## @utility
def _checked_section(name: str, value: Any, path: Path) -> Any:
    """@brief Refuse a wrong-shaped section, naming it and the expected shape.
    @return The checked value.
    @version 1
    """
    from .buildoptions import BuildOptionError, check_manifest_document

    if name in LIST_SECTIONS:
        return _checked_list_section(name, value, path)
    if name == SECTION_REQUIREMENTS:
        return _checked_requirements(value, path)
    if name == SECTION_TESTS and isinstance(value, dict):
        value = _checked_tests(value, path)
    if name in PATH_SECTIONS:
        if not isinstance(value, str) or not value.strip():
            raise DeclarationError(
                f"{path}: {name} must be one repo-relative path, got {type(value).__name__}"
            )
        return value
    if not isinstance(value, dict):
        raise DeclarationError(
            f"{path}: {name} must be a mapping (the document inline), got "
            f"{type(value).__name__}. Nothing reads a {type(value).__name__} here, so the build "
            f"would have used built-in defaults while reporting the section declared."
        )
    if name in MANIFEST_SECTIONS:
        try:
            return check_manifest_document(name, value)
        except BuildOptionError as exc:
            raise DeclarationError(f"{path}: {exc}") from exc
    _check_section_keys(name, value, path)
    return value


## @brief Check the list-shaped keys of `tests:`.
## @param value The section.
## @param path Source file.
## @return The section, checked.
## @version 1
## @utility
def _checked_tests(value: dict[str, Any], path: Path) -> dict[str, Any]:
    """`paths` and `function_prefixes` are lists; `macros` maps a SHAPE (`named` / `suite` /
    `bare`) to a list. An unknown shape is refused by name: it would read as no macros at all.

    @brief Check tests: lists and shapes.
    @return The section.
    """
    out = dict(value)
    for key in (TESTS_PATHS, TESTS_FUNCTION_PREFIXES):
        if key in out:
            out[key] = _checked_list_section(f"{SECTION_TESTS}.{key}", out[key], path)
    macros = out.get(TESTS_MACROS)
    if macros is not None:
        if not isinstance(macros, dict) or set(macros) - TESTS_MACRO_SHAPES:
            raise DeclarationError(
                f"{path}: tests.macros must map a shape ({', '.join(sorted(TESTS_MACRO_SHAPES))}) to a "
                f"list of macro names, got {macros!r}"
            )
        out[TESTS_MACROS] = {
            shape: _checked_list_section(f"tests.macros.{shape}", names, path)
            for shape, names in macros.items()
        }
    return out


## @brief Check the catalog section against the gate's own schema.
## @param value Declared value: a path, or the catalog mapping.
## @param path Source file.
## @return The section as a mapping; raises DeclarationError on an unknown key or wrong type.
## @version 1
## @utility
def _checked_requirements(value: Any, path: Path) -> dict[str, Any]:
    """@brief Validate `requirements:` with REQUIREMENTS_SCHEMA. @return Mapping."""
    from .guard.config import REQUIREMENTS_SCHEMA, _validate_node

    section = {"file": value} if isinstance(value, str) else value
    if not isinstance(section, dict):
        raise DeclarationError(
            f"{path}: {SECTION_REQUIREMENTS} must be one path or the catalog mapping, got "
            f"{type(value).__name__}"
        )
    errors = _validate_node(section, REQUIREMENTS_SCHEMA, SECTION_REQUIREMENTS)
    if errors:
        raise DeclarationError(f"{path}: {'; '.join(errors)}")
    return dict(section)


## @brief Read a list section, accepting one bare string as a one-item list.
## @param name Section name.
## @param value Declared value.
## @param path Source file.
## @return The list of strings; raises DeclarationError for any other type.
## @version 1
## @utility
def _checked_list_section(name: str, value: Any, path: Path) -> list[str]:
    """@brief Normalise a list section. @return Strings."""
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(v, (str, int, float)) for v in value):
        raise DeclarationError(
            f"{path}: {name} must be a list of strings (or one string), got {type(value).__name__}"
        )
    return [str(v) for v in value]


## @brief Refuse a key a section-document section's reader never reads.
## @param name Section name.
## @param value Section mapping.
## @param path Source file.
## @return None; raises DeclarationError naming the unknown key(s).
## @version 1
## @utility
def _check_section_keys(name: str, value: dict[str, Any], path: Path) -> None:
    """R5-CFG F4: `preprocessor: {predefine: [FOO]}` recorded a DECLARED configuration with no
    macros, and `kconfig: {path: ...}` (once the documented spelling) was ignored in favour of the
    root Kconfig by convention.

    @brief Allow-list a section document's keys.
    """
    allowed = SECTION_KEYS.get(name)
    if allowed is None:
        return
    unknown = sorted(str(k) for k in value if k not in allowed)
    if unknown:
        raise DeclarationError(
            f"{path}: {name} names unknown key(s) {', '.join(repr(k) for k in unknown)} — "
            f"allowed: {', '.join(sorted(allowed))}. A misspelled key reads as an absent one, so "
            f"it would silently take its default."
        )


## @brief Parse a YAML file expected to hold a mapping.
## @param path File to read.
## @return The mapping, or {} when unreadable, malformed, empty, or not a mapping.
## @version 2
## @utility
def _read_mapping(path: Path) -> dict[str, Any]:
    """AN EMPTY OR COMMENT-ONLY FILE IS NOT MALFORMED (gh#48). It is exactly what
    `propose_declaration` hands an owner — a draft written entirely as comments so that committing
    it changes nothing — and it used to log "does not contain a mapping — ignoring it", a WARNING
    that reads as a broken file and sent a reporter looking for damage that was not there. It
    states nothing, so the defaults apply, and that is said at INFO in those words.

    @brief Read a YAML mapping, degrading to {} with a message that names the actual state.
    @return The mapping, or {}.
    @version 2
    """
    data, problem = _parsed_declaration(path)
    if problem is not None:
        logger.warning("%s %s — ignoring it, using built-in defaults", path, problem)
    elif not data:
        logger.info(
            "%s states nothing (it is empty or comments only) — built-in defaults apply", path
        )
    return data


## @brief Parse a declaration file into (mapping, problem).
## @param path File to read.
## @return The mapping ({} when empty), and a phrase naming why it is unusable, or None.
## @version 1
## @utility
def _parsed_declaration(path: Path) -> tuple[dict[str, Any], str | None]:
    """ONE PARSE FOR THE BUILD AND FOR THE MESSAGES that describe it, so a refusal saying
    "comments only" and a build honouring nothing cannot disagree about the same file.

    @brief Parse a declaration file, classifying why it holds nothing.
    @return (mapping, problem phrase or None).
    @version 1
    """
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return {}, f"is unreadable ({exc})"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return {}, f"holds a {type(data).__name__}, not a mapping of sections"
    return data, None


## @brief One sentence on a repository's `.clew.yaml` and whether a build honours it.
## @param repo_root The repository root.
## @return The sentence, or "" when the repository has no `.clew.yaml`.
## v3 (1.4.0): ignores the `wiki:` section as it does `guard:`.
## @version 3
## @req REQ-DDB-CONFIG-001
def describe_declaration(repo_root: Path) -> str:
    """gh#48 ASK 4. A reporter's split repository carried a `.clew.yaml` that was comments only, so
    its guidance reached neither clew nor the agent — and nothing on the tool surface said so. A
    refusal about that repository now names the file and whether it was honoured, which is where an
    owner would go to change the behaviour being refused.

    SILENT WHEN THE FILE IS ABSENT, which is the common case and not news: most repositories declare
    nothing, and a sentence saying so on every refusal is a sentence nobody reads.

    @brief Describe a repository's declaration file for a message.
    @return The sentence, or "".
    @version 2
    """
    path = Path(repo_root) / DECLARATION_NAME
    if not path.is_file():
        return ""
    data, problem = _parsed_declaration(path)
    if problem is not None:
        return f"Its {DECLARATION_NAME} {problem}, so it is ignored and built-in defaults apply."
    if not data:
        return (
            f"Its {DECLARATION_NAME} holds only comments, so it states nothing and built-in "
            f"defaults apply — uncomment a section to have builds honour it."
        )
    sections = ", ".join(sorted(str(k) for k in data if k not in NON_DECLARATION_SECTIONS))
    if not sections:
        return (
            f"Its {DECLARATION_NAME} configures only the gate (`{SECTION_GUARD}:`), so builds "
            f"run on built-in defaults."
        )
    return f"Its {DECLARATION_NAME} declares {sections}, which every build honours."


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
