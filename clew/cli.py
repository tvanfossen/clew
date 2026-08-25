# SPDX-License-Identifier: MIT
"""argparse + pipeline glue for `python -m clew`.

The pipeline runs in fixed order:
  1. doxygen → SQLite + XML
  2. copy_database to the user-specified --output path
  3. enrich_database (optional, --enrich)
  4. fix_doxygen_paths (STRIP_FROM_PATH undo)
  5. ingest_supplementary_docs (README + docs/*.md → FTS5)
  5a1. import_kconfig (gh#18: the CONFIGURATION SPACE — kconfig_symbols +
      kconfig_choices, and every prompt/help block into the SAME FTS5 table.
      IMMEDIATELY AFTER step 5 and never before: step 5 DROPs and recreates
      supplementary_docs, so running above it inserts these chunks and then
      deletes them, with no error anywhere.)
  5a2. import_kconfig_gates (gh#18 part 3: kconfig_gates — which source lines a
      CONFIG symbol gates. Independent of 5a1 on purpose; a gate on a symbol no
      Kconfig declares is a finding, not noise to filter.)
  5b. recover_ast_symbols (gh#11: memberdef rows for the C/C++ function definitions
      doxygen did not emit, stamped dg_source='ast'. ABOVE every call-edge layer —
      they resolve their endpoints to memberdef rowids.)
  5c. report_index_coverage (gh#6: how much of the indexed set yielded symbols,
      overall AND documented-only)
  5d. ingest_file_docs (gh#10: each indexed file's module docstring / file-level
      @file comment into `file_docs` AND the same FTS5 table, so a CONCEPTUAL query
      reaches code named for its mechanics. BELOW 5c and not above it: coverage
      treats a file that yielded prose as not-barren, so running earlier would
      improve the barren ratio without indexing one extra symbol.)
  6. build_call_edges (Layer 1: doxygen sqlite3 inline xrefs)
  7b. import_macro_hop_edges (Layer 1b: caller -> macro definition -> callee)
  8. import_ast_call_edges (Layer 3: tree-sitter, optional)
  9. import_callback_registration_edges (Layer 4: fnptr + external_boundaries)
 9b. extract_locks (R1 lock layers L1 AND L2: locks + lock_acquisitions +
     critical_section_calls; declared `locks:`). L2 rides inside this stage
     rather than getting its own, because critical-section membership is
     derived from the SAME tree-sitter walk that finds the acquisitions — a
     second stage would re-parse every file to rediscover what this one
     already has in hand.
 9c. import_declared_dispatch_edges (Layer 6: declared indirect dispatch —
     interface→implementor edges + interface-boundary termini + fnptr dispatch
     tables; optional --dispatch / `dispatch:`). MUST sit here: it reads the
     completed call-edge layers above and its synthetic edges must exist BEFORE
     the thread-membership and reachability BFS below can flow across the seam.
 10. extract_threads (R1: threads + thread_membership; optional --thread-patterns)
 11. import_shared_key_edges_inferred (Layer 5a: optional --shared-key-patterns,
     merged with the dispatch manifest's `shared_key_wrappers`)
 12. import_shared_key_edges_declared (Layer 5b: optional --data-model)
 13. import_mqtt_dispatch_edges (Layer 5c: optional --mqtt-dispatch)
 13b. import_event_edges (Layer 5d: author-DECLARED @emits/@handles via the
      repo's own xrefitem ALIASES → edge_kind='event')
 14. annotate_thread_boundaries (R1: crosses_thread/to_thread_id on shared_key_edges)
 15. ingest_requirements_yaml (optional --requirements)
 16. import_req_edges (@req doxygen-tag traceability)
 17. import_req_test_edges (test-function coverage subset)
 18. mark_reachability (BFS from entry-point seeds — UNCHANGED, call-edges only)
 19. report_stats (print summary)

@brief CLI + pipeline orchestration.
@version 10
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from ._common import active_console, console, logger
from .ast_symbols import recover_ast_symbols
from .buildoptions import (
    MANIFEST_OPTIONS,
    SECTION_DOCUMENT_OPTIONS,
    BuildOptionError,
    apply_options,
)
from .macro_refs import import_ast_macro_refs
from .call_edges import (
    build_call_edges,
    import_ast_call_edges,
    import_macro_hop_edges,
)
from .callback_edges import import_callback_registration_edges
from .coverage import report_index_coverage
from .external import EXTERNAL_ROOTS_META_KEY, stamp_external_provenance
from .declaration import (
    SECTION_TEST_PATHS,
    SECTION_DATA_MODEL,
    SECTION_DISPATCH,
    SECTION_ENRICH,
    SECTION_ENTRY_PATTERNS,
    SECTION_EVENT_TAGS,
    SECTION_LOCKS,
    SECTION_MQTT,
    SECTION_PREPROCESSOR,
    SECTION_REQUIREMENTS,
    SECTION_SHARED_KEY,
    SECTION_THREADS,
    SECTION_VENDORED,
    declared_event_tags,
    declared_path,
    load_declaration,
    section,
    stated_document_meta,
    string_list,
)
from .dispatch import load_dispatch_manifest, shared_key_document
from .dispatch_edges import import_declared_dispatch_edges
from .dominated_edges import prune_dominated_fuzzy_call_edges
from .doxygen import (
    in_doxygen_scope,
    copy_database,
    declared_file_patterns,
    describe_doxyfile_resolution,
    discover_doxyfile,
    doxyfile_content_for,
    effective_file_patterns,
    parse_doxyfile_values,
    fix_doxygen_paths,
    rejected_doxyfile_candidates,
    repair_attribute_named_functions,
    run_doxygen,
    sanitize_doxygen_text,
    synthesize_doxyfile,
)
from .diagnostics import collect as collect_diagnostics
from .enrichment import enrich_database
from .errors import DoxygenUnavailableError, RustdocUnavailableError
from .event_edges import import_event_edges
from .filedocs import ingest_file_docs
from .harvest_plan import build_harvest_plan, warm_harvest_plan
from .doxygen_splice import include_expansion, splice_doxygen, xref_closure
from .indexcache import IndexCache
from .testscope import TEST_PATH_FACTS, mark_test_scope
from .datamodel import import_data_model_keys
from .kconfig import import_kconfig
from .kconfig_gates import import_kconfig_gates
from .locks import extract_locks
from .precommit import discover_guard_config_logged
from .preprocessor import PreprocessorConfig, doxyfile_lines, resolve_preprocessor
from .prose import ingest_supplementary_docs
from .py_entrypoints import python_entry_seeds
from .query._common import meta_section
from .reachability import (
    ENTRY_PATTERN_FACTS,
    ENTRY_PATTERN_HEURISTICS,
    mark_reachability,
)
from .requirements import (
    resolve_catalog_path,
    import_req_edges,
    import_req_test_edges,
    ingest_requirements_yaml,
    load_guard_config,
    resolve_req_id_pattern,
)
from .rustdoc import run_rustdoc, uses_rustdoc
from .scope import (
    INDEX_SCOPE_SECTION,
    SCOPE_FROM_GUARD,
    SOURCE_DOXYFILE,
    DerivedScope,
    derive_scope,
    derive_scope_logged,
)
from .shared_key_edges import (
    import_mqtt_dispatch_edges,
    import_shared_key_edges_declared,
    import_shared_key_edges_inferred,
    resolve_key_alias_prefixes,
)
from .stagetimer import STAGES_KEY, StageTimer
from .threads import annotate_thread_boundaries, extract_threads
from .tiers import (
    OPTIONS_META_PREFIX,
    DocumentResolution,
    LayeredResolution,
    options_meta,
    recorded_document,
    recorded_explicit,
    resolve_document,
    resolve_layered,
)
from .treescan import (
    ScanSummary,
    doxygen_input_roots,
    enumerate_tree,
    manifest_key,
    roots_matching_no_file_pattern,
)
from .vocabulary import DeclarationError

## The one subcommand word this CLI dispatches on, before the build parser sees
## argv. Mirrors `propose.command.COMMAND`, which is the definition — spelled
## again here so a build invocation never has to import the proposer, and pinned
## by a test (tests/test_propose.py) so the two cannot drift apart.
PROPOSE_COMMAND = "propose"

## `export` writes an index's TIER-1 STATEMENTS back out as a declaration (plan 4.19), closing the
## half of "YAML is an import/export format" that `--declare` only opened. Dispatched on the first
## word and imported lazily like its siblings, so a build never pays for yaml rendering.
EXPORT_COMMAND = "export"
## Same arrangement for the MCP registration doctor: mirrors
## `init_command.COMMAND` and is pinned by a test (tests/test_init.py), so a build
## invocation never imports it. That matters more here than for `propose` —
## `init` is the FIRST command a fresh `pip install clew` runs, so a plain
## build invocation must not drag the registration doctor — or the MCP SDK it
## probes for — into its import graph.
INIT_COMMAND = "init"

## The `build_meta` section carrying the scope decision, and the key inside it that
## records what the OPERATOR removed — kept apart from `scope.excludes`, which is
## what the walker pruned. The two invite opposite responses from a reader: a derived
## exclude is a fact about the tree, an operator exclude is a decision that can be
## withdrawn, and one merged list states neither.
SCOPE_META_PREFIX = "scope"
OPERATOR_EXCLUDES_KEY = "operator_excludes"

## How the repo-relative path lists in `scope.*` are joined. One constant for the
## writer and the reader because `operator_excludes` is READ BACK on the next build,
## so a separator that drifted would not merely misprint — it would replay a
## different set of exclusions than the operator stated.
SCOPE_LIST_SEPARATOR = ", "

## The option name the reachability seed patterns are stamped and replayed under,
## inside the `options` build_meta section (`tiers.OPTIONS_META_PREFIX`). One
## literal for the writer and the reader, for the reason above — a drifted option
## name would replay nothing while the stamp still looked healthy.
OPTION_ENTRY_PATTERNS = "entry_patterns"

## The ingot key-alias prefixes, the second layered option (gh#319). Recorded but
## NOT replayed: unlike `--entry-patterns` there is no flag carrying the prefixes
## themselves — `--shared-key-patterns` names a FILE, which is re-read every build,
## so there is no one-off statement that a refresh could silently discard.
##
## THE SECOND HALF OF THAT SENTENCE WAS WRONG AND IS KEPT (gh#364). The prefixes are
## still derived and still not replayable — that part holds. But "the file is re-read
## every build" quietly conflated the FILE with the FLAG THAT NAMES IT: nothing replayed
## `--shared-key-patterns`, so the next build re-read no file at all and fell back to the
## target's own declaration. Measured on this repo's self-index: a pass that stated a
## shared-key manifest inline, followed by a pass that stated nothing, returned in 1.7 s
## having reverted to the undeclared policy while reporting success. The five manifest
## options are replayed by `_replay_manifest_statements` below for exactly that reason.
OPTION_KEY_ALIAS_PREFIXES = "key_alias_prefixes"

## gh#366. The two tier-1 options that reached ONE build and were then lost, because
## `options_meta` was never given them and the replay loop covered manifests only. Named
## here beside the others so the three replay paths read from one list of option names.
OPTION_PREDEFINED = "predefined"
OPTION_EVENT_TAGS = "event_tags"


## @brief Print summary statistics of the generated database.
## @version 2
## @req REQ-DDB-CLI-001
def report_stats(db_path: Path) -> None:
    """Print summary statistics of the generated database onto the active console.

    The second of the two build-path writers that render outside `make_progress`,
    so it goes through the same seam: a caller whose stdout is a protocol transport
    captures this summary along with everything else. Rendered as one block with
    markup and highlighting off — a table name is a SQL identifier, not markup, and
    `soft_wrap` keeps a long database path on one line.

    @brief Report database contents summary.
    @version 2
    """
    conn = sqlite3.connect(str(db_path))
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        ).fetchall()
    ]
    lines = [f"\n  Database: {db_path}", f"  Tables: {len(tables)}"]
    for table in sorted(tables):
        count = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        lines.append(f"    {table}: {count} rows")
    conn.close()
    active_console().print("\n".join(lines), markup=False, highlight=False, soft_wrap=True)


## Every build dest that NO LONGER HAS A FLAG, with the default the flag declared. The
## surface collapsed from 22 arguments to 6; the DESTS did not, and that distinction is the
## whole safety of the change.
##
## WHY `set_defaults` RATHER THAN DELETING THEM. `build_index` sources its defaults BY
## PARSING (`_build_argparser().parse_args(["--output", …])`) precisely so a value it does
## not name arrives with the parser's declared default instead of silently becoming None —
## and `apply_options` lands a stated value ON one of these dests, because the option names
## ARE the dest names. Deleting the dest would break both mechanisms at once and turn every
## three-state option (absent inherits / empty withdraws / non-empty replaces) into a
## two-state one, which is the withdrawal-on-every-refresh defect this pipeline documents in
## four places.
##
## SO EVERY VALUE HERE IS THE FLAG'S OWN DEFAULT, COPIED, and nothing else: this collapse
## changes what a caller can SAY, never what any value MEANS. `scope` is the one that would
## have hurt — the parser declared `from-guard` and an earlier `build_index` signature
## declared `doxyfile`, which is the gh#333 inversion (a repo punished for documenting
## itself) reachable through one of two doors. It is written here once, so there is one
## declaration of it left in the tool.
##
## HOW EACH ONE IS NOW STATED, per group:
##   * `predefined`, `entry_patterns`, `shared_key_patterns`, `data_model`, `thread_patterns`,
##     `locks`, `mqtt_dispatch`, `dispatch`, `requirements`, `enrich` — a DECLARATION key,
##     reachable three ways: the target's own `.clew.yaml`, `--declare <file>`, or
##     the `options` argument of `build_index` / `index(action='refresh')`.
##   * `extra_input` / `extra_exclude` — absorbed by `index_scope:` (`roots:` / `excludes:`),
##     which `_apply_scope` folds into exactly these two dests, so the fold target is
##     literally the same list the flags appended to.
##   * `guard_config` — DELETED in favour of discovery, not folded. `discover_guard_config`'s
##     own docstring is the evidence: it searches the root, the path the doxygen-guard
##     pre-commit hook names in its `--config` arg, then `conf/ | config/ | .config/`, and it
##     says "Discovery (not a new flag) is deliberately the fix … a target keeping its config
##     in `conf/` is indexable through both entry points with nothing passed". The flag's
##     other job — carrying a declaration in the `x-clew` passthrough — is what
##     `--declare` now does directly and better, because it needs no guard config at all.
##   * `doxyfile` / `scope` — build MECHANICS with no declaration home, kept reachable on the
##     typed surface (`build_index(doxyfile=…, scope=…)`, `index(action='refresh',
##     doxyfile=…, scope=…)`) and by Doxyfile DISCOVERY for the CLI operator. `SCOPE_DOXYFILE`
##     is therefore still a real, reachable value; it is not a CLI opt-out any more.
##   * `index_cache` / `no_index_cache` — the sidecar path is DERIVED from `--output`, and
##     `--rebuild` is the operator-facing "do not trust the cache" verb. See
##     `_open_index_cache`.
_FOLDED_BUILD_DEFAULTS: dict[str, Any] = {
    "doxyfile": None,
    "scope": SCOPE_FROM_GUARD,
    "guard_config": None,
    "enrich": None,
    "requirements": None,
    "extra_input": None,
    "extra_exclude": None,
    "shared_key_patterns": None,
    "data_model": None,
    "thread_patterns": None,
    "locks": None,
    "mqtt_dispatch": None,
    "dispatch": None,
    "predefined": None,
    "entry_patterns": None,
    ## D4's vendored signal. A dest is REQUIRED, not optional: `apply_options` writes a
    ## stated section onto args, and a test asserts every accepted option can actually be
    ## applied — which is what caught this missing.
    "vendored": None,
    ## Same requirement as `vendored`: a dest is REQUIRED, and a test asserts every
    ## accepted option can actually be applied.
    "test_paths": None,
    "index_cache": None,
    "no_index_cache": False,
}


##
# @brief Default `--output` to the path the MCP server derives for `--repo-root`.
# @param args Parsed arguments, mutated in place.
# @return None.
# @version 1
# @dg_internal
def _resolve_output(args: argparse.Namespace) -> None:
    """THE TWO SURFACES DISAGREED ON WHERE AN INDEX LIVES. The MCP tools name a REPOSITORY and
    derive the database path from it; the CLI demanded a FILE and knew nothing about that
    derivation. So a CLI build landed wherever the caller said and was invisible to `dossier`
    and `search` unless they had independently computed the same path — and nothing in the CLI
    offered to. This repository's own acceptance notes worked around it by pasting a `python -c`
    one-liner into a comment, which is the shape of a missing feature rather than a recipe.

    IT IS THE ONLY BUILD ROUTE THAT MATTERS FOR PIPELINE WORK. A build through the server is
    refused whenever the server process predates the source, so anyone changing a stage must use
    this CLI — the one surface that could not write where the server reads.

    DERIVED THROUGH `target_for`, NEVER REIMPLEMENTED. The slug is a name plus a hash of the
    resolved path; a second copy of that rule here would be a second place for it to drift, and
    the failure would be silent — the index builds, the server looks elsewhere, and the repo
    reports as unindexed. Imported inside the function because `mcp_server` is a VIEW over this
    pipeline, so importing it at module scope would point the dependency backwards.

    NO EXISTING INVOCATION CHANGES. `--output` was `required=True`, so the branch below was
    unreachable until now; defaulting `--repo-root` to the working directory therefore cannot
    alter what any current caller builds.

    @brief Fill in `--output` from `--repo-root` when the caller named no file.
    @return None.
    @version 1
    """
    if args.output:
        return

    from .mcp_server.state import target_for

    repo = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd()
    args.repo_root = str(repo)
    args.output = target_for(repo).db_path
    logger.info("output: none given — writing where the MCP server reads %s: %s", repo, args.output)


## @brief Construct the argparse.ArgumentParser for the build script.
## @version 18
## @req REQ-DDB-CLI-001
## @return Configured ArgumentParser with all build-script CLI arguments registered.
def _build_argparser() -> argparse.ArgumentParser:
    """SIX ARGUMENTS, DOWN FROM TWENTY-TWO, and the count was never the point — the
    AMBIGUITY was. Eight of the twenty-two duplicated a declaration section, so the same
    fact had two spellings with a precedence rule between them, and several separate
    mechanisms decided the indexed scope. An agent resolving that ambiguity at build time
    has to work out which of two routes it is on before it can state anything at all.

    WHAT SURVIVES, AND WHY EACH ONE IS NOT A DECLARATION:
      * `--output` and `--repo-root` name the two ENDPOINTS of a build. Neither can live in
        a declaration read FROM the repo root, because one of them IS the repo root and the
        other is outside the tree being described.
      * `--exclude` is an INDEX-SHAPE argument — what the operator wants indexed, which
        nothing in the repository can state on their behalf. It is recorded into the index
        and replayed, so it is durable without being declared.
      * `--rebuild` and `--verbose` are properties of THIS RUN, not of the repository.
      * `--declare` is the import route for everything that IS a declaration.

    `--verbose` IS THE ONE DELIBERATE EXCEPTION and it is not a declaration: it changes the
    CLI's own stderr and nothing that reaches the index. A build's verbosity is not a
    property of the repository, so recording it would be recording the operator's terminal.

    Every dest the removed flags wrote to survives with its declared default in
    `_FOLDED_BUILD_DEFAULTS` — read the comment above it for the route that replaces each
    flag, and for why deleting the dests instead would break `build_index`'s
    defaults-by-parsing and `apply_options`' three states.

    @brief Construct the argparse.ArgumentParser for the build script.
    @return The configured parser.
    @version 17
    """
    parser = argparse.ArgumentParser(
        description="Build doxygen SQLite knowledge database",
        ## THE SUBCOMMANDS ARE NOT SUBPARSERS, so argparse cannot list them itself: `main`
        ## dispatches them by inspecting `sys.argv[1:2]` before this parser is built, which is
        ## what lets each one own its own flag set. The cost is that three working commands were
        ## absent from `--help` and discoverable only by already knowing they existed.
        epilog=(
            f"commands:\n"
            f"  {INIT_COMMAND:<10}register the MCP server and check it can run\n"
            f"  {PROPOSE_COMMAND:<10}propose a .clew.yaml declaration for a repository\n"
            f"  {EXPORT_COMMAND:<10}export an index\n"
            f"\nRun `clew <command> --help` for a command's own options.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.set_defaults(**_FOLDED_BUILD_DEFAULTS)
    parser.add_argument(
        "--output",
        help=(
            "Output database path. OPTIONAL: when omitted the index is written to the same "
            "location the MCP server derives for --repo-root, so a CLI build is visible to "
            "`dossier`/`search` without the caller computing a path."
        ),
    )
    parser.add_argument(
        "--repo-root",
        help=(
            "Repository to index (default: the current directory). It is the discovery root "
            "for the repo's own `.clew.yaml` and doxygen-guard config, the source of "
            "supplementary docs (README, CHANGELOG, docs/*.md), and what --output defaults from."
        ),
    )
    parser.add_argument(
        "--declare",
        metavar="FILE",
        help=(
            "Path to a declaration document — the same YAML shape as a repo's own "
            "`.clew.yaml` — stated for THIS build. It is the single route for "
            "every declared convention: index_scope, preprocessor (predefined, "
            "config_header), kconfig, event_tags, entry_patterns, locks, thread_patterns, "
            "shared_key_patterns, data_model, mqtt_dispatch, dispatch, requirements, "
            "enrich. It is applied at TIER 1 through exactly the same validated route as "
            "the `options` argument of build_index and index(action='refresh'), so a "
            "section stated here wins over the target's own file, is validated in the same "
            "words, and is recorded and replayed by later builds of the same database. "
            "Use it for a repository you do not own and must leave byte-identical."
        ),
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=None,
        metavar="PATH",
        help=(
            "Repo-relative paths to leave OUT of the index. An --exclude is RECORDED "
            "into the index as scope.operator_excludes and REPLAYED by every later build "
            "of the same database, so a refresh that does not restate it still honours "
            "it. Pass --exclude with no values to withdraw a recorded one; omit the flag "
            "entirely to inherit it. This is an INDEX-SHAPE argument — what the "
            "operator wants indexed — and deliberately not a route for declared "
            "CONVENTIONS (locks, threads, dispatch, shared keys, index_scope), which "
            "are stated with --declare or read from the target repo's own "
            ".clew.yaml so the CLI and the MCP server cannot honour different "
            "ones."
        ),
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "Ignore every cached entry (full doxygen run + full re-parse) but "
            "still REFRESH the cache, so the next build is incremental again."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser


## @brief Apply a `--declare` document through the tier-1 options route.
## @param args Parsed CLI arguments, mutated in place; `declare` is None when unstated.
## @return The option names applied, sorted, for logging.
## @version 2
## @req REQ-DDB-CONFIG-008
## @dg_internal
def _apply_declared_document(args: argparse.Namespace) -> list[str]:
    """ONE ROUTE, NOT A SECOND ONE. This does not parse, resolve or interpret anything: it
    reads the YAML and hands the whole mapping to `apply_options`, the same function the
    `options` argument of `build_index` and `index(action='refresh')` goes through. So a
    document stated on the command line and the identical mapping stated by an embedding
    caller are refused in the same words, land on the same dests, and are recorded and
    replayed by the same machinery. A separate loader here would be a second authority free
    to drift from the one an agent actually uses.

    THAT IS ALSO WHY UNKNOWN KEYS ARE `apply_options`' PROBLEM AND NOT HANDLED HERE. It
    already refuses an unknown option by name against the accepted set and a DERIVED one
    with the reason it cannot be stated — and it validates before assigning anything, so a
    document with one bad entry leaves the namespace untouched rather than half-applied.

    A DOCUMENT THAT IS NOT A MAPPING IS REFUSED, not silently ignored, and an EMPTY one is
    allowed. `{}` is the withdrawal spelling every option keeps, so `--declare` on an empty
    file states nothing and falls back to the target's own declaration — the same three
    states (absent inherits / empty withdraws / non-empty replaces) the flags it replaces
    had. `yaml.safe_load` returns None for an empty file, which is the empty case rather
    than an error.

    Relative paths INSIDE the document resolve against `--repo-root`, not the process's
    working directory, because `apply_options` is given the repo root for exactly that
    reason: a caller states the path they would have written in the declaration file.

    @brief Read a stated declaration document and apply it at tier 1.
    @return The applied option names.
    @version 2
    """
    import yaml

    stated = getattr(args, "declare", None)
    if not stated:
        return []
    path = Path(stated).expanduser().resolve()
    try:
        ## BYTES ONCE, decoded here rather than read twice. The recorded sha has to be over
        ## the bytes this call actually applied: a second `read_bytes()` for the record could
        ## hash a file edited in between and certify a statement that was never applied —
        ## which is the precise failure this record exists to catch, reintroduced by the
        ## mechanism meant to catch it.
        raw = path.read_bytes()
        document = yaml.safe_load(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise DeclarationError(f"--declare {path} could not be read: {exc}") from exc
    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise DeclarationError(
            f"--declare {path} must hold a mapping of declaration sections, got "
            f"{type(document).__name__}"
        )
    applied = apply_options(args, document, Path(args.repo_root) if args.repo_root else None)
    ## RECORDED HERE, where the document's BYTES are still in hand, and deliberately after
    ## `apply_options` — so a document that is refused stamps nothing. Stamping before the
    ## validation would record a statement the build did not honour, which is worse than no
    ## record: a checker would then confirm application that never happened.
    args.declaration_meta = stated_document_meta(raw, document)
    logger.info(
        "build options: stated by --declare %s (tier 1) — %s",
        path,
        ", ".join(applied) or "nothing (the document is empty)",
    )
    return applied


## @brief Route logging through Rich so summary INFOs share progress styling.
## @version 1
## @dg_internal
def _configure_logging(verbose: bool) -> None:
    """Route logging through Rich so summary INFOs share progress styling."""
    from rich.logging import RichHandler

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[
            RichHandler(
                console=console,
                show_time=False,
                show_path=False,
                show_level=False,
                markup=False,
            ),
        ],
    )


## @brief Refuse when an --extra-input root cannot contribute a file (gh#3).
## @param doxyfile The Doxyfile whose FILE_PATTERNS are in effect.
## @param extra_input The USER-supplied --extra-input entries only.
## @param extra_exclude The user-supplied --extra-exclude entries.
## @param repo_root Repo root, for enumeration keying.
## @return None; exits 1 when a root's every file is excluded by FILE_PATTERNS.
## @version 1
## @req REQ-DDB-INDEX-001
def _verify_extra_input_is_read(
    doxyfile: Path,
    extra_input: list[str] | None,
    extra_exclude: list[str] | None,
    repo_root: Path,
) -> None:
    """FAILS LOUDLY, because the alternative was reporting success. `--extra-input`
    adds a path to the indexed set; if the resolved Doxyfile's FILE_PATTERNS match
    none of the files under it, doxygen reads them, discards them and exits 0, and
    the requested files are simply absent from the index. A consumer meets that
    later as "that function is not in the database", which reads as a parser gap
    rather than the configuration one it is.

    A WARNING was considered and rejected. The user named this root explicitly, so
    the build cannot do what was asked; the whole defect class this repo keeps
    finding is a check whose output is indistinguishable from success, and a warning
    on a successful build is exactly that. Naming both the root and the patterns is
    what makes the refusal actionable in one read: the root says which flag to drop,
    the patterns say what to widen, and either alone leaves the user guessing.

    MUST BE PASSED THE USER'S OWN --extra-input, not `args.extra_input` after
    `_apply_scope` has run. That function PREPENDS the derived scope roots (and, on
    the whole-repo fallback, the repo root itself) into the same list, so checking
    the mutated value would judge roots the user never named — and a derived root
    that legitimately holds no matching file would then refuse a build that has
    always worked.

    @brief Refuse an --extra-input root that FILE_PATTERNS excludes entirely.
    @return None.
    @version 1
    """
    offenders = roots_matching_no_file_pattern(
        doxyfile, doxyfile.parent, extra_input, extra_exclude, repo_root
    )
    if not offenders:
        return
    patterns = " ".join(effective_file_patterns(doxyfile))
    for root in offenders:
        logger.error(
            "--extra-input %s contributes NOTHING to the index: it holds files, but "
            "not one matches the effective FILE_PATTERNS (%s) declared by %s. doxygen "
            "would read them, discard them, and exit 0 — so the build would have "
            "reported success with those files absent. Widen FILE_PATTERNS in that "
            "Doxyfile, or drop --extra-input %s.",
            root,
            patterns,
            doxyfile,
            root,
        )
    sys.exit(1)


## @brief Fold a derived scope's roots and excludes into the build arguments.
## @param args Parsed CLI arguments (mutated in place).
## @param scope The scope whose roots become the INPUT list.
## @version 1
## @req REQ-DDB-CLI-001
def _fold_scope_into_args(args: argparse.Namespace, scope: DerivedScope) -> None:
    """ONE fold for every tier. The whole-repo root used to be written into
    `extra_input` here with no `DerivedScope` and therefore no EXCLUDEs, so the widest
    scope in the tool was the one that reached doxygen without the containment a
    narrow declared root gets.

    @brief Make a derived scope the build's INPUT/EXCLUDE lists.
    @version 1
    """
    args.extra_input = [str(p) for p in scope.roots] + list(args.extra_input or [])
    args.extra_exclude = [str(p) for p in scope.excludes] + list(args.extra_exclude or [])
    args.replace_input = True


## @brief Apply `--scope from-guard` by folding the resolved roots into the args.
## @param args Parsed CLI arguments (mutated in place).
## @param repo_root Repo root whose declaration is read.
## @version 7
## @req REQ-DDB-CLI-001
def _apply_scope(args: argparse.Namespace, repo_root: Path) -> None:
    """`--scope from-guard` RESOLVES the indexed file set from the target's own
    declaration and makes it the INPUT list (`replace_input`), with any explicit
    `--extra-input` appended on top.

    EVERY from-guard SCOPE IS NOW FOLDED, declared or not (gh#333). The undeclared
    branch used to `return` without folding, which handed INPUT back to the
    Doxyfile — so a repo with a Doxyfile got its published-API subset and a repo
    without one got the whole tree, which is the inversion gh#333 names: a repo was
    punished for documenting itself. `derive_scope` now returns a whole-repo scope
    with real roots in that case, so there is one code path and no fallthrough.

    The old `index_whole_repo` special case is gone with it. It existed because the
    synthesis branch had to guarantee a non-empty INPUT — measured on mbedtls as a
    clean `rc=0` build producing 0 functions, 0 files, 0 edges — and `derive_scope`
    now guarantees that for every repo root, so a second path to the same scope
    would only be a way for the two to disagree.

    @brief Resolve the build's file scope from the requested source.
    @version 7
    """
    args.replace_input = False
    if args.scope != SCOPE_FROM_GUARD:
        ## gh#382 — REFUSE the contradiction rather than discard the statement. A stated
        ## `index_scope` is only read on the from-guard path, so pairing it with any other
        ## `--scope` would build a DIFFERENT boundary than the caller stated and report
        ## success — the shape `_repo_relative_exclusion` below already refuses three times
        ## over. An agent that cannot see the log is exactly the caller this option exists
        ## for, so a warning would be invisible to it.
        if getattr(args, INDEX_SCOPE_SECTION, None):
            logger.error(
                "%s was stated but --scope is %r, and a stated %s is only read on %r — "
                "the boundary you stated would be silently replaced. Drop --scope (its "
                "default) or drop the %s statement.",
                INDEX_SCOPE_SECTION,
                args.scope,
                INDEX_SCOPE_SECTION,
                SCOPE_FROM_GUARD,
                INDEX_SCOPE_SECTION,
            )
            sys.exit(1)
        return
    ## gh#382 completes 11/11: `index_scope` is the one section the declaration-merge
    ## injection cannot reach, because scope is resolved HERE — before the declaration is
    ## loaded for the stages. So the stated document is threaded down to
    ## `_declared_index_scope`, which builds it through the same construction a written one
    ## takes; only the reported `reason` differs, and it must, or an owner reading
    ## "declared in <file>" would go and edit a file that says nothing.
    _fold_scope_into_args(
        args,
        derive_scope_logged(
            repo_root,
            getattr(args, "guard_config", None),
            getattr(args, INDEX_SCOPE_SECTION, None),
        ),
    )


## @brief Normalize one stated exclusion to a repo-relative path, or refuse it.
## @param entry The path the operator stated, absolute or repo-relative.
## @param repo_root Resolved repository root the record is relative to.
## @return The repo-relative POSIX spelling to record and replay.
## @version 1
## @req REQ-DDB-CONFIG-001
def _repo_relative_exclusion(entry: str, repo_root: Path) -> str:
    """REFUSES rather than warns, in both fatal cases, because both produce a build
    that succeeds while doing something other than what was asked:

    - OUTSIDE THE REPO. The record is stored repo-relative, so such a path has no
      honest stored form; storing its bare name would replay as a DIFFERENT exclusion
      on the next build, and it excludes nothing in the meantime because nothing
      outside the repo is indexed.
    - THE REPO ROOT ITSELF. Indexing nothing and reporting success is the worst
      available outcome — a well-formed, confident, empty database.
    - A COMMA. The stamped list is comma-joined like `scope.roots` beside it, and this
      one is READ BACK, so a comma inside a member silently splits into two
      exclusions neither of which is the one stated.

    A path that does not EXIST is warned about and kept. Dropping it would be the
    silent discard this whole feature exists to prevent, and an exclusion may
    legitimately name a tree that has not been generated yet.

    @brief Validate and normalize one operator exclusion.
    @return Repo-relative POSIX path.
    @version 1
    """
    if SCOPE_LIST_SEPARATOR.strip() in entry:
        logger.error(
            "--exclude %r contains %r, which separates the recorded list — the "
            "exclusion could not be replayed as stated. Rename the path or exclude a "
            "parent of it.",
            entry,
            SCOPE_LIST_SEPARATOR.strip(),
        )
        sys.exit(1)
    path = (repo_root / entry).resolve()
    if path == repo_root:
        logger.error(
            "--exclude %r resolves to the repository root %s, which would index "
            "NOTHING and report success. Name the subtree to leave out instead.",
            entry,
            repo_root,
        )
        sys.exit(1)
    try:
        relative = path.relative_to(repo_root)
    except ValueError:
        logger.error(
            "--exclude %r resolves to %s, which is OUTSIDE the repository %s. Nothing "
            "there is indexed, so the exclusion would do nothing, and it has no "
            "repo-relative form to record.",
            entry,
            path,
            repo_root,
        )
        sys.exit(1)
    if not path.exists():
        logger.warning(
            "--exclude %s does not exist under %s — recording it anyway, so it applies "
            "if that path appears later. Check the spelling if you expected it to "
            "remove something from this build.",
            relative.as_posix(),
            repo_root,
        )
    return relative.as_posix()


## @brief The exclusions in force for this build: stated now, else recorded before.
## @param args Parsed CLI arguments, whose `exclude` is None when the flag is absent.
## @param output Live database path, which still holds the PREVIOUS build's record.
## @param repo_root Resolved repository root.
## @return Repo-relative exclusions, order-preserving and de-duplicated.
## @version 1
## @req REQ-DDB-CONFIG-001
def _operator_excludes(args: argparse.Namespace, output: Path, repo_root: Path) -> tuple[str, ...]:
    """READS THE PREVIOUS BUILD'S RECORD, and that read is the entire point. Scope is
    re-derived from the repo's declarations and the tree on every build — nothing in
    the build path has ever consulted what a previous build stamped — so an exclusion
    that is applied and recorded but not read back is discarded by the next refresh,
    which then reports success and a healthy coverage ratio over exactly the content
    the operator removed.

    THREE STATES, kept distinct: the flag ABSENT (`None`) inherits, the flag EMPTY
    (`[]`) withdraws, and a non-empty list replaces. Collapsing absent into empty
    would make the record unreadable-back; collapsing empty into absent would make it
    unwithdrawable except by deleting the database.

    Read off `output` rather than the temp database being built, and therefore BEFORE
    the atomic swap: the build writes a fresh `build_meta` into a temp file that
    replaces this one, so after the swap the previous record is gone.

    LOST TO A CULL. The record lives in the database, and `mcp_server.state` drops a
    target by removing its directory — so a culled target's next build starts from an
    unnarrowed index. Stated plainly rather than worked around: a second copy in the
    registry would be a second source of truth for one decision, and the CLI has no
    registry to keep it in.

    @brief Resolve the operator exclusions for this build.
    @return The repo-relative exclusions in force.
    @version 1
    """
    stated = getattr(args, "exclude", None)
    if stated is None:
        recorded = meta_section(output, SCOPE_META_PREFIX).get(OPERATOR_EXCLUDES_KEY, "")
        entries = [part.strip() for part in recorded.split(SCOPE_LIST_SEPARATOR.strip())]
    else:
        entries = [str(entry) for entry in stated]
    resolved: list[str] = []
    for entry in entries:
        if not entry:
            continue
        relative = _repo_relative_exclusion(entry, repo_root)
        if relative not in resolved:
            resolved.append(relative)
    return tuple(resolved)


## @brief Invoke doxygen with the CLI's extra INPUT/EXCLUDE arguments applied.
## @param doxyfile The target's Doxyfile (or the synthesized one).
## @param args Parsed CLI arguments.
## @param predefined Pre-rendered PREDEFINED Doxyfile text, empty when none is declared.
## @return Path to the generated doxygen SQLite database.
## @version 4
## @dg_internal
def _run_doxygen_from_args(doxyfile: Path, args: argparse.Namespace, predefined: str = "") -> Path:
    """@brief Run doxygen for the parsed CLI arguments."""
    return run_doxygen(
        doxyfile,
        doxyfile.parent,
        extra_input=args.extra_input,
        extra_exclude=args.extra_exclude,
        replace_input=getattr(args, "replace_input", False),
        output_dir=_doxygen_out_dir(args),
        predefined=predefined,
    )


## @brief Run doxygen over an explicit file list, replacing the Doxyfile's own INPUT.
## @param doxyfile The Doxyfile to base the run on.
## @param args Parsed CLI arguments.
## @param predefined Pre-rendered PREDEFINED text.
## @param repo_root Absolute repository root.
## @param subset Repo-relative paths to make the whole INPUT.
## @return The generated database path.
## @version 1
## @req REQ-DDB-INDEX-002
def _run_subset(
    doxyfile: Path,
    args: argparse.Namespace,
    predefined: str,
    repo_root: Path,
    subset: list[str],
) -> Path:
    """Extracted because the incremental path runs doxygen TWICE and the two invocations must
    be identical in configuration. Spelling them out separately is how the second pass would
    quietly drift from the first.

    @brief Run one subset doxygen pass.
    @return Path to the generated database.
    @version 1
    """
    return run_doxygen(
        doxyfile,
        doxyfile.parent,
        extra_input=[str(repo_root / rel) for rel in subset],
        replace_input=True,
        output_dir=_doxygen_out_dir(args),
        predefined=predefined,
    )


## How many consecutive splices are allowed before a whole-tree build is forced. A spliced
## database is not bit-identical to a rebuild — measured on this repository, one stale call
## edge in 5168 with nothing missing — and nothing in a splice bounds the accumulation of
## that error across many refreshes. 20 keeps the worst case at roughly twenty stale edges
## while still amortising one full build over twenty cheap ones.
SPLICE_GENERATION_LIMIT = 20


## @brief Decide whether an incremental doxygen run is possible, and what to feed it.
## @param cache The index cache holding the previous output and this run's scan.
## @param summary This run's tree classification.
## @param repo_root Absolute repository root.
## @param config_sha This build's configuration hash; only matching output may be spliced.
## @param doxyfile The Doxyfile, read for the scope patterns.
## @param args Parsed CLI arguments, for the replace_input regime.
## @return (previous output, changed set, removed set, subset list), or None to run in full.
## @version 2
## @req REQ-DDB-INDEX-002
def _incremental_plan(
    cache: IndexCache,
    summary: ScanSummary,
    repo_root: Path,
    config_sha: str,
    doxyfile: Path,
    args: argparse.Namespace,
) -> tuple[Path, set[str], set[str], list[str]] | None:
    """SEPARATED FROM THE ACTION so the decision is readable on its own and so the guard
    conditions cannot be lost among the file shuffling that follows.

    Declines in three cases, each for a different reason:

      - nothing changed AND nothing was removed: there is no work, and the caller's
        `doxygen_get` hit should already have covered it;
      - no verified previous output exists: there is nothing to splice INTO, so a full run is
        not a fallback but the only correct answer;
      - the closure expanded to the whole tree: a subset run would re-read everything anyway,
        so paying the splice's complexity buys nothing. No arbitrary threshold is involved —
        doxygen's cost is near-linear in input size, so the break-even IS the tree.

    @brief Plan an incremental doxygen run.
    @return The plan, or None.
    @version 2
    """
    ## THE SCAN IS UNFILTERED BY DESIGN — it answers "did anything change", where a false
    ## positive only costs a rebuild. Using that same set as the doxygen INPUT is what let a
    ## glob-excluded file be spliced into the master, so the changed set is narrowed to the
    ## run's REAL scope here, before it becomes either a delete target or an INPUT entry.
    ## Filtered at the plan, not at the run, so `changed` and `subset` cannot disagree about
    ## what is in scope — a file dropped from one but not the other lands in `skipped` and
    ## reads as "left stale" when it should never have been a candidate.
    honor_exclude = not getattr(args, "replace_input", False)
    changed = set(
        in_doxygen_scope(
            sorted(set(summary.modified) | set(summary.added)), doxyfile, honor_exclude
        )
    )
    removed = set(in_doxygen_scope(sorted(summary.removed), doxyfile, honor_exclude))
    if cache.splice_generation() >= SPLICE_GENERATION_LIMIT:
        logger.info(
            "doxygen: %d consecutive incremental splices — running in full to reset "
            "accumulated drift",
            cache.splice_generation(),
        )
        return None
    previous = cache.doxygen_any(config_sha) if (changed or removed) else None
    if previous is None:
        return None
    subset = sorted(xref_closure(previous, changed, repo_root)) if changed else []
    total = len(summary.unchanged) + len(changed)
    viable = subset and len(subset) < total if changed else bool(removed)
    return (previous, changed, removed, subset) if viable else None


## @brief Satisfy the doxygen stage by re-reading only the changed files and splicing.
## @param doxyfile The Doxyfile driving the run.
## @param args Parsed CLI arguments.
## @param predefined Pre-rendered PREDEFINED text for the declared preprocessor config.
## @param cache The index cache.
## @param summary This run's tree classification.
## @param repo_root Absolute repository root.
## @param config_sha This build's configuration hash.
## @return The spliced database, or None when a full run is required.
## @version 3
## @req REQ-DDB-INDEX-002
def _incremental_doxygen(
    doxyfile: Path,
    args: argparse.Namespace,
    predefined: str,
    cache: IndexCache,
    summary: ScanSummary,
    repo_root: Path,
    config_sha: str,
) -> Path | None:
    """THE COPY BEFORE THE SUBSET RUN IS THE WHOLE TRICK. Every `doxygen_cache` key names the
    SAME output path and each build OVERWRITES it, so the subset run destroys the database
    being spliced from. `previous` is copied aside FIRST; skip that and the splice reads its
    own subset as its master and quietly produces a database holding only the changed files.

    Falls back by returning None rather than raising. An incremental path that fails should
    cost a full rebuild, never a failed build — the feature exists to make refreshes cheap,
    and a cheap refresh that sometimes breaks the index would be worse than an expensive one.

    @brief Run doxygen incrementally and splice the result.
    @return The spliced database, or None.
    @version 3
    """
    plan = _incremental_plan(cache, summary, repo_root, config_sha, doxyfile, args)
    if plan is None:
        return None
    previous, changed, removed, subset = plan
    keep = previous.with_name(previous.name + ".prev")
    staged: Path | None = None
    try:
        shutil.copy2(previous, keep)
        if subset:
            produced = _run_subset(doxyfile, args, predefined, repo_root, subset)
            ## SECOND PASS, BOUNDED AT ONE. `xref_closure` is derived from the PRE-EDIT
            ## master, so it can only re-supply callees the changed file ALREADY called — and
            ## a change set is exactly where NEW calls appear. Measured: adding one call to a
            ## previously-uncalled function produced a subset with none of that callee's files
            ## and lost the edge against a full rebuild, with `xrefs_unresolved` at zero
            ## because the row never existed to be dropped.
            extra = include_expansion(produced, keep, changed, set(subset), repo_root)
            if extra:
                logger.info(
                    "doxygen: incremental second pass — the include graph adds %d file(s) "
                    "the pre-edit xref table could not have named",
                    len(extra),
                )
                subset = sorted(set(subset) | extra)
                produced = _run_subset(doxyfile, args, predefined, repo_root, subset)
            staged = produced.with_name(produced.name + ".subset")
            shutil.copy2(produced, staged)
        report = splice_doxygen(keep, staged, changed, previous, repo_root, removed=removed)
    except (OSError, sqlite3.Error) as exc:
        logger.warning("doxygen: incremental splice failed (%s) — running in full", exc)
        return None
    finally:
        for scratch in (keep, staged):
            if scratch is not None:
                scratch.unlink(missing_ok=True)
    logger.info(
        "doxygen: incremental — re-read %d of %d file(s); %s",
        len(subset),
        len(summary.unchanged) + len(changed),
        report.describe(),
    )
    return previous


## @brief Which paths hold test code, resolved through the five-tier rule.
## @param args Parsed CLI arguments (uses --test-paths / the stated option).
## @param decl The repo's parsed `.clew.yaml`.
## @return The resolution: the pattern set plus the stated tier that won.
## @version 1
## @req REQ-DDB-CONFIG-006
## @req REQ-DDB-QUERY-003
def _test_paths(args: argparse.Namespace, decl: dict) -> LayeredResolution:
    """`TEST_PATH_FACTS` enters as HEURISTICS, not facts, and the distinction is the whole
    point of the tier rule here. A repo that declares `test_paths:` is stating its layout, so
    the guesses must be DISPLACED rather than accumulated — otherwise declaring `t/*` would
    still leave `tests/*` and `*_test.*` in force, and an operator could not narrow the rule at
    all, only widen it.

    Contrast `entry_patterns`, where the built-ins are facts that accumulate beneath a
    statement. Reachability wants every plausible seed; this wants exactly the caller's notion
    of "test".

    @brief Resolve the test-path patterns and their provenance.
    @return The LayeredResolution for `test_paths`.
    @version 1
    """
    return resolve_layered(
        facts=(),
        explicit=getattr(args, "test_paths", None),
        declared=decl.get(SECTION_TEST_PATHS),
        heuristics=TEST_PATH_FACTS,
    )


## @brief Reachability entry patterns, resolved through the five-tier rule.
## @param args Parsed CLI arguments (uses --entry-patterns).
## @param decl The repo's parsed `.clew.yaml`.
## @return The resolution: the pattern set plus the stated tier that won.
## @version 3
## @req REQ-DDB-CLI-001
## @req REQ-DDB-CONFIG-006
def _entry_patterns(args: argparse.Namespace, decl: dict) -> LayeredResolution:
    """THE FIRST CONSUMER of `tiers.resolve_layered`, and the case that motivated
    it. This function used to implement two different meanings of "supersede" in
    four lines: the flag REPLACED the whole list while the declaration EXTENDED it.
    So moving one value from `.clew.yaml` onto the command line silently
    dropped `main`, `app_main` and every guess with them — reachability collapsed
    and no warning, count or stamped row said so.

    Under the rule both stated tiers now displace only the tier-5 guesses, and
    `ENTRY_PATTERN_FACTS` accumulates beneath whatever anyone states. The
    declaration therefore changes meaning too, and deliberately: declaring
    `%trampoline%` now yields `main, app_main, %trampoline%` rather than the eleven
    it used to, because a repo that names its own dispatch convention is stating
    that convention rather than adding a footnote to ours.

    RETURNS THE RESOLUTION, not a list, so the winning tier travels with the values
    to the stamping stage — a tiered resolution nobody records is the same opacity
    with more steps.

    @brief Resolve the reachability seed patterns and their provenance.
    @return The LayeredResolution for `entry_patterns`.
    @version 3
    """
    return resolve_layered(
        facts=ENTRY_PATTERN_FACTS,
        explicit=getattr(args, "entry_patterns", None),
        declared=string_list(decl, SECTION_ENTRY_PATTERNS),
        heuristics=ENTRY_PATTERN_HEURISTICS,
    )


## @brief The tier-1 entry-pattern statement in force: stated now, else recorded before.
## @param args Parsed CLI arguments, whose `entry_patterns` is None when the flag is absent.
## @param output Live database path, which still holds the PREVIOUS build's record.
## @return The explicit patterns, or None when there is no tier-1 statement.
## @version 1
## @req REQ-DDB-CONFIG-006
def _recorded_entry_patterns(args: argparse.Namespace, output: Path) -> list[str] | None:
    """THE SAME READ-BACK `_operator_excludes` DOES, for the same reason. Entry
    patterns are re-resolved from scratch on every build, so a `--entry-patterns`
    applied once is discarded by the next refresh — and the refresh that discards it
    is usually the MCP server's, which passes no flags at all. The operator sees a
    successful rebuild and a liveness split computed from a policy they replaced.

    THREE STATES, kept distinct exactly as excludes keep them: the flag ABSENT
    (`None`) inherits the recorded statement, the flag EMPTY (`[]`) withdraws it and
    falls back to the declaration or the built-in guesses, and a non-empty list
    replaces it. `--entry-patterns` takes `nargs="*"` so the withdrawal is
    expressible; with `+` there was no way back to the defaults short of deleting
    the database.

    ONLY TIER 1 IS REPLAYED. A tier-2 declaration re-derives itself from a file that
    may have changed, so replaying a stored copy would freeze a stale declaration —
    `LayeredResolution.as_meta` records nothing to replay for it.

    Read off `output`, the live path, and therefore BEFORE the atomic swap: the
    build writes a fresh `build_meta` into a temp file that replaces this one.

    @brief Resolve the tier-1 entry-pattern statement for this build.
    @return The explicit pattern list, or None when none is in force.
    @version 1
    """
    stated = getattr(args, "entry_patterns", None)
    if stated is not None:
        return [str(entry) for entry in stated]
    recorded = recorded_explicit(meta_section(output, OPTIONS_META_PREFIX), OPTION_ENTRY_PATTERNS)
    return list(recorded) or None


## @brief Merge any tier-1 section documents over the target's own declaration.
## @param decl The declaration as loaded from the target, possibly empty.
## @param args Parsed CLI arguments, carrying any stated section documents.
## @return The declaration the stages should read.
## @version 1
## @req REQ-DDB-CONFIG-008
def _with_stated_sections(decl: dict, args: argparse.Namespace) -> dict:
    """gh#382 — ONE INJECTION POINT INSTEAD OF THREE PLUMBING ROUTES. `preprocessor:` and
    `kconfig:` were tier-2 ONLY: readable from a checked-in `.clew.yaml` and
    unreachable from the MCP surface, because neither has an argparse dest. That is
    CLAUDE.md's rule read the other way round — "a declaration reachable only from argv is
    not a declaration" — and it bites hardest on the case the declaration model exists for,
    a third-party repository that carries no config file for a tool it has never heard of.

    Merged over the declaration the stages already read, rather than threaded through three
    new dests with three new resolution orders. Every consumer of `decl` gets the stated
    value for free and there is one place where tier 1 beats tier 2.

    SECTION-LEVEL REPLACEMENT, NOT A DEEP MERGE, and that is the fail-closed choice. A deep
    merge of `preprocessor: {predefined: [...]}` over a declared `{config_header: auto}`
    would produce a configuration NEITHER side stated, which is the variant nobody can point
    at — and this pipeline's whole discipline is that an index represents a configuration
    somebody chose. Stating a section replaces it; stating `{}` withdraws the statement and
    the target's own declaration answers again, matching every other option's three states.

    @brief Overlay stated section documents onto the declaration.
    @return The merged declaration.
    @version 1
    """
    stated = {
        name: document
        for name in SECTION_DOCUMENT_OPTIONS
        if (document := getattr(args, name, None))
    }
    if not stated:
        return decl
    logger.info(
        "build options: section(s) stated inline (tier 1 replaces the target's own "
        "declaration) — %s",
        ", ".join(sorted(stated)),
    )
    return {**decl, **stated}


## Declaration sections whose whole value is a repo-relative PATH to a document this tool
## reads but does not own, and which land on the argparse dest of the flag they replaced.
## Deliberately NOT part of `SECTION_DOCUMENT_OPTIONS`: those are merged into `decl` for the
## stages to read, while these two are consumed as `args.requirements` / `args.enrich` by
## code that has always read a path there. Merging them instead would leave both consumers
## reading None.
_DECLARED_PATH_SECTIONS: tuple[str, ...] = (SECTION_REQUIREMENTS, SECTION_ENRICH)


## @brief Let the target's own declaration supply the path options nothing stated.
## @param args Parsed CLI arguments, mutated in place.
## @param decl The repo's declaration, already carrying any tier-1 stated section.
## @param repo_root Root a relative declared path resolves against.
## @return The section names the declaration supplied, sorted, for logging.
## @version 1
## @req REQ-DDB-CONFIG-001
## @req REQ-DDB-CONFIG-008
## @dg_internal
def _apply_declared_paths(args: argparse.Namespace, decl: dict, repo_root: Path) -> list[str]:
    """TIER 1 WINS BY BEING CHECKED FIRST, which is the whole of the precedence rule and the
    reason this is `is not None` rather than truthiness. `requirements: ""` states "no
    catalog" and must not fall through to the declaration, exactly as `[]` withdraws an
    entry-pattern statement instead of inheriting one — the absent/empty/replaces convention
    every option here keeps.

    IT DOES NOT DISPLACE `resolve_catalog_path`. That function owns the order below this one
    (the guard's own `impact.requirements.file`, then the conventional root file, then
    nothing) and is reached with `args.requirements` as its explicit input. A declared
    `requirements:` therefore inserts ONE tier above the gate's declaration rather than
    replacing the resolver — which matters because those two are different documents' claims
    about the same thing and the repo's rule is that the more specific declaration wins.

    RELATIVE TO THE REPO, never to the process's working directory: the declaration is read
    from the repo root and names paths the way every other section does, and an MCP server's
    cwd is not the target repo.

    @brief Fill unstated path options from the target's own declaration.
    @return The sections that supplied a value.
    @version 1
    """
    supplied: list[str] = []
    for name in _DECLARED_PATH_SECTIONS:
        if getattr(args, name, None) is not None:
            continue
        declared = decl.get(name)
        if not declared or not isinstance(declared, (str, Path)):
            continue
        resolved = Path(declared).expanduser()
        setattr(args, name, str(resolved if resolved.is_absolute() else repo_root / resolved))
        supplied.append(name)
    if supplied:
        logger.info(
            "declaration: %s supplied by the target's own declaration — %s",
            "path(s)" if len(supplied) > 1 else "path",
            ", ".join(f"{name}={getattr(args, name)}" for name in supplied),
        )
    return supplied


## @brief Resolve the tier-1 `predefined` statement in force for this build.
## @param args Parsed CLI arguments; `predefined` is None when unstated this run.
## @param output Live database path, still holding the PREVIOUS build's record.
## @return The explicit macro list, or None when none is in force.
## @version 3
## @req REQ-DDB-CONFIG-006
## @req REQ-DDB-CONFIG-008
def _recorded_predefined(args: argparse.Namespace, output: Path) -> list[str] | None:
    """gh#366 — THE SAME HOLE gh#364 CLOSED FOR MANIFESTS, left open on this option, and it
    loses more than a policy. A stated `predefined` decides which preprocessor branches
    doxygen even parses, so losing it silently changes WHICH CODE IS IN THE INDEX: measured
    on mbedtls, the difference between a stated and an unstated preprocessor configuration is
    663 doxygen call edges against 9,940.

    AND gh#11's AST RECOVERY MASKS THE LOSS, which is why this was invisible. After a lost
    `predefined` the symbols are still in `memberdef` — recovered from source text as
    `dg_source='ast'`, with no brief, no params and no `@req`. A health check asking "is the
    symbol indexed?" reports fine. Only a check filtering on PROVENANCE can see it, which is
    what the control for this asserts.

    THE SECOND BUILD IS THE NORMAL CASE, not a corner: `status` reports staleness and the
    guidance tells an agent to refresh, so an agent that brings an index up with a stated
    configuration and then refreshes discards its own bringup work and is never told.

    Three states, exactly as `entry_patterns` and `--exclude` keep them: ABSENT (`None`)
    inherits the record, EMPTY (`[]`) withdraws it, non-empty replaces. `--predefined` takes
    `nargs="+"`, so the withdrawal is expressible only through the tier-1 `options` route —
    which is the route that matters here, since the MCP server passes no flags at all.

    @brief Resolve the tier-1 predefined statement for this build.
    @return The explicit macro list, or None.
    @version 3
    """
    stated = getattr(args, "predefined", None)
    ## BOTH DOCUMENTED SPELLINGS, and only one of them was wired. `predefined` is the alias;
    ## `preprocessor: {predefined: [...]}` is the section form, and it is the one a team writes
    ## in a declaration file because it is the only form that can also carry `config_header`.
    ##
    ## MEASURED ON THE LIVE mbedtls INDEX, built from ONE declaration file carrying both a
    ## `locks:` and a `preprocessor:` section: `locks.tier` came out `explicit` and appeared in
    ## `stated_options`, while `predefined.tier` came out `declared`. Same file, same `--declare`,
    ## two tiers — and `recorded_explicit` replays only tier 1, so a later plain refresh kept the
    ## locks and silently dropped the macros.
    ##
    ## THE FAILURE IS AN ACCEPTED-BUT-UNREAD KEY. A stated `preprocessor:` is a SECTION_DOCUMENT
    ## option, so `apply_options` validates it and sets `args.preprocessor`; this resolver read
    ## `args.predefined` only. The statement parsed, validated, and was reported as applied, then
    ## resolved from the declaration at tier 2 as though nobody had stated anything.
    ##
    ## AND IT CONTRADICTED `--declare`'s OWN HELP, which promises the document "is applied at
    ## TIER 1 ... and is recorded and replayed by later builds of the same database". That help
    ## also says to use it "for a repository you do not own and must leave byte-identical" — so
    ## the file lives OUTSIDE the target, tier 2 means "the target's own file says so", and the
    ## next build re-reads a file that is not there. For `predefined` the cost is the
    ## macro-guarded half of a codebase dropping out of the index while the build reports success.
    ## AN EMPTY SECTION IS A WITHDRAWAL, AND IT WAS READ AS SILENCE. `{}` and `[]` are both the
    ## withdrawal spelling — but only `[]` was implemented. A stated `preprocessor: {}` left
    ## `section_form.get(OPTION_PREDEFINED)` as None, which is exactly what "the caller said
    ## nothing" looks like, so the replay below fired and restored the macro the caller had just
    ## withdrawn. The build then reported success while indexing the variant that was revoked.
    ##
    ## The three states are distinguished by whether the SECTION is present, not by what is
    ## inside it: absent inherits the record, PRESENT withdraws or replaces, and only a present
    ## non-empty statement replaces.
    section_form = getattr(args, "preprocessor", None)
    section_stated = isinstance(section_form, dict)
    if stated is None and section_stated:
        stated = section_form.get(OPTION_PREDEFINED)
    if stated is not None:
        ## An empty statement is NOT promoted: fabricating an empty tier-1 record here would
        ## replay a withdrawal as a statement.
        return [str(macro) for macro in stated] or None
    if section_stated:
        ## Stated, and carrying no macros: a withdrawal. Do NOT consult the record.
        return None
    recorded = recorded_explicit(meta_section(output, OPTIONS_META_PREFIX), OPTION_PREDEFINED)
    return list(recorded) or None


## @brief Replay the tier-1 manifest statements a previous build recorded.
## @param args Parsed CLI arguments; each manifest option is None when unstated this run.
## @param output Live database path, which still holds the PREVIOUS build's record.
## @return The option names replayed, sorted, for logging.
## @version 2
## @req REQ-DDB-CONFIG-006
## @req REQ-DDB-CONFIG-008
def _replay_manifest_statements(args: argparse.Namespace, output: Path) -> list[str]:
    """THE HOLE THIS CLOSES, MEASURED (gh#364, and gh#332 before it). A manifest
    statement — a `--locks` path, or since gh#360 the document inline — reached exactly
    one build and nothing recorded it. The next build that ran resolved the manifest
    from the target's own declaration again and the stated layer VANISHED, with the
    build reporting success: on this repo's self-index, a pass stating a shared-key
    manifest followed by a pass stating nothing returned in 1.7 s having reverted to
    the undeclared policy.

    WHY IT MATTERS BEYOND TIDINESS. The second build is not hypothetical, it is the
    normal case: `status` reports staleness and the guidance tells an agent to refresh,
    so a cell's agent that brings the index up and then calls `build_or_refresh` again
    would LOSE its own bringup work mid-cell and never be told — turning a measured
    bringup into a measurement of nothing.

    THREE STATES, kept distinct exactly as `--exclude` and `--entry-patterns` keep
    them. The option ABSENT (`None`) inherits the recorded statement; EMPTY (`{}`
    inline, or `""` on the command line) WITHDRAWS it, falling back to the target's own
    declaration; anything else replaces it. `{}` does both halves of the withdrawal
    with one spelling because they are one intent — "stop overriding" — and the record
    is then gone rather than merely ignored: this build stamps a fresh `build_meta`
    into the temp database that replaces `output`, and a withdrawal records no
    statement to carry over.

    Read off `output`, the live path, and therefore BEFORE the atomic swap, for the
    reason `_operator_excludes` and `_recorded_entry_patterns` are: the record lives in
    the database the swap is about to replace.

    @brief Resolve the tier-1 manifest statements in force for this build.
    @return The replayed option names.
    @version 1
    """
    ## NOT named `section`: that is `declaration.section`, imported into this module and
    ## used by the resolver two functions down. A local shadowing it here would read as
    ## the same lookup on a different subject.
    recorded_section = meta_section(output, OPTIONS_META_PREFIX)
    replayed: list[str] = []
    ## gh#366 adds `event_tags` to the loop. It is an INLINE MAPPING rather than a manifest
    ## path, and it belongs here rather than with `predefined` for a shape reason: the stored
    ## form is a DOCUMENT, so `recorded_document` reads it, while `predefined` is a LIST and
    ## needs `recorded_explicit`. One loop over two readers would have to branch per option,
    ## which is the shape that lets one option take the other's decoder.
    for option in (*MANIFEST_OPTIONS, OPTION_EVENT_TAGS):
        if getattr(args, option, None) is not None:
            continue
        recorded = recorded_document(recorded_section, option)
        if recorded is None:
            continue
        setattr(args, option, recorded)
        replayed.append(option)
    return sorted(replayed)


## @brief Which tier supplied each manifest document, for the `options.*` stamp.
## @param args Parsed CLI arguments, carrying any stated or replayed manifest.
## @param decl The repo's parsed `.clew.yaml`.
## @return Option name to its DocumentResolution, for `options_meta`.
## @version 1
## @req REQ-DDB-CONFIG-006
def _manifest_option_tiers(args: argparse.Namespace, decl: dict) -> dict[str, DocumentResolution]:
    """READS THE SAME TWO INPUTS `_declared_or_flag` DOES, in the same order, so the
    label stamped here cannot disagree with the document the stages were actually
    given. Both are pure functions of `(args, decl)`; a resolution computed from
    anything else would be a second opinion.

    THE STAMP IS THE OWNER'S CONDITION FOR ALLOWING THE REPLAY AT ALL. A replayed
    statement means the index carries a policy the repository does not declare, so two
    operators of one commit can hold different indexes — the shape of the defect
    rejected in gh#352, where an external tag was a property of the working copy. What
    makes it acceptable here is that a statement is DELIBERATE and RECORDED where the
    gitlink case was accidental and silent. Without these rows this becomes that
    defect. They may differ; they must never differ SILENTLY.

    @brief Resolve the recorded tier for every manifest option.
    @return The per-option resolutions.
    @version 1
    """
    return {
        option: resolve_document(
            explicit=getattr(args, option, None),
            declared=section(decl, option),
        )
        for option in MANIFEST_OPTIONS
    }


## @brief Resolve one manifest input: explicit statement, else the declaration.
## @param flag The tier-1 statement — a path string, the document inline as a mapping, or None.
## @param decl The repo's parsed `.clew.yaml`.
## @param name Declaration section to fall back to.
## @return A resolved Path, the stated or declared mapping, or None when neither is given.
## @version 3
## @req REQ-DDB-CONFIG-001
## @req REQ-DDB-CONFIG-008
def _declared_or_flag(flag: str | dict | None, decl: dict, name: str) -> Path | dict | None:
    """An explicit statement always WINS: the declaration is the repo's standing
    statement, a flag is a deliberate one-off override. The loaders accept
    either a path or an already-parsed mapping, so both routes feed the same
    parser and there is exactly one format per manifest.

    A TIER-1 STATEMENT MAY NOW ARRIVE AS THAT MAPPING (gh#360), not only as a path. It is
    passed through UNCHANGED rather than written to a temporary file: the loaders already
    take `Path | dict` for the declaration route, `treescan.manifest_key` already hashes a
    mapping canonically, and materialising a file would put the statement back inside a
    filesystem the caller may not be able to write to — the reason the inline form exists.
    `buildoptions._checked_manifest` has already validated the document by the time it gets
    here; an empty one is falsy and therefore a withdrawal to the declaration, matching the
    absent/empty/replaces convention elsewhere.

    @brief Prefer an explicit statement over the repo's declaration.
    @return Path (a stated path), mapping (a stated or declared document), or None.
    @version 3
    """
    if isinstance(flag, dict):
        return flag or section(decl, name)
    if flag:
        return Path(flag).resolve()
    return section(decl, name)


## @brief The scratch directory this build makes doxygen write into.
## @param args Parsed CLI arguments (uses --output).
## @return Absolute directory beside the output database.
## @version 4
## @dg_internal
def _doxygen_out_dir(args: argparse.Namespace) -> Path:
    """Keep doxygen's sqlite3/xml output beside the database clew is
    building, NEVER inside the target repo. A repo's Doxyfile legitimately
    declares its own OUTPUT_DIRECTORY for the repo's own tooling (a repo may use
    `docs/generated/doxygen`); honoring it made an index build mutate the
    working tree, collide between concurrent builds, and share a directory
    with output clew did not produce.

    Keyed to the INDEX CACHE when one is given, not to --output. The cache is
    what asserts "this tree is unchanged, so the previous doxygen output is
    still valid", so two builds sharing a cache must share the directory that
    output lives in — otherwise the warm build cannot find it and re-runs
    doxygen, silently losing the skip that makes a warm rebuild fast.

    Matches the naming `synthesize_doxyfile` already uses, so both paths land
    in the same place.

    @brief Resolve this build's doxygen scratch directory.
    @return Absolute path to `<cache-or-output-stem>.doxygen`.
    @version 4
    """
    base = Path(args.index_cache or args.output).resolve()
    return base.parent / (base.stem + ".doxygen")


## @brief Whether this build should use rustdoc instead of doxygen.
## @param repo_root Repository root.
## @return True when `repo_root` has a Cargo.toml and no discoverable Doxyfile.
## @version 2
## @dg_internal
def _is_rust_only_repo(repo_root: Path) -> bool:
    """Thin alias over `rustdoc.uses_rustdoc` — kept so callers in this module
    read as a build-routing decision rather than reaching into `rustdoc.py`
    directly. `init_command.py`'s doxygen doctor check shares the same
    underlying helper, so the two never drift on what "rust-only" means.

    @brief Decide whether this build should use rustdoc instead of doxygen.
    @return True when `repo_root` has a Cargo.toml and no discoverable Doxyfile.
    @version 2
    """
    return uses_rustdoc(repo_root)


## @brief Scan the indexed tree and reuse the cached doxygen output if it matches.
## @param cache Live index cache, or None when caching is disabled.
## @param preprocessor The resolved preprocessor configuration this index represents.
## @param timer Stage timer, marked once the tree scan and its hash are complete.
## @return Path to the doxygen SQLite output (cached or freshly generated).
## @version 8
## @dg_internal
def _doxygen_stage(
    doxyfile: Path,
    repo_root: Path,
    args: argparse.Namespace,
    cache: IndexCache | None,
    preprocessor: PreprocessorConfig | None = None,
    timer: StageTimer | None = None,
) -> Path:
    """doxygen has no incremental mode, so the only available win is SKIPPING
    it: hash every file under the declared INPUT roots plus the exact Doxyfile
    text we pipe in, and reuse the previous run's output when that tree hash
    matches AND the sqlite db it produced still exists. Anything short of that
    re-runs doxygen — a false hit here would ship a database describing code
    that no longer exists.

    THE PREDEFINED TEXT IS RENDERED ONCE and used for BOTH the hash and the run
    (gh#17). A changed `preprocessor:` declaration changes no source file and no
    Doxyfile, so if it were fed to the run and not to the hash, editing the
    declared macros would replay the previous configuration's parse out of cache
    and report success — a well-formed index of the variant the owner just stopped
    declaring. Rendering in one place is what makes the two impossible to diverge.

    THE TREE SCAN IS TIMED SEPARATELY from the doxygen run, because on a warm build
    they are the two candidates for the remaining cost and the aggregate cannot tell
    them apart: hashing every file under the INPUT roots happens whether or not
    doxygen is then skipped. With no cache there is no scan and no mark, so the
    caller's `doxygen` segment covers the whole stage — which is what happened.

    @brief Doxygen stage with tree-hash-based skip.
    @version 6
    """
    predefined = doxyfile_lines(preprocessor or PreprocessorConfig())
    if cache is None:
        return _run_doxygen_from_args(doxyfile, args, predefined)
    replace_input = getattr(args, "replace_input", False)
    roots, excludes = doxygen_input_roots(
        doxyfile,
        doxyfile.parent,
        args.extra_input,
        args.extra_exclude,
        replace_input,
    )
    summary = cache.scan(enumerate_tree(roots, excludes, repo_root))
    content = doxyfile_content_for(
        doxyfile,
        args.extra_input,
        args.extra_exclude,
        replace_input,
        predefined,
    )
    tree_sha = cache.tree_sha(content, [])
    ## The CONFIGURATION key, which unlike tree_sha does not move when a file is edited.
    ## Gating the splice on it is what stops a scope change from splicing into output built
    ## under the old scope (#399's aliasing, re-shipped once already).
    config_sha = cache.config_sha(content, [])
    if timer is not None:
        timer.mark("index_cache_scan")
    cached_db = cache.doxygen_get(tree_sha)
    if cached_db is not None:
        logger.info("doxygen: tree unchanged — reusing cached output %s", cached_db)
        return cached_db
    spliced = _incremental_doxygen(
        doxyfile, args, predefined, cache, summary, repo_root, config_sha
    )
    generated = spliced or _run_doxygen_from_args(doxyfile, args, predefined)
    ## A full run makes the index exact again, so it CLEARS the counter; a splice adds one
    ## generation of bounded drift. Recorded here rather than inside the splice because
    ## this is the only place that knows which of the two actually ran.
    cache.record_splice(reset=spliced is None)
    cache.doxygen_put(tree_sha, generated, config_sha)
    return generated


## @brief Run every build stage against one (temp) output DB path.
## @param timer Stage timer; one `mark` closes each stage below. A fresh one when omitted.
## @version 51
## @req REQ-DDB-PIPE-001
## @req REQ-DDB-MCP-004
## @req REQ-DDB-CONFIG-007
## @req REQ-DDB-CONFIG-001
def _build_stages(
    output: Path,
    doxyfile: Path,
    args: argparse.Namespace,
    cache: IndexCache | None = None,
    timer: StageTimer | None = None,
) -> None:
    """Execute the doxygen → augmentation pipeline against `output`.

    `output` is a temp DB during a live build (see _run_pipeline's atomic
    swap); all stages mutate it in place. `cache` (when given) makes the
    per-file AST stages incremental; every CROSS-FILE stage below —
    reachability, thread membership, boundary annotation, requirements — is
    always recomputed, because they depend on the whole assembled graph.

    EVERY STAGE IS FOLLOWED BY ONE `timer.mark`, which closes the segment that just
    ran. A stage added without one is not reported missing — its cost is charged to
    the neighbour that marks next — so `tests/test_stage_timings.py` pins the recorded
    name set against a real build rather than trusting the convention to hold.

    THE TEN PER-FILE AST STAGES SHARE ONE PARSE (gh#358): `warm_harvest_plan` runs
    above the first of them and fills each stage's own cache row off a single parse
    per file. It changes no stage's position and emits nothing — see harvest.py.

    @brief Execute every augmentation stage against one output database.
    @version 46
    """
    timer = timer or StageTimer()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else doxyfile.parent
    # The repo's own standing declaration. Discovered from --repo-root, which BOTH entry
    # points already pass — so the MCP server picks these up with no argv plumbing,
    # closing the gap where every override was CLI-only and the built-in defaults were
    # therefore the whole policy on the primary surface.
    #
    # LOADED HERE, above the doxygen stage, because gh#17's `preprocessor:` section
    # decides what doxygen is even asked to parse — unlike every other section, which
    # annotates an already-built graph. It was previously read twice further down; one
    # read now serves all three consumers.
    decl = _with_stated_sections(load_declaration(repo_root, args.guard_config), args)
    _apply_declared_paths(args, decl, repo_root)
    preprocessor = resolve_preprocessor(repo_root, decl, getattr(args, "predefined", None))
    timer.mark("declaration")
    if _is_rust_only_repo(repo_root):
        # Doxygen has no Rust parser — clew/rustdoc.py fills the same
        # path/refid/memberdef tables from `cargo +nightly rustdoc` JSON
        # instead, writing straight to `output` rather than a scratch db a
        # doxygen-style copy_database step would then relocate.
        run_rustdoc(repo_root, output)
        timer.mark("doxygen")
        timer.mark("copy")
        timer.mark("sanitize")
    else:
        generated_db = _doxygen_stage(doxyfile, repo_root, args, cache, preprocessor, timer)
        timer.mark("doxygen")
        copy_database(generated_db, output)
        timer.mark("copy")
        # Repair any non-UTF-8 bytes doxygen wrote into description columns
        # BEFORE augmentation / shipping — see sanitize_doxygen_text.
        sanitize_doxygen_text(output)
        timer.mark("sanitize")

    if args.enrich:
        enrich_path = Path(args.enrich).resolve()
        if not enrich_path.exists():
            logger.error("Enrichment file not found: %s", enrich_path)
            sys.exit(1)
        enrich_database(output, enrich_path)
        timer.mark("enrich")

    fix_doxygen_paths(output, doxyfile, repo_root)
    timer.mark("fix_paths")
    repair_attribute_named_functions(output, repo_root)
    timer.mark("repair_names")
    ingest_supplementary_docs(output, repo_root)
    timer.mark("supplementary_docs")
    ## gh#18. IMMEDIATELY AFTER prose ingestion and not before, because
    ## `ingest_supplementary_docs` DROPs and recreates `supplementary_docs` on every
    ## build: run above it, the Kconfig help chunks would be inserted and then deleted,
    ## and the observable result would be an empty `search_prose` with no error anywhere.
    ##
    ## The configuration SPACE (what variants exist) — distinct from `preprocessor`
    ## above, which resolved which variant this index IS. Inert for a repo with no
    ## Kconfig: no table created, no prose chunk, no `kconfig.*` row.
    kconfig_model = import_kconfig(output, repo_root, decl)
    timer.mark("kconfig")
    ## gh#358, and the ONE stage here that emits nothing. Ten stages below each walk
    ## every indexed file's AST; each used to drive its own full-tree harvest, so a
    ## cold build parsed every file ten times — three minutes on 8,435 files, nine
    ## tenths of it redundant. This parses each file ONCE and warms each stage's OWN
    ## cache row (the key is NOT merged — see harvest.py on why a combined key is
    ## either all-or-nothing or silently lossy).
    ##
    ## MUST sit above `import_kconfig_gates`, the first of the ten, and below
    ## `fix_doxygen_paths`, which is what makes `path.name` resolvable against
    ## repo_root. Every declaration the ten stages need is resolved here, once, and
    ## the harvester OBJECTS are handed to the stages below rather than rebuilt: an
    ## equal-but-separate harvester is a chance for the warmed key and the read key
    ## to disagree, and that disagreement is invisible (the stage would simply parse
    ## for itself and produce identical rows, slowly).
    ##
    ## The five resolutions are hoisted from further down for that reason alone;
    ## each is pure, and the stage call sites still read the same locals.
    lock_source = _declared_or_flag(args.locks, decl, SECTION_LOCKS)
    thread_patterns = _declared_or_flag(args.thread_patterns, decl, SECTION_THREADS)
    shared_key_patterns = _declared_or_flag(args.shared_key_patterns, decl, SECTION_SHARED_KEY)
    dispatch_source = _declared_or_flag(args.dispatch, decl, SECTION_DISPATCH)
    dispatch = load_dispatch_manifest(dispatch_source)
    # `shared_key_wrappers` IS the argument-keyed half of the shared-key manifest,
    # so the dispatch declaration feeds the SAME matcher rather than a second one.
    #
    # HELD IN A LOCAL because it is now used THREE times — the harvest plan, the
    # inferred pass, and the alias-prefix resolution stamped below. Separately-built
    # expressions could drift into resolving different things; one local cannot.
    shared_key_wrappers = shared_key_document(dispatch)
    mqtt_dispatch = _declared_or_flag(args.mqtt_dispatch, decl, SECTION_MQTT)
    ## WHICH TIER supplied each of the five documents resolved just above, captured HERE
    ## rather than at the stamp 300 lines down, from the same `args` and `decl` those
    ## calls read. Computing it beside them is what keeps the label and the document one
    ## decision; re-deriving it later from anything else would be a second opinion free
    ## to disagree with what the stages were actually given.
    manifest_tiers = _manifest_option_tiers(args, decl)
    plan = build_harvest_plan(
        lock_patterns=lock_source,
        thread_patterns=thread_patterns,
        shared_key_patterns=shared_key_patterns,
        shared_key_wrappers=shared_key_wrappers,
        dispatch=dispatch,
        dispatch_key=manifest_key(dispatch_source),
        mqtt_dispatch=mqtt_dispatch,
    )
    warm_harvest_plan(output, repo_root, plan, cache)
    timer.mark("shared_parse")
    ## gh#18 part 3, and INDEPENDENT of the line above on purpose: a gate on a symbol no
    ## Kconfig declares is dead code behind a symbol nobody can set, which is a finding
    ## worth keeping rather than filtering away — and this layer still works when the
    ## Kconfig parse failed, so a consumer sees the gating structure with `kconfig.error`
    ## explaining the empty space beside it.
    ##
    ## gh#390 — `preprocessor.macros` is passed to LABEL the rows, never to select them.
    ## The same set already feeds doxygen's PREDEFINED and was then discarded, so the
    ## build knew which symbols the index REPRESENTS and threw the answer away. Passing
    ## it here is the whole of that fix: the harvest is unchanged by it, and a target
    ## that declares nothing still gets every gate, marked `undeclared`.
    import_kconfig_gates(output, repo_root, cache, declared=preprocessor.macros)
    timer.mark("kconfig_gates")
    ## gh#11. MUST sit above every call-edge layer: those resolve their endpoints to
    ## memberdef rowids, so a symbol recovered afterwards would get a row and no
    ## edges — the same defect in a subtler form. And below
    ## `repair_attribute_named_functions`, whose merges and renames decide the
    ## doxygen body spans this stage dedups against.
    ##
    ## Above `report_index_coverage` deliberately too, so the barren ratio measures
    ## the index a consumer will actually query rather than doxygen's intermediate
    ## state. The DOCUMENTED ratio is measured separately and reported alongside it,
    ## so recovering the graph cannot silence the advice to declare PREDEFINED.
    recover_ast_symbols(output, repo_root, cache)
    timer.mark("ast_symbols")
    ## AFTER prose ingestion, deliberately. Coverage excludes files that yielded PROSE
    ## instead of symbols — a markdown file is not barren, it is not code — and it can
    ## only do that once `supplementary_docs` is populated. Measured on mbedtls: run
    ## before this line, 27 substantive `.md` files read 100% barren and inflate the
    ## headline ratio. `report_index_coverage` subsumes the older
    ## `warn_if_no_function_bodies` call that used to sit above.
    ## gh#335, and it MUST precede `report_index_coverage`. Coverage reports FIRST
    ## PARTY by default, which it can only do once the rows carry the tag — run the
    ## other way round, a repo that vendors a submodule gets one averaged ratio over
    ## two codebases, which is not a noisy measurement but a false one.
    external_tagged, external = stamp_external_provenance(output, repo_root)
    timer.mark("external")
    coverage = report_index_coverage(output, repo_root)
    timer.mark("coverage")
    ## gh#10. BELOW `report_index_coverage` and this ordering is load-bearing in a way
    ## that is easy to miss: coverage excludes files that yielded PROSE instead of
    ## symbols, by reading `supplementary_docs`. Run above this line, every source file
    ## with a module docstring would count as "yielded prose", and the barren ratio —
    ## whose entire job is to say how much of the index is empty — would improve without
    ## one extra symbol being indexed. Also below `ingest_supplementary_docs`, which
    ## DROPs that table; above it these rows would be inserted and then deleted.
    ingest_file_docs(output, repo_root)
    timer.mark("file_docs")
    build_call_edges(output)
    timer.mark("call_edges")
    import_macro_hop_edges(output)
    timer.mark("macro_hop_edges")
    import_ast_call_edges(output, repo_root, cache)
    timer.mark("ast_call_edges")
    ## AFTER the call-edge stages, because it joins recovered identifiers against `memberdef`
    ## and a macro recovered by `ast_symbols` must already have its row (gh#9).
    import_ast_macro_refs(output, repo_root, cache)
    timer.mark("macro_refs")
    ## `preprocessor` is passed for gh#35: Layer 4 needs it to choose which `#if` branch a
    ## conditional function-pointer binding belongs to. It was resolved 60-odd lines above
    ## and reached only the Doxyfile and `build_meta`, so branch selection was making its
    ## decisions from a configuration that was sitting in scope, unread — the same
    ## "declaration reachable only from argv" shape the no-hardcoding mandate names.
    import_callback_registration_edges(output, repo_root, cache, preprocessor)
    timer.mark("callback_edges")

    ## Via `_declared_or_flag` like every other section (resolved into `lock_source`
    ## above, with the rest of the harvest plan's declarations). It previously read
    ## the declaration DIRECTLY, so `locks` was the one declared section with no CLI
    ## route — to test a third-party clone's lock idiom you had to write a
    ## declaration file INTO the clone. Every other manifest already honoured
    ## "an explicit flag beats the repo's standing declaration"; this one silently
    ## did not.
    extract_locks(
        output,
        repo_root,
        lock_source,
        cache,
        plan.locks,
    )
    timer.mark("locks")

    # Layer 6 — the declared indirect-dispatch recovery. Ordering is load-bearing
    # in BOTH directions: it reads the call edges Layers 1-4 produced (a virtual
    # call DOES land on the interface method, it just stops there), and its
    # synthetic edges have to exist before extract_threads' membership closure
    # and mark_reachability's seeded BFS run below — that cascade is what lets one
    # declared `register_via` move a whole dispatched sub-graph from orphan to
    # live with no liveness-specific special case.
    import_declared_dispatch_edges(
        output, repo_root, dispatch, cache, manifest_key(dispatch_source), plan.dispatch
    )
    timer.mark("dispatch_edges")

    ## gh#26. BELOW every layer that can produce a non-fuzzy ANCHOR — including
    ## macro_hop, fnptr and the declared dispatch directly above — because the pass
    ## deletes an AST name-guess only when a stronger layer named a different callee
    ## for the same call site. Judging the fan-out before a later layer has spoken
    ## would spare rows that layer disproves, so this cannot move up beside the
    ## self-edge guard inside Layer 3.
    ##
    ## Its position ABOVE extract_threads and mark_reachability is free rather than
    ## load-bearing, and that is worth stating because it is the checkable safety
    ## property of the whole stage: only `fuzzy` rows are deleted, and both the
    ## membership closure and the seeded liveness BFS traverse non-fuzzy edges only.
    ## Liveness and termini therefore cannot move, whichever side of them this runs on.
    prune_dominated_fuzzy_call_edges(output)
    timer.mark("dominated_fuzzy")

    # R1 thread layer runs after the call-edge layers (membership BFS needs
    # the complete non-fuzzy call graph, including fnptr edges) and before
    # the boundary annotation below.
    extract_threads(output, repo_root, thread_patterns, cache, plan.threads)
    timer.mark("threads")

    import_shared_key_edges_inferred(
        output,
        repo_root,
        shared_key_patterns,
        cache,
        shared_key_wrappers,
        plan.shared_key,
    )
    timer.mark("shared_key_inferred")
    data_model = (
        Path(args.data_model).resolve()
        if args.data_model
        else declared_path(decl, SECTION_DATA_MODEL, repo_root)
    )
    import_shared_key_edges_declared(output, data_model)
    timer.mark("shared_key_declared")

    ## gh#351, and it sits HERE for one reason: its `observed` column is a join against the
    ## shared-key vocabulary the two stages above just wrote. Above them every row would
    ## read `observed = 0` — a plausible answer saying a repository touches none of its own
    ## data model, which is worse than an absent one.
    ##
    ## This reads the GENERATOR'S OWN manifests, never its output. The generated
    ## `dm_full.yaml` is a BUILD ARTIFACT: a built tree carries it and a bare clone does
    ## not, so reading it would make the index a function of whether somebody ran a build
    ## and two indexes of ONE COMMIT would disagree about which keys exist. Same defect
    ## class as an external tag that was a property of the working copy.
    ##
    ## THE BUILD'S OWN EXCLUDE LIST is handed in rather than re-derived. `args.extra_exclude` is
    ## the list `_fold_scope_into_args` already gave doxygen, so the catalog cannot see a
    ## subtree the index does not — which is a correctness property here, not tidiness: a
    ## generated data model's OUTPUT lands in a build directory, and this layer must read the
    ## generator's sources and nothing it produced. Re-deriving the scope would add a third
    ## `git ls-files` walk AND allow the two answers to differ.
    ##
    ## MEASURED COST OF NOT BOUNDING THIS WALK: one control target vendors a YAML parser's
    ## benchmark corpus under `build/`, including a 10.7 MB pathological document, and the first
    ## version of this stage did not finish in twenty-five minutes at full CPU.
    data_model_set = import_data_model_keys(
        output, repo_root, tuple(Path(p) for p in (args.extra_exclude or []))
    )
    timer.mark("data_model_keys")

    import_mqtt_dispatch_edges(output, repo_root, mqtt_dispatch, cache, plan.subscribe)
    timer.mark("mqtt_dispatch")

    # Author-DECLARED event edges (@emits/@handles via the repo's own xrefitem
    # ALIASES). Must precede annotate_thread_boundaries so event edges acquire
    # crosses_thread/to_thread_id like every other shared-key row.
    #
    # The vocabulary is passed from the declaration, and this call site is the whole
    # of gh#317: the parameter had existed since the importer was written and NOTHING
    # ever supplied it, so the 17 built-in English verbs were the entire policy with no
    # route to change them — the "declaration reachable only from argv" shape, in its
    # purest form, since here there was not even an argv route. There is deliberately
    # no CLI flag: a bus vocabulary is a standing property of a repo, not a one-off.
    #
    # HOISTED for the same reason `shared_key_wrappers` above is: the diagnostics stamp
    # re-derives the unclaimed aliases from this SAME vocabulary, and two separately-built
    # expressions could drift into classifying against different ones — which would report
    # a repo's tags as unclaimed while the importer had in fact claimed them.
    #
    # TIER 1 BEATS TIER 2 (gh#332). `getattr` rather than `args.event_tags` because the
    # ARGUMENT PARSER DOES NOT DEFINE THIS DEST — there is deliberately no `--event-tags`
    # flag, so the attribute exists only when an embedding caller stated one. That absence
    # is exactly why this key needed a route: before, the only way to state a bus
    # vocabulary was to edit the target repo's own tree.
    event_tags = getattr(args, "event_tags", None) or declared_event_tags(decl)
    import_event_edges(output, doxyfile, event_tags)
    timer.mark("event_edges")

    # Annotate crosses_thread / to_thread_id once all shared-key rows exist.
    annotate_thread_boundaries(output)
    timer.mark("thread_boundaries")

    requirements_yaml = Path(args.requirements).resolve() if args.requirements else None
    # Declaration-driven requirement-tag handling: explicit --guard-config, else the
    # UNIFIED discovery in `precommit` — root, the path the pre-commit hook's args
    # declare, then convention (gh#16). This site used to hardcode the root literal,
    # one of three independent copies; `load_guard_config` returns None (→ permissive
    # fallback) when nothing is found, so builds still work config-free, and
    # `_logged` now says which config was used or where it looked and failed.
    # `repo_root` travels with the path so a VERSION SKEW can name the `rev:` the target
    # pins as well as the release we import (gh#32) — a report with only our half of the
    # story reads as the target author's mistake.
    guard_cfg = load_guard_config(
        discover_guard_config_logged(repo_root, args.guard_config).path, repo_root
    )
    req_id_pattern = resolve_req_id_pattern(guard_cfg)
    ## gh#368 follow-up: ONE resolver for both doors. The MCP server used to compose
    ## `repo/"requirements.yaml"` and pass it as this flag, which put the CONVENTION above
    ## the DECLARATION — the opposite of every other precedence in this pipeline, and only
    ## through one of the two entry points. `resolve_catalog_path` owns the whole order now:
    ## flag > declaration > convention > nothing.
    requirements_yaml = requirements_yaml or resolve_catalog_path(guard_cfg, repo_root)
    ingest_requirements_yaml(output, requirements_yaml, guard_cfg)
    timer.mark("requirements")
    import_req_edges(output, req_id_pattern)
    timer.mark("req_edges")
    import_req_test_edges(output)
    timer.mark("req_test_edges")

    # Python entry points are STRUCTURAL, not name-shaped: a `__main__` guard's
    # callee has doxygen attributing the guard call to the function ITSELF, so it
    # holds a non-fuzzy incoming edge and the zero-incoming source cannot seed it
    # (measured on the Python real codebase: its `_main` was a false orphan).
    # Empty for a repo
    # with no Python and no pyproject.toml, so the C/C++ seed set is unchanged.
    ## Held rather than inlined, because the SAME resolution has to reach two places:
    ## the BFS that uses the patterns, and the stamp that records which tier chose
    ## them. Inlining it would let the two drift — the index would describe seeds it
    ## was not built from — which is the failure the recording exists to prevent.
    entry_seeds = _entry_patterns(args, decl)
    mark_reachability(
        output,
        entry_patterns=list(entry_seeds.values),
        extra_seeds=python_entry_seeds(output, repo_root, cache),
    )
    timer.mark("reachability")

    ## AFTER the path table is complete, and stamped into the index because the resolver runs
    ## against a database with no repo root and no `.clew.yaml` to re-read.
    test_scope = _test_paths(args, decl)
    with sqlite3.connect(output) as _ts_conn:
        mark_test_scope(_ts_conn, list(test_scope.values))
    timer.mark("test_scope")

    # Stamp the build-version signature last so a partial build never leaves a
    # DB looking current. Consumers' freshness checks treat a mismatch as stale.
    #
    # The SCOPE DECISION rides along, because the pipeline already computed it and was
    # throwing it away into the log. A consumer could see what was indexed and never why —
    # measured as the only clearly actionable gap in the entropic grid's 56 marks.
    from .signature import write_build_signature

    ## HOISTED OUT OF THE CALL BELOW so it gets its own timing segment, because it is
    ## not the cheap dictionary build it reads as: on the whole-repo tier it re-derives
    ## the scope, which runs `git ls-files` and walks the tree a second time.
    scope_meta = _scope_provenance(repo_root, args)
    ## gh#335. Carried in the SCOPE section because it is a fact about the boundary:
    ## `roots` says what was indexed, `excludes` what was not, and this says which
    ## part of what WAS indexed belongs to somebody else. Stamped from the return of
    ## the tagging stage rather than re-derived, so the list and the column cannot
    ## disagree — the same reasoning that made `_scope_provenance` stop reading the
    ## tier out of `args`. The count rides along because a reader needs to know
    ## whether a named root actually contributed rows or merely exists.
    if external:
        scope_meta[EXTERNAL_ROOTS_META_KEY] = SCOPE_LIST_SEPARATOR.join(external)
        scope_meta["external_files"] = str(external_tagged)
    timer.mark("scope_provenance")

    ## Coverage rides along for the same reason scope does: a number that lives only in
    ## a warning is gone by the time anyone queries the index, which is exactly the
    ## defect persisting scope provenance fixed.
    ##
    ## The measurement from above is REUSED rather than retaken. Verified rather than
    ## assumed: the only writes to `memberdef` anywhere in the pipeline are in
    ## `repair_attribute_named_functions`, which runs before it, so the earlier value
    ## still describes the shipped index — and re-measuring would cost a second
    ## line-count pass over every indexed file (570 of them on mbedtls).
    ## And WHICH VARIANT of those files the index describes (gh#17). The third leg of
    ## the same argument scope and coverage make: a codebase with a config header has a
    ## different set of FUNCTIONS per configuration, so two indexes of one repo can
    ## disagree about whether a symbol exists. Empty for a target that declares no
    ## `preprocessor:` section, in which case no `preprocessor.*` row is written at all.
    write_build_signature(
        output,
        scope=scope_meta,
        coverage=coverage.as_meta(),
        preprocessor=preprocessor.as_meta(),
        ## And WHICH VARIANTS EXIST (gh#18) — the one section here that is a fact about
        ## the REPOSITORY rather than about this index. Carries `kconfig.error`, so a
        ## Kconfig that was found and could not be parsed is distinguishable from a repo
        ## that has none; both otherwise present as zero rows.
        kconfig=kconfig_model.as_meta(),
        ## The NINTH leg (P0.1), and the only section recording what an OPERATOR stated rather
        ## than what the repository holds. Absent for a build with no `--declare`, which the
        ## falsy-drop rule turns into no row at all — honestly "nothing was stated" rather
        ## than a statement that was made and was blank.
        declaration=getattr(args, "declaration_meta", None),
        ## The SEVENTH leg (gh#351), and it is stamped from the STAGE'S OWN RETURN rather
        ## than re-derived. `diagnostics.py` states when re-deriving is safe — when no column
        ## in the database can disagree with the value — and that does not hold here: every
        ## count in this section describes rows in `data_model_keys`, so a second discovery
        ## walk could report a set the table does not hold. The same rule made gh#335's
        ## external roots carry the tagging stage's return.
        data_model=data_model_set.as_meta(),
        ## The SIXTH leg, and the first that records a POLICY rather than a
        ## measurement (gh#319). `scope.*` says which files were indexed and
        ## `preprocessor.*` which variant of them — `options.*` says which TIER chose
        ## a layered setting, so a consumer reading an unexpected liveness split can
        ## tell "this repo declared its own dispatch vocabulary" from "these are our
        ## built-in guesses". `options_meta` refuses anything but a resolution, so a
        ## value whose tier was dropped on the way here cannot be stamped.
        ##
        ## `key_alias_prefixes` is RE-RESOLVED here rather than carried, because the
        ## value the pass uses is computed several frames down inside
        ## `import_shared_key_edges_inferred` and threading it back out would widen
        ## that signature for a metadata row. `resolve_key_alias_prefixes` is pure and
        ## both calls take the same two locals, so they cannot disagree — and
        ## `tests/test_tiers.py` pins them against each other rather than trusting it.
        ##
        ## THE FIVE MANIFEST OPTIONS JOIN IT (gh#364), and their rows are what makes the
        ## replay above legible. A statement that survives a rebuild means this index
        ## carries a policy the REPOSITORY does not declare, so two operators of one
        ## commit can hold different indexes — the shape of the defect rejected in
        ## gh#352, acceptable here only because it is deliberate AND recorded. These rows
        ## are that record; `status` surfaces them, and `tiers.stated_options` names them
        ## without a reader having to know which tier word matters.
        options=options_meta(
            **{
                OPTION_ENTRY_PATTERNS: entry_seeds,
                OPTION_KEY_ALIAS_PREFIXES: resolve_key_alias_prefixes(
                    shared_key_patterns, shared_key_wrappers
                ),
                ## gh#366. WITHOUT THESE TWO ROWS THE REPLAY HAS NOTHING TO READ — the
                ## record and the read-back are one mechanism, and stamping was the half
                ## that was missing. `predefined` resolves LAYERED (a list, over the
                ## declared `preprocessor.predefined`); `event_tags` resolves as a DOCUMENT
                ## (a mapping), which is why they take different resolvers rather than one.
                OPTION_PREDEFINED: resolve_layered(
                    facts=(),
                    explicit=getattr(args, OPTION_PREDEFINED, None),
                    declared=string_list(
                        section(decl, SECTION_PREPROCESSOR) or {}, OPTION_PREDEFINED
                    ),
                ),
                OPTION_EVENT_TAGS: resolve_document(
                    explicit=getattr(args, OPTION_EVENT_TAGS, None),
                    declared=section(decl, SECTION_EVENT_TAGS),
                ),
                **manifest_tiers,
            }
        ),
        ## The SEVENTH leg, and the first that records what is NOT here (gh#320). The
        ## other six describe rows; this names what the build searched for and did not
        ## claim, so a sparse causal layer can be told apart from a repo that has no
        ## dataflow. Re-derived from the same locals the stages were given — the
        ## `key_alias_prefixes` argument immediately above, applied to a second value.
        diagnostics=collect_diagnostics(
            output,
            doxyfile,
            shared_key_patterns,
            shared_key_wrappers,
            event_tags,
            ## gh#385 — the same declaration the locks stage ran with, so the hint cannot
            ## suggest declaring something this build already had.
            getattr(args, "locks", None),
        ).as_meta(),
    )
    timer.mark("signature")


## @brief Record the vendored paths a repository declares, and which of them exist.
## @param root Repository root, already resolved.
## @param rel Callable rendering a path repo-relative.
## @param args Parsed CLI arguments, carrying the guard config and any stated sections.
## @return Mapping of `vendored_*` keys, empty when nothing was declared.
## @version 1
## @dg_internal
def _vendored_scope(root: Path, rel: Any, args: argparse.Namespace) -> dict[str, str]:
    """ONLY PATHS THAT EXIST ARE NAMED, and the rest are COUNTED. gh#335 nearly published a
    machine path this way: the nested-tree walk saw every directory on disk including ones
    another rule excluded, and the first version stamped an excluded target's directory name
    into `scope.external_roots` — a path the build was configured to leave out, published by
    the feature that found it. The rule that came out of it is "report only roots that own at
    least one indexed row; count the rest", and the same rule applies to a DECLARED path that
    is simply wrong: a typo names a directory that is not there, and echoing it back as though
    it were found is how a declaration gets believed.

    So a declared path that does not exist is dropped from the list and shows up in
    `vendored_declared_missing`, which is the actionable half — it is the difference between a
    repository with no vendored code and one whose declaration nobody checked.

    @brief Flatten declared vendored paths, naming only the ones present.
    @return Mapping of `vendored_*` keys.
    @version 1
    """
    ## RE-DERIVED FROM THE SAME INPUTS the stages got, not carried. `diagnostics.collect`
    ## makes this argument for itself: "CALLED WITH THE SAME INPUTS THE STAGES GOT, which is
    ## the whole correctness argument for re-deriving rather than carrying." And the merged
    ## form is required, not the file alone — a `vendored:` stated through `--declare` (which
    ## is how a third-party target declares anything at all, since its tree must stay
    ## byte-identical) lands via `_with_stated_sections` and would otherwise be invisible here.
    ## TWO TIERS, in the order every other option uses. Tier 1 is `args.vendored`, which
    ## `apply_options` sets from a stated `vendored:` — the only route open to a third-party
    ## target, whose tree must stay byte-identical and so cannot carry a `.clew.yaml`.
    ## Tier 2 is that file, for a repository declaring its own. An empty stated list WITHDRAWS
    ## the statement and lets tier 2 answer, matching the three-state rule the rest of the
    ## surface follows.
    stated = getattr(args, "vendored", None)
    if stated is None:
        try:
            stated = (
                load_declaration(root, getattr(args, "guard_config", None)).get(SECTION_VENDORED)
                or ()
            )
        except Exception as exc:  # pragma: no cover - metadata must not break a built index
            logger.warning("vendored paths not recorded (%s)", exc)
            return {}
    if isinstance(stated, str):
        stated = [stated]
    paths = [str(p).strip() for p in stated if str(p).strip()]
    if not paths:
        return {}
    present = sorted({rel(root / p) for p in paths if (root / p).exists()})
    missing = sorted({p for p in paths if not (root / p).exists()})
    out = {"vendored_declared": SCOPE_LIST_SEPARATOR.join(sorted(set(paths)))}
    if present:
        out["vendored_roots"] = SCOPE_LIST_SEPARATOR.join(present)
    if missing:
        ## COUNTED AND NAMED, because a declaration that matches nothing is a finding rather
        ## than a no-op, and it is the one an author can act on.
        out["vendored_declared_missing"] = SCOPE_LIST_SEPARATOR.join(missing)
    return out


## @brief Read the target's own declared documentation scope.
## @param root Repository root, already resolved.
## @param rel Callable rendering a path repo-relative.
## @param stated The Doxyfile the build resolved, when there is one.
## @return Mapping of `doxyfile_*` keys, empty when the repo declares no doc scope.
## @version 1
## @dg_internal
def _doxyfile_scope(root: Path, rel: Any, stated: str | None = None) -> dict[str, str]:
    """The scope the REPOSITORY declares for its own documentation, as opposed to the scope
    this index used. Three keys, all absent when the repo ships no Doxyfile.

    A SCOPE STATEMENT HAS THREE KEYS AND READING ONE ANSWERS LESS THAN IT LOOKS. gh#333
    replaced INPUT and cleared EXCLUDE, and entropic's surviving `EXCLUDE_PATTERNS` dropped a
    submodule again on the way in — a build that exited 0 and indexed 16 vendored files. The
    same trio decides what a repo's own doc build covers, so recording INPUT alone would
    reproduce that error one layer over: `FILE_PATTERNS = *.h` is the whole answer to
    "headers only?" and lives in neither of the other two.

    Values are joined with the scope list separator so a reader gets the list rather than a
    single first entry, and every path is repo-relative for the reason `_scope_provenance`
    documents at length: anything stored here is published over MCP.

    @brief Read the target's own declared documentation scope.
    @return Mapping of `doxyfile_*` keys, empty when the repo ships no Doxyfile.
    @version 1
    """
    ## THE STATED PATH FIRST, and it is what makes this reachable at all on a real target.
    ## Discovery deliberately REFUSES to guess — root, then `docs/`/`doc/`, then nothing —
    ## because it was once caught selecting a test fixture's Doxyfile to index a whole
    ## project. Mbed-TLS keeps its at `doxygen/mbedtls.doxyfile`, which is none of those and
    ## is not even named `Doxyfile`, so discovery correctly finds nothing there and this
    ## section would stay empty on the one target the question is asked about.
    ##
    ## `args.doxyfile` is SAFE to read here, which took checking rather than assuming: it is
    ## set from discovery or from the operator's `--doxyfile`, and the SYNTHESIZED file for a
    ## repo that ships none is a separate local passed straight to `_build_stages`. So this
    ## cannot stamp our own synthesized INPUT as the repository's declared doc scope — the
    ## failure mode that made me reach for discovery-only in the first place.
    try:
        found = Path(stated).resolve() if stated else discover_doxyfile(root)
    except Exception as exc:  # pragma: no cover - discovery is already fail-soft
        logger.warning("target doxyfile scope not recorded (%s)", exc)
        return {}
    if found is None or not found.is_file():
        return {}
    out = {"doxyfile_path": rel(found)}
    ## `declared_file_patterns` ALREADY EXISTS FOR THIS, and its own docstring says so:
    ## "KEPT BECAUSE THE DECLARATION IS STILL A FACT, just no longer a policy. A target that
    ## publishes an API reference with `FILE_PATTERNS = *.h` has said something true about its
    ## DOCUMENTATION target, and a consumer asking 'why does the index hold more than the docs
    ## do' deserves that answer rather than silence." It was written, kept deliberately, and
    ## then read by nobody — the capability was there and only the persistence was missing,
    ## which is this repo's own lesson about checking before building.
    ##
    ## It returns EMPTY rather than doxygen's defaults when nothing is declared, so
    ## "not recorded" stays distinct from "recorded as the default" — exactly the three-state
    ## discipline the falsy-drop rule below depends on.
    patterns = declared_file_patterns(found)
    if patterns:
        out["doxyfile_file_patterns"] = SCOPE_LIST_SEPARATOR.join(patterns)
    for key, meta in (("INPUT", "doxyfile_input"), ("EXCLUDE_PATTERNS", "doxyfile_excludes")):
        values = parse_doxyfile_values(found, key)
        if values:
            out[meta] = SCOPE_LIST_SEPARATOR.join(values)
    return out


## @brief Flatten the resolved scope into build_meta values, repo-relative.
## @param repo_root Repository root, or None when unknown.
## @param args Parsed CLI arguments, which carry the tier the build actually took.
## @return {source, reason, roots, excludes, operator_excludes, doxyfile_*} as strings; empty when nothing was resolved.
## @version 8
## @req REQ-DDB-CONFIG-001
def _scope_provenance(repo_root: Path | None, args: argparse.Namespace) -> dict[str, str]:
    """A PURE FUNCTION OF THE REPO AGAIN (gh#333). It used to read the tier from
    `args.index_whole_repo`, because whether the whole-repo tier won depended on
    whether a Doxyfile had been resolved several hundred lines away — and re-deriving
    from `repo_root` alone would then stamp `source: doxyfile` on a build that indexed
    the whole repository. `derive_scope` no longer consults the Doxyfile at all, so
    the two cannot disagree and the coupling is deleted rather than maintained.

    `--scope doxyfile` IS STILL A REAL ANSWER and is reported as one. It is now an
    explicit operator opt-out rather than the default, and under it `_apply_scope`
    folds nothing — so stamping the resolved whole-repo tier would describe a scope
    this build did not use.

    FAILS SOFT. Scope provenance is metadata about a build that has already succeeded; a
    derivation that raises here must not destroy the index it is describing. Returning {}
    means "not recorded", which the reader distinguishes from a recorded-and-empty decision.

    REPO-RELATIVE, ALWAYS. `DerivedScope` holds absolute paths, and the first version of this
    stamped them verbatim — reintroducing exactly the machine-layout disclosure that forced
    the build-version-9 bump, where `path.name` stored the builder's home directory in 112 of
    112 rows. `reason` is scrubbed too: it embeds the config's absolute path in its own text.
    A stored path is published over MCP; the build machine's layout is not the consumer's
    business.

    THE OPERATOR'S EXCLUSIONS ARE A SEPARATE KEY, not folded into `excludes`, and this
    is the one value here that is read BACK rather than only displayed: the next build
    replays it, because scope is otherwise re-derived from scratch every time. Merging
    it into the derived list would both destroy the distinction a reader needs and
    make the replay re-state the walker's prunings as operator decisions.

    @brief Flatten the resolved scope into build_meta values, repo-relative.
    @return Mapping of provenance keys to strings.
    @version 6
    """
    if repo_root is None:
        return {}
    root = Path(repo_root).resolve()
    if getattr(args, "scope", SCOPE_FROM_GUARD) != SCOPE_FROM_GUARD:
        return {
            "source": SOURCE_DOXYFILE,
            "reason": (
                "--scope doxyfile was passed, so the indexed tree is the Doxyfile's own "
                "INPUT list. That is a DOCUMENTATION target: it states what the repo "
                "publishes, not what can be reasoned about."
            ),
            OPERATOR_EXCLUDES_KEY: SCOPE_LIST_SEPARATOR.join(getattr(args, "exclude", None) or ()),
        }
    try:
        derived = derive_scope(root, getattr(args, "guard_config", None))
    except Exception as exc:
        logger.warning("scope provenance not recorded (%s)", exc)
        return {}

    def _rel(path: Path) -> str:
        """@brief Repo-relative spelling, or the bare name when outside the repo."""
        try:
            return str(Path(path).resolve().relative_to(root))
        except ValueError:
            return Path(path).name

    return {
        ## THE TARGET'S OWN DOC SCOPE, which is a DIFFERENT FACT from the three keys below
        ## and was being discarded. This repo's standing rule is that "INDEX scope is not
        ## GATE scope, and it is not DOXYFILE scope either" — the Doxyfile is read for
        ## ALIASES and PREDEFINED and its INPUT is deliberately REPLACED, so nothing in the
        ## index could answer what the repository itself chooses to document.
        ##
        ## Measured cost, already recorded in `write_build_signature`'s own docstring: on the
        ## entropic grid the raw arm scored 3/3 on "checks the Doxyfile and reports that its
        ## INPUT does not list examples/" and the index arm 1/3 — the only clearly actionable
        ## gap in 56 marks. Persisting scope provenance fixed the half about OUR boundary and
        ## left the half about THEIRS, which is what a question like "does the doc build cover
        ## implementation files or only headers" actually asks. On Mbed-TLS/mbedtls the answer
        ## is `FILE_PATTERNS = *.h`, i.e. headers only, and it was unanswerable from here.
        ##
        ## READ FROM DISCOVERY, NOT FROM `args.doxyfile`, and that is load-bearing: on a repo
        ## that ships none we SYNTHESIZE one, so `args` may carry OUR file — stamping its
        ## INPUT as the target's declared doc scope would publish our own decision as the
        ## repository's. Discovery returns None there and these keys are simply absent, which
        ## the falsy-drop rule renders as "not recorded" rather than as an empty declaration.
        **_doxyfile_scope(root, _rel, getattr(args, "doxyfile", None)),
        ## D4's SEPARATE vendored signal, and it is separate on purpose. `external` stays a
        ## GIT TREE, so `coverage`, `graph_stats` and every orphan count are untouched by this
        ## — a declared vendored path changes what the index can SAY, never what it counts.
        ##
        ## Reported here rather than tagged per row because the question it answers is a
        ## repository-level one ("what in here is not this project's code"), and a per-row tag
        ## would be a schema change plus a filter that no query may honour — the emptiness
        ## rule: an answer that is silently filtered is worse than one that is merely absent.
        **_vendored_scope(root, _rel, args),
        ## NAMES THE TIER, and the tier is now the whole answer to "was this boundary
        ## chosen": `clew-declaration` is a decision, `doxyfile` is the repo's
        ## documentation scope standing in, `whole-repo` is what a repo gets for saying
        ## nothing. A consumer reading a narrow root list has opposite responses available
        ## — trust it, or go and declare one — and `source` is what it chooses between.
        "source": derived.source,
        ## `str(root)` is the only absolute path that can appear in the reason text.
        "reason": derived.reason.replace(f"{root}/", "").replace(str(root), "."),
        "roots": SCOPE_LIST_SEPARATOR.join(_rel(r) for r in derived.roots),
        ## What the WALKER pruned: git-ignored trees, dot/cache directories, nested
        ## foreign repositories. Facts about the tree, not decisions.
        "excludes": SCOPE_LIST_SEPARATOR.join(_rel(e) for e in derived.excludes),
        ## What the OPERATOR removed. Already repo-relative and already validated by
        ## `_repo_relative_exclusion`, so it is joined rather than passed through
        ## `_rel` — re-relativising an already-relative string against the root would
        ## fall through to the bare-name branch and corrupt the record it replays from.
        OPERATOR_EXCLUDES_KEY: SCOPE_LIST_SEPARATOR.join(getattr(args, "exclude", None) or ()),
    }


## @brief Open the sidecar index cache for this build, unless disabled.
## @return A live IndexCache, or None when --no-index-cache was passed.
## @version 2
## @req REQ-DDB-INDEX-002
def _open_index_cache(
    args: argparse.Namespace,
    output: Path,
    repo_root: Path,
) -> IndexCache | None:
    """`--no-index-cache` returns None (fully uncached build). `--rebuild`
    opens the cache with reads DISABLED, so everything is recomputed and then
    re-stored — one forced full build that re-warms the cache.

    @brief Construct the build's index cache.
    @version 2
    """
    if args.no_index_cache:
        logger.info("index cache: disabled (--no-index-cache)")
        return None
    cache_path = (
        Path(args.index_cache).resolve()
        if args.index_cache
        else output.with_name(output.name + ".idxcache")
    )
    if args.rebuild:
        logger.info("index cache: --rebuild — ignoring cached entries, refreshing them")
    return IndexCache(cache_path, repo_root, read_enabled=not args.rebuild)


## @brief Execute the build pipeline, writing atomically to --output.
## @version 17
## @req REQ-DDB-PIPE-001
## @req REQ-DDB-PIPE-002
## @req REQ-DDB-MCP-004
## @req REQ-DDB-CONFIG-008
def _run_pipeline(args: argparse.Namespace) -> None:
    """Build into a sibling temp DB, then os.replace() it onto --output.

    The swap is atomic (same filesystem), so a concurrent reader — the
    docs_server opens a fresh RO connection per tool call — never sees a
    half-built DB, and a failed build leaves the existing clew.db untouched
    (readers keep the good old index until the swap lands). This makes every
    rebuild path swap-safe: launch, background self-heal, and --rebuild-docs.

    TIMED FROM THE FIRST LINE, so `refresh.duration_ms` is the cost a caller actually
    waited for rather than the part of it the stamping call happens to sit after. gh#9.
    The `StageTimer` starts here for the same reason, so the segments it records
    partition the duration it is reported beside instead of some inner part of it.

    @brief Run the build pipeline, recording what it cost.
    @version 17
    """
    started = time.perf_counter()
    timer = StageTimer()
    ## FIRST, BEFORE ANY RESOLUTION READS A DEST IT COULD SET. A stated `index_scope` is
    ## consumed by `_apply_scope` four lines down and by `_resolve_doxyfile_and_root` above
    ## it; `predefined` decides what doxygen is asked to parse. Applying the document later
    ## would leave the earliest consumers reading the defaults while the log said the
    ## statement was honoured — this pipeline's most-recorded failure shape.
    ##
    ## Applied HERE rather than in `main` so that any namespace carrying `declare` is
    ## honoured however it was built, and so `build_index` (whose `options` argument reaches
    ## `apply_options` directly) and the CLI converge on one code path before the build.
    _apply_declared_document(args)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    doxyfile, repo_root = _resolve_doxyfile_and_root(args, output)
    # gh#3. Checked AFTER the Doxyfile is resolved (its FILE_PATTERNS is the thing
    # that excludes) and BEFORE `_apply_scope`, which PREPENDS derived scope roots
    # into `args.extra_input` — so this sees only the roots the user named, and a
    # derived root that happens to hold no matching file can never refuse a build.
    _verify_extra_input_is_read(doxyfile, args.extra_input, args.extra_exclude, repo_root)
    _apply_scope(args, repo_root)
    ## The operator's own narrowing, resolved AFTER the derived scope so the two are
    ## never confused, and written back onto `args` so the fold below and the stamp in
    ## `_scope_provenance` read ONE value. Resolved from `output` — the previous build
    ## — while it still exists, which is before the swap at the bottom of this function.
    ##
    ## An index-SHAPE argument, and the distinction is worth keeping sharp: scope is
    ## what the operator wants indexed, so it travels as an argument. A declared
    ## CONVENTION (locks, threads, dispatch, shared keys) is a fact about the code and
    ## is read from the target's own `.clew.yaml`, so that the CLI and the MCP
    ## server cannot end up honouring different ones.
    args.exclude = _operator_excludes(args, output, repo_root)
    args.extra_exclude = list(args.extra_exclude or []) + [
        str(repo_root / relative) for relative in args.exclude
    ]
    ## The operator's tier-1 entry-pattern statement, resolved here for exactly the
    ## reason the exclusions above are: `output` is the PREVIOUS build's database and
    ## it is gone after the swap at the bottom of this function. Written back onto
    ## `args` so `_entry_patterns` in the build stages reads ONE value, whether it was
    ## typed on this command line or replayed from the last one.
    args.entry_patterns = _recorded_entry_patterns(args, output)
    ## gh#366, and it is the same read-back at the same moment for the same reason. Kept
    ## SEPARATE from the manifest loop because a list and a document have different stored
    ## forms and therefore different readers.
    args.predefined = _recorded_predefined(args, output)
    ## The operator's tier-1 MANIFEST statements, replayed here for the same reason and
    ## at the same moment: `output` is the previous build's database and it is gone after
    ## the swap. Written back onto `args` so `_declared_or_flag` in the build stages reads
    ## ONE value whether it was stated on this call or on an earlier one — and so the tier
    ## stamped by `_manifest_option_tiers` describes the document the stages were given.
    replayed = _replay_manifest_statements(args, output)
    if replayed:
        logger.info(
            "build options: replaying the tier-1 statement recorded by an earlier build "
            "(this index carries a policy the repository does not declare) — %s",
            ", ".join(replayed),
        )
    cache = _open_index_cache(args, output, repo_root)
    timer.mark("resolve")
    tmp = output.with_name(output.name + ".tmp")
    counts: tuple[int, int] | None = None
    try:
        _build_stages(tmp, doxyfile, args, cache, timer)
        os.replace(tmp, output)  # atomic swap onto the live path
        # Persist the cache only after the swap lands: a failed build must not
        # leave source_files claiming the current tree was successfully indexed.
        if cache is not None:
            cache.commit()
            ## Read BEFORE close() rather than after. The counters survive closing — they
            ## are plain ints — but reading state off a closed object is exactly the kind
            ## of accident that works until someone makes close() reset them.
            counts = (cache.hits, cache.misses)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    finally:
        if cache is not None:
            cache.close()
    timer.mark("swap")
    report_stats(output)
    timer.mark("report_stats")
    _stamp_refresh_metrics(output, started, counts, timer)


## @brief Run one build in-process, without composing a command line.
## @param output Database path to build (written atomically).
## @param repo_root Repository being indexed, or None to take the Doxyfile's directory.
## @param doxyfile Explicit Doxyfile; None discovers or synthesizes one.
## @param scope Where the indexed file set comes from (`doxyfile` or `from-guard`).
## @param requirements Requirements catalog to ingest, or None to discover one.
## @param exclude Repo-relative paths to leave out; None inherits the recorded ones, [] withdraws them.
## @param options Tier-1 build options keyed by declaration-file section name; None or {} states nothing.
## @version 3
## @req REQ-DDB-PIPE-001
## @req REQ-DDB-CLI-001
## @req REQ-DDB-CONFIG-001
## @req REQ-DDB-CONFIG-008
def build_index(
    output: Path | str,
    repo_root: Path | str | None = None,
    doxyfile: Path | str | None = None,
    scope: str | None = None,
    declare: str | Path | None = None,
    requirements: Path | str | None = None,
    exclude: list[str] | None = None,
    options: dict[str, Any] | None = None,
) -> None:
    """THE ENTRY POINT FOR AN EMBEDDING CALLER — the MCP server runs the build
    through this, in its own process, so a failure arrives as an exception carrying
    a traceback rather than as an exit code plus whatever reached a pipe.

    Every option this does not name keeps the parser's declared default, which is
    why the defaults are sourced by parsing rather than restated here: a flag added
    to `_build_argparser` reaches this path with its intended default instead of
    silently becoming None.

    Output goes to the console `_common.active_console` resolves, so a caller whose
    stdout is a protocol transport wraps the call in `_common.captured_output` and
    nothing reaches stdout.

    `exclude` PRESERVES ITS THREE STATES across this boundary — `None` inherits what
    the database already records, `[]` withdraws it, a list replaces it — so a caller
    that simply forwards its own optional argument gets the inheriting behaviour by
    default, which is the one that makes a refresh honour a decision taken earlier.
    Normalising `None` to `[]` here would silently turn every plain refresh into a
    withdrawal.

    `options` IS TIER 1 AND IT ARRIVES LAST, after every other assignment, because it is
    the tier that wins. It is applied through `apply_options` rather than unpacked here so
    that both this caller and any future one refuse the same malformed mapping in the same
    words — and so a bad entry raises BEFORE `_run_pipeline` starts, rather than producing
    a build whose policy is half what was asked for. Relative paths inside it resolve
    against `repo_root`, not the process's working directory, because an embedding server's
    cwd is not the target repo.

    @brief Build one index in-process from typed arguments.
    @version 3
    """
    args = _build_argparser().parse_args(["--output", str(output)])
    args.repo_root = str(repo_root) if repo_root is not None else None
    args.doxyfile = str(doxyfile) if doxyfile is not None else None
    if scope is not None:
        args.scope = scope
    args.requirements = str(requirements) if requirements is not None else None
    args.exclude = list(exclude) if exclude is not None else None
    ## `--declare`'s OWN ROUTE, reachable from the typed entry point too. Phase 5 gave the CLI a
    ## `--declare FILE` and left `build_index` with only the inline `options`, so an embedding
    ## caller could not exercise the import path a team actually commits — and the export/declare
    ## round trip could only be tested by re-implementing the document read, which would have
    ## tested a copy of the reader rather than the reader.
    ##
    ## APPLIED BEFORE `options`, so an inline statement still wins: the document is a file on disk
    ## and the mapping is what this call said, and the later assignment is the more specific one.
    if declare is not None:
        args.declare = str(declare)
        _apply_declared_document(args)
    applied = apply_options(args, options, Path(repo_root) if repo_root is not None else None)
    if applied:
        logger.info("build options: stated by the caller (tier 1) — %s", ", ".join(applied))
    _run_pipeline(args)


## @brief Resolve which Doxyfile to build with, and the repo root it belongs to.
## @param args Parsed CLI arguments.
## @param output Resolved --output path (its parent hosts a synthesized Doxyfile).
## @return (doxyfile, repo_root). Exits 1 when neither can be established.
## @version 3
## @dg_internal
def _resolve_doxyfile_and_root(args: argparse.Namespace, output: Path) -> tuple[Path, Path]:
    """EXTRACTED from `_run_pipeline`, which the gh#3/gh#4 messaging work took to
    cognitive complexity 16 against a ceiling of 15.

    Pure extraction: the four-way resolution and its two exit paths are unchanged, and
    the caller's ordering constraint is preserved — gh#3's check must run AFTER a
    Doxyfile is resolved (its `FILE_PATTERNS` is what excludes) and BEFORE
    `_apply_scope` prepends derived roots, so the check only ever judges roots the
    user actually named.

    @brief Decide the Doxyfile and repo root for this build.
    @return The resolved (doxyfile, repo_root) pair.
    @version 3
    """
    doxyfile = Path(args.doxyfile).resolve() if args.doxyfile else None
    if doxyfile is None and args.repo_root:
        # Discover the repo's OWN Doxyfile before considering synthesis. Without
        # this the CLI jumped straight to a 3-line synthesized Doxyfile even for
        # repos that ship one, silently discarding their declared ALIASES (so
        # @emits/@handles/@req xrefitem rewrites never happened), PREDEFINED
        # macros and filters — while the MCP path, which always discovered,
        # produced a materially richer database from the same repo. Synthesis is
        # for the genuinely Doxyfile-less case (#33), not a default.
        doxyfile = discover_doxyfile(Path(args.repo_root).resolve())
    if doxyfile is not None and doxyfile.exists():
        repo_root = Path(args.repo_root).resolve() if args.repo_root else doxyfile.parent
    elif (
        args.scope == SCOPE_FROM_GUARD
        and args.repo_root
        and derive_scope(Path(args.repo_root).resolve(), args.guard_config).is_derived()
    ):
        # No usable Doxyfile, but the repo DECLARES its scope (a doxygen-guard
        # hook that actually derives roots) — synthesize a minimal one rather
        # than refusing to index a repo whose build is fully derivable.
        repo_root = Path(args.repo_root).resolve()
        doxyfile = synthesize_doxyfile(repo_root, output.parent / (output.stem + ".doxygen"))
    elif args.repo_root:
        # NEITHER a usable Doxyfile NOR a declared scope — synthesize one.
        #
        # THE SCOPE DECISION NO LONGER LIVES HERE (gh#333). This branch used to be the
        # only route to whole-repo indexing, which is what produced the inversion: a repo
        # SHIPPING a Doxyfile got its documentation subset and a repo without one got its
        # whole tree. `_apply_scope` now replaces INPUT for every from-guard build, so this
        # branch decides only whether a Doxyfile has to be MANUFACTURED, not what to index.
        #
        # Why INPUT is replaced at all, measured on Mbed-TLS/mbedtls, a standard OSS library
        # with no doxygen-guard: its `doxygen/mbedtls.doxyfile` sets `FILE_PATTERNS = *.h`
        # and `INPUT = ../include`, because it publishes an API reference. Honouring that
        # indexes 1,571 header declarations, ZERO of its 108 `library/*.c` implementations,
        # and therefore zero of the 13 files that take a mutex — a confidently populated
        # index of the wrong thing.
        #
        # A repo's OWN Doxyfile is still PREFERRED over synthesis when one is found: it
        # carries ALIASES, PREDEFINED and filters synthesis cannot reconstruct. Those are
        # exactly the settings that survive an INPUT replacement.
        repo_root = Path(args.repo_root).resolve()
        # gh#4. Which of the two SUPPORTED no-Doxyfile situations this is — the repo
        # ships none, or it ships one somewhere discovery refuses to guess from —
        # phrased by the same table that phrases the two fatal ones, so a supported
        # route cannot drift into sounding like a failure. `explicit=None` because
        # this branch is reached only when no usable Doxyfile was resolved, and the
        # explicitly-missing case is reported separately just below.
        logger.warning(
            "%s",
            describe_doxyfile_resolution(
                None, repo_root, rejected_doxyfile_candidates(repo_root)
            ).message,
        )
        if args.doxyfile:
            # A SILENT DISCARD of an explicit flag, found while probing gh#4's branch
            # reachability: `--doxyfile <nonexistent> --repo-root <repo>` fell straight
            # through to whole-repo synthesis and never mentioned the path it was told
            # to use. Same class as gh#4 itself — the tool did something other than
            # what it was asked and said nothing — so it gets a sentence rather than
            # silence. Still not fatal: --repo-root is sufficient on its own.
            logger.warning(
                "the --doxyfile you passed does not exist and is being IGNORED: %s. The "
                "whole-repo synthesis above is what will be indexed instead",
                Path(args.doxyfile).resolve(),
            )
        doxyfile = synthesize_doxyfile(repo_root, output.parent / (output.stem + ".doxygen"))
    else:
        # gh#4. The old sentence here served all four resolution situations at once,
        # described none of them, and in the only case a user could actually reach by
        # passing a flag it answered "Pass --doxyfile" — the thing they had just done.
        # `describe_doxyfile_resolution` says what was looked for, where, what was
        # found, and the one action that changes the outcome.
        logger.error("%s", describe_doxyfile_resolution(doxyfile, None, []).message)
        sys.exit(1)
    return doxyfile, repo_root


## @brief Record what this build actually cost, into the built index.
## @param output Path to the swapped-in database.
## @param started `time.perf_counter()` reading from the top of the build.
## @param counts (cache hits, cache misses) when a cache ran, else None.
## @param timer Per-stage breakdown collected during the build.
## @version 4
## @req REQ-DDB-MCP-004
def _stamp_refresh_metrics(
    output: Path, started: float, counts: tuple[int, int] | None, timer: StageTimer
) -> None:
    """gh#9. The pipeline knew its wall duration, how many files it reprocessed and how
    many it took from cache, and returned NONE of it — so an agent asked what a refresh
    costs had to estimate one, and the two acceptance marks demanding a measured number
    missed 9 of 9 cells across every model tier. An agent told the number simply
    refreshes; an agent left to estimate may decide it is expensive and skip it.

    STAMPED LAST, after the swap, so the duration is the whole cost a
    caller waited for rather than the part of it this function happens to sit after. That
    is a second `write_build_signature` call on the live path, which is safe because it
    UPSERTS: the `scope`/`coverage`/`preprocessor`/`kconfig` rows written into the temp
    database during the stages survive untouched.

    Every value is a STRING, and that is load-bearing rather than cosmetic:
    `write_build_signature` DROPS FALSY VALUES so an absent key can honestly read as "not
    recorded", which means a genuine ZERO — a fully cached build reprocessing no files,
    or a sub-millisecond one — would silently vanish as `0` and survives as `"0"`.

    The cache counts are ABSENT under `--no-index-cache` rather than written as zero.
    Zero reprocessed files and no cache to report are different facts, and conflating
    them is the "two indistinguishable ways to be empty" defect this repo has recorded
    more than any other.

    THE PER-STAGE BREAKDOWN RIDES ALONG for the reason the total itself does: one
    number over thirty stages is enough to decide whether to refresh and not enough to
    decide what to make faster, and the timings existed at runtime and were discarded.
    It is a `refresh.stages` value rather than a key per stage so the section stays one
    line wide in a `status` payload; `stagetimer.parse_stages` decodes it.

    @brief Persist the measured cost of this build, whole and per stage, into build_meta.
    @version 3
    """
    from .signature import write_build_signature

    metrics = {
        "duration_ms": str(int((time.perf_counter() - started) * 1000)),
        "at_epoch": str(int(time.time())),
    }
    if counts is not None:
        hits, misses = counts
        metrics["cache_hits"] = str(hits)
        ## THE UNIT IS A (file, stage) PAYLOAD, NOT A FILE (#470). The cache's key is
        ## (content_sha, stage, stage_version, extra_key), so one changed file contributes up to
        ## one miss PER STAGE and there are ~10. Named `files_reprocessed` it read as a second,
        ## contradicting count of the same thing the tree scan reports — "5 source files changed"
        ## beside "45 file(s) reprocessed" — and the numbers were both right.
        metrics["payloads_recomputed"] = str(misses)
    metrics.update(timer.as_meta())
    write_build_signature(output, refresh=metrics)
    logger.info(
        "refresh cost: %s ms, %s cached stage payload(s) recomputed, %s served from cache",
        metrics["duration_ms"],
        metrics.get("payloads_recomputed", "unmeasured"),
        metrics.get("cache_hits", "unmeasured"),
    )
    logger.info("refresh stages: %s", metrics.get(STAGES_KEY, "unmeasured"))


## @brief Entry point — dispatch a subcommand, else parse args and build.
## @version 16
## @req REQ-DDB-CLI-001
def main() -> None:
    """Entry point — parse args, run doxygen, optionally enrich.

    `clew propose` and `init` are dispatched on the FIRST word
    rather than by converting the build parser into subparsers: the build's flat
    flags are the interface every existing caller uses — `python -m
    clew --output ...` — and moving them under a `build` subcommand would
    break all of them for a cosmetic gain. Every subcommand module is imported
    LAZILY, inside its branch, so a build never pays for them and `init` in
    particular stays runnable on an install missing the pipeline's heavier
    optional dependencies.

    An embedding caller does not come through here at all: `build_index` runs the
    same pipeline from typed arguments, so nothing has to survive a command line.

    A `DeclarationError` is caught here and reported as one line rather than a
    traceback: it means the target repo's own `.clew.yaml` (or a standalone
    manifest) names a value no schema vocabulary allows, and the message already
    carries the file, the token and the allowed set. It is the owner's config to
    fix, not a clew crash, so it exits 2 to separate it from a build failure.

    A `BuildOptionError` gets the SAME treatment and it is the same kind of fact one door
    over: the caller's own `--declare` document names a section nothing reads, or shapes an
    entry so no loader will see it. Without this it surfaced as a traceback out of
    `apply_options`, which reads as a crash in the tool for what is a typo in a YAML file —
    and the message already carries the key, the allowed set and why a silent default would
    have been worse.

    @brief Parse CLI arguments and run the build pipeline.
    @version 15
    """
    if sys.argv[1:2] == [PROPOSE_COMMAND]:
        from .propose.command import (
            propose_main,
        )

        sys.exit(propose_main(sys.argv[2:]))
    if sys.argv[1:2] == [EXPORT_COMMAND]:
        from .export_command import (
            export_main,
        )

        sys.exit(export_main(sys.argv[2:]))
    if sys.argv[1:2] == [INIT_COMMAND]:
        from .init_command import (
            init_main,
        )

        sys.exit(init_main(sys.argv[2:]))
    args = _build_argparser().parse_args()
    _configure_logging(args.verbose)
    _resolve_output(args)
    try:
        _run_pipeline(args)
    except (DeclarationError, BuildOptionError) as exc:
        logger.error("invalid declaration — %s", exc)
        sys.exit(2)
    except (DoxygenUnavailableError, RustdocUnavailableError) as exc:
        # Same treatment as a bad declaration, for the same reason: this is the
        # environment being wrong, not clew failing. It used to surface as a
        # twelve-frame FileNotFoundError naming 'doxygen', which reads as a crash
        # in this tool and is the first thing a new user on a clean machine sees.
        # RustdocUnavailableError is the Rust-repo analog — same refusal shape,
        # different missing prerequisite (a nightly toolchain instead of a
        # system package).
        logger.error("cannot build — %s", exc)
        sys.exit(2)
