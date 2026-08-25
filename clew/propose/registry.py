# SPDX-License-Identifier: MIT
"""Run every declaration section over one repo and assemble the Proposal.

This is the module `model` and `context` refer to as "the registry", and its one
structural rule is that it enumerates EVERY section of `.clew.yaml` — not just
the ones a detector exists for. Silence about a section is the failure this
design exists to prevent: an owner reading a draft with no `locks:` in it cannot
tell whether clew looked and found nothing, or never looked at all, and those
two call for opposite actions.

So `_DETECTED` holds the sections with a detector, `HAND_DECLARED` holds the ones
clew deliberately refuses to guess (each carrying the reason), and
`index_scope` is report-only. Every one of them returns a `SectionProposal`.

The AST detectors are also gated as a group, because four conditions make them
meaningless rather than merely empty: no tree-sitter, no DERIVED index scope (the
detectors have no notion of "first-party" without one — `threads_detect` rule 1),
no parseable source at all, and no C/C++ file inside that scope. Reporting
`no_candidates` in any of those cases would claim a measured absence clew never
measured. clew's own Python-only indexed scope is the last case, and it must
read NOT_APPLICABLE — note that the parser router covers Python, so the gate has
to count files a C/C++ GRAMMAR handles rather than files that parsed.

@brief Section registry and top-level assembler for the declaration proposer.
@version 3
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..declaration import (
    SECTION_DATA_MODEL,
    SECTION_DISPATCH,
    SECTION_DOXYFILE,
    SECTION_ENRICH,
    SECTION_ENTRY_PATTERNS,
    SECTION_TEST_PATHS,
    SECTION_EVENT_TAGS,
    SECTION_KCONFIG,
    SECTION_LOCKS,
    SECTION_MQTT,
    SECTION_PREPROCESSOR,
    SECTION_REQUIREMENTS,
    SECTION_SHARED_KEY,
    SECTION_THREADS,
    SECTION_VENDORED,
    load_declaration,
)
from ..harvest import try_import_tree_sitter
from ..scope import INDEX_SCOPE_SECTION, derive_scope
from ..signature import CLEW_BUILD_VERSION, read_build_signature
from .context import Context
from .dryrun import index_defect
from .model import Proposal, SectionProposal, SectionStatus
from .notindexed import report_not_indexed
from .render import render_declaration
from .scanning import (
    Corpus,
    ast_readable_in_scope,
    repo_source_files,
    scan_repo,
    scope_membership,
)
from .sharedkey_detect import split_accessor
from .sharedkey_report import propose_shared_key_patterns
from .threads_detect import propose_thread_patterns

## One section detector: everything it may read is on the Context.
Detector = Callable[[Context], SectionProposal]

## Sections a detector exists for, in render order. Both are tree-sitter AST
## detectors and both are gated together by `_blocking`.
_DETECTED: tuple[tuple[str, Detector], ...] = (
    (SECTION_SHARED_KEY, propose_shared_key_patterns),
    (SECTION_THREADS, propose_thread_patterns),
)

## Sections clew will NOT propose, each with the reason. These are not gaps
## waiting for a detector — every one of them is a case where a plausible guess
## writes a specific, wrong claim into the graph, which is worse than an empty
## layer because nothing downstream can tell it from a measured fact.
HAND_DECLARED: dict[str, str] = {
    SECTION_VENDORED: (
        "whether a committed directory is code this project WROTE or code it merely SHIPS "
        "is a fact about authorship, and nothing in the tree carries it. `external` covers "
        "the case that IS mechanical — a git tree of its own — and this section exists "
        "precisely for the case that is not: Mbed-TLS's `3rdparty/` is committed, not a "
        "submodule, so no git test finds it. A directory NAME is not evidence either: "
        "`vendor/` and `third_party/` are conventions, and a `3rdparty/` full of "
        "first-party glue is a real thing. Guessing here would mislabel a project's own "
        "code as somebody else's, which is worse than saying nothing."
    ),
    SECTION_MQTT: (
        "a topic-subscription call is not distinguishable by shape: the topic is a "
        "runtime string or variable, and no arity or naming rule separates "
        "subscribe(topic, handler) from any other two-argument call. A wrong guess "
        "routes unrelated handlers onto one topic and mints keyed dispatch edges "
        "between functions that never communicate."
    ),
    SECTION_DATA_MODEL: (
        "this section names a repo-relative PATH to a generator manifest (an ingot-style "
        "TOML), not a pattern. clew cannot know which of a repo's manifests is the "
        "authoritative data model, and the declared layer is AUTHORITATIVE (no "
        "inference gates it), so naming the wrong file writes writer/reader edges "
        "straight into the causal layer."
    ),
    SECTION_REQUIREMENTS: (
        "this section names a repo-relative PATH to the requirements catalog, and there is "
        "no universal shape for one — a flat {id,title,...} list and a nested domains: tree "
        "are both real, read additively. Convention already finds the common case, and "
        "resolve_catalog_path REFUSES rather than picks when several candidates are "
        "ambiguous; proposing one would be making exactly the pick that refusal avoids. "
        "Naming the wrong document does not empty the requirement layer — @req edges come "
        "from TAGS — it fills every row's metadata from a catalog describing other work."
    ),
    SECTION_ENRICH: (
        "this section names a repo-relative PATH to an architecture-topics document, which "
        "is prose an owner writes about their own system. There is nothing in a repository "
        "to detect it from: an absent enrichment file is the normal state, not a gap, and a "
        "guess would nominate whichever YAML happened to sit in docs/."
    ),
    SECTION_LOCKS: (
        "the built-in patterns already cover the language/OS primitives "
        "(std::lock_guard / std::unique_lock / pthread_mutex_lock / ...). A repo's OWN "
        "guard type is a type name with no distinguishing call shape, and a wrong one "
        "fabricates synchronization: two lock rows collapsing into one is "
        "indistinguishable from real shared locking (see clew/locks.py on "
        "scope-qualified identity)."
    ),
    SECTION_ENTRY_PATTERNS: (
        "these are SQL LIKE patterns naming this repo's indirect-dispatch convention. "
        "Seeding a genuinely dead handler as LIVE is a worse error than reporting a "
        "false orphan — a false orphan is visible, a false live is not — so clew "
        "keeps them declared rather than guessed (clew/declaration.py, "
        "SECTION_ENTRY_PATTERNS)."
    ),
    SECTION_TEST_PATHS: (
        "these are glob patterns naming the paths that hold TEST code, so a bare ambiguous "
        "function name resolves to the library definition rather than a same-named test "
        "helper. Measured on a real C++ target: `run_turn` had four definitions and the "
        "resolver picked a file-local helper in tests/, because the real method is declared "
        "in a header and defined out of line and so loses the in-place tie-break. Declared "
        "rather than guessed because `tests/` is a convention — `test/`, `spec/`, `t/` and "
        "colocated `foo_test.cpp` are all in the wild — and a DECLARATION DISPLACES the "
        "built-in guesses rather than extending them, so stating your layout narrows the rule "
        "instead of only widening it (clew/testscope.py, TEST_PATH_FACTS)."
    ),
    SECTION_DISPATCH: (
        "all three dispatch shapes (interface bindings, fnptr registration sites, "
        "key-carrying generic helpers) hide ONE endpoint of a relationship behind an "
        "indirection. The static graph cannot see the hidden end, which is exactly why "
        "the recovery has to be an author's statement and not an inference."
    ),
    SECTION_PREPROCESSOR: (
        "this section states WHICH BUILD VARIANT the index represents, and doxygen "
        "evaluates #if defined(X) as it parses. So a wrong macro list does not merely "
        "widen or narrow the index — it makes the index describe a DIFFERENT VARIANT of "
        "the same code, while every count taken from it still looks legitimate. A "
        "proposal cannot know which variant an owner meant to index."
    ),
    SECTION_KCONFIG: (
        "needed only where convention does NOT reach: discover_kconfig already believes "
        "an unambiguous root Kconfig without any declaration, and refuses rather than "
        "picks when several candidates are ambiguous. Proposing one would be making "
        "exactly the pick that refusal exists to avoid — and naming the wrong top of the "
        "tree reports a configuration SPACE the build never had."
    ),
    SECTION_DOXYFILE: (
        "where the repository keeps its OWN documentation target, needed only where "
        "convention does not reach — the same trade kconfig makes above. discover_doxyfile "
        "matches the name `Doxyfile` in the root, `docs/` and `doc/` and refuses to guess "
        "further, having once been caught selecting a test FIXTURE's Doxyfile to index a "
        "whole project. Proposing one would be making exactly that pick again: a repo can "
        "hold several doxygen configurations (a published API reference, an internal one, a "
        "test fixture's) and nothing in a filename says which is the project's."
    ),
    SECTION_EVENT_TAGS: (
        "the tag names a repo documents its event bus with. Nothing in an ALIASES line "
        "marks a tag as belonging to an event bus rather than to exceptions, ownership or "
        "any other cross-reference, so a guess reads one for the other and mints "
        "declared=1 causal edges out of it. The BUILD reports the unclaimed tags instead "
        "(event_edges._report_unrecognised_aliases), which names candidates without "
        "asserting any of them."
    ),
}

_NO_TREE_SITTER = (
    "tree_sitter (or its C/C++ grammars) is not importable in this environment, so no "
    "AST corpus could be built. NOTHING was scanned — this is not a measured absence. "
    "Install the grammars and re-run."
)

_NO_DERIVED_SCOPE = (
    "this repo's index scope is NOT derived from a declaration: {reason}. Without a "
    "derived scope clew has no notion of which source is FIRST-PARTY, and the first "
    "thing a detector proposes is a vendored library's own helper. Declare an "
    "index_scope: section and re-run."
)

_NO_SOURCE = (
    "no file under this repo has an extension a tree-sitter C/C++ grammar handles, so "
    "there is nothing for the AST detectors to read."
)

_NONE_IN_SCOPE = (
    "NOT ONE of the {in_scope} file(s) inside the derived index scope ({source}) is C or "
    "C++. The R1 AST detectors — accessor families and thread-spawn wrappers — read C/C++ "
    "node shapes only, so there is nothing here for them to detect; this is a fact about "
    "the detectors, not a measurement of the repo. Everything else clew builds (the "
    "call graph, prose, requirements traceability) works on this repo regardless."
)

_ALREADY_DECLARED = (
    "this repo's own .clew.yaml already declares this section. clew does not "
    "second-guess a hand-written declaration — it is the authoritative statement."
)


## @brief Assemble everything the detectors are allowed to read, once.
## @param repo_root Repo to propose a declaration for.
## @param db_path Built index to measure candidates against, or None.
## @param dry_run Whether candidates may be measured against the index.
## @param use_declaration Read the repo's own `.clew.yaml` (False = as if undeclared).
## @return The assembled Context.
## @version 1
## @req REQ-DDB-CONFIG-001
def build_context(
    repo_root: Path | str,
    db_path: Path | str | None = None,
    *,
    dry_run: bool = True,
    use_declaration: bool = True,
) -> Context:
    """`use_declaration=False` is how an owner AUDITS a declaration they already
    wrote: it runs detection as if the repo declared nothing, so a hand-written
    entry shows up as a fresh proposal instead of being refused as
    already-covered. It deliberately does NOT affect scope derivation, which
    reads the same file — the scope a proposal is computed against must be the
    one the build actually uses, or every measured number describes a different
    repo than the one being indexed.

    @brief Build the shared detector context for one repo.
    @version 1
    """
    root = Path(repo_root).expanduser().resolve()
    scope = derive_scope(root)
    ts_classes = try_import_tree_sitter()
    files = repo_source_files(root)
    in_scope = scope_membership(scope)
    corpus = (
        scan_repo(root, files, in_scope, ts_classes, split_accessor)
        if ts_classes is not None
        else Corpus()
    )
    return Context(
        repo_root=root,
        db_path=Path(db_path).expanduser().resolve() if db_path else None,
        scope=scope,
        declared=load_declaration(root) if use_declaration else {},
        files=files,
        in_scope=in_scope,
        corpus=corpus,
        ts_classes=ts_classes if ts_classes is not None else (None, None),
        dry_run=dry_run,
    )


## @brief Propose a starter `.clew.yaml` for one repo.
## @param repo_root Repo to propose a declaration for.
## @param db_path Built index to measure candidates against, or None.
## @param dry_run Whether candidates may be measured against the index.
## @param use_declaration Read the repo's own `.clew.yaml` (False = as if undeclared).
## @return The Proposal, including the rendered all-comments draft.
## @version 2
## @req REQ-DDB-CONFIG-001
def propose(
    repo_root: Path | str,
    db_path: Path | str | None = None,
    *,
    dry_run: bool = True,
    use_declaration: bool = True,
) -> Proposal:
    """An index that exists but cannot be measured against is passed to the
    detectors as NO index, so they fail closed exactly as they do when none was
    found. The defect is still reported in the header — a reader who sees "NO
    INDEX" while holding a `clew.db` needs to know it was rejected and why.

    @brief Detect every section and render the commented draft.
    @version 3
    """
    status = db_status_summary(Path(db_path).expanduser().resolve() if db_path else None)
    ctx = build_context(
        repo_root,
        db_path if status.get("usable") else None,
        dry_run=dry_run,
        use_declaration=use_declaration,
    )
    sections = _sections(ctx)
    scope = scope_summary(ctx)
    return Proposal(
        repo_root=ctx.repo_root,
        db_path=ctx.db_path,
        db_status=status,
        scope=scope,
        sections=sections,
        yaml_text=render_declaration(ctx.repo_root, status, scope, sections),
    )


## @brief Every section's result, in render order.
## @param ctx Shared detector inputs.
## @return One SectionProposal per `.clew.yaml` section.
## @version 1
## @dg_internal
def _sections(ctx: Context) -> tuple[SectionProposal, ...]:
    """@brief Run the detectors, then the hand-declared and report-only sections."""
    blocking = _blocking(ctx)
    detected = tuple(
        _blocked_section(name, blocking) if blocking is not None else detector(ctx)
        for name, detector in _DETECTED
    )
    hand = tuple(_hand_section(ctx, name, reason) for name, reason in HAND_DECLARED.items())
    return (*detected, *hand, _index_scope_section(ctx, detected))


## @brief Why the AST detectors cannot run, when they cannot.
## @param ctx Shared detector inputs.
## @return (status, reason) when detection is impossible, else None.
## @version 3
## @dg_internal
def _blocking(ctx: Context) -> tuple[SectionStatus, str] | None:
    """Ordered most-fundamental first, so the reported reason is the root cause
    rather than a downstream symptom of it (a missing grammar also produces zero
    in-scope files).

    The last check counts files a C/C++ grammar handles, NOT files that parsed.
    The parser router covers Python as well, and a Python file parses cleanly
    while contributing no definition and no call site these detectors can read —
    so counting parses would report a Python codebase as a MEASURED empty C repo,
    which is a claim about the repo where the truth is a claim about the detector.

    @brief Decide whether the AST detectors can produce a measured answer.
    @version 3
    """
    corpus = ctx.corpus
    readable = ast_readable_in_scope(ctx.files, ctx.in_scope)
    checks = (
        (ctx.ts_classes == (None, None), SectionStatus.NOT_ANALYSED, _NO_TREE_SITTER),
        (
            not ctx.scope.is_derived(),
            SectionStatus.NOT_ANALYSED,
            _NO_DERIVED_SCOPE.format(reason=ctx.scope.reason),
        ),
        (corpus.files_parsed == 0, SectionStatus.NOT_APPLICABLE, _NO_SOURCE),
        (
            readable == 0,
            SectionStatus.NOT_APPLICABLE,
            _NONE_IN_SCOPE.format(in_scope=corpus.files_in_scope, source=ctx.scope.source),
        ),
    )
    return next(((status, reason) for cond, status, reason in checks if cond), None)


## @brief A detector section that could not run, carrying the reason it could not.
## @param name Section name.
## @param blocking (status, reason) from `_blocking`.
## @return The SectionProposal standing in for the detector.
## @version 1
## @dg_internal
def _blocked_section(name: str, blocking: tuple[SectionStatus, str]) -> SectionProposal:
    """@brief Report a detector that was never able to look."""
    status, reason = blocking
    return SectionProposal(name=name, status=status, reason=reason)


## @brief A section clew refuses to detect: hand-declared, or already declared.
## @param ctx Shared detector inputs.
## @param name Section name.
## @param reason Why clew will not propose it.
## @return The SectionProposal.
## @version 2
## @dg_internal
def _hand_section(ctx: Context, name: str, reason: str) -> SectionProposal:
    """A declared section reports ALREADY_DECLARED rather than repeating the
    refusal: the owner has clearly already read this, and the draft's job then is
    to confirm clew sees it, not to lecture.

    @brief Report one hand-declared section.
    @version 2
    """
    declared = ctx.declared.get(name) is not None
    return SectionProposal(
        name=name,
        status=SectionStatus.ALREADY_DECLARED if declared else SectionStatus.NOT_ANALYSED,
        reason=_ALREADY_DECLARED if declared else f"NOT PROPOSED BY DESIGN — {reason}",
        checked={"declared_by_the_repo": declared},
    )


## @brief The report-only `index_scope` section, plus the no-corpus caveat.
## @param ctx Shared detector inputs.
## @param detected The detector sections (for cross-section conflict warnings).
## @return The REPORT_ONLY SectionProposal.
## @version 1
## @dg_internal
def _index_scope_section(ctx: Context, detected: tuple[SectionProposal, ...]) -> SectionProposal:
    """`report_not_indexed` derives its directory list from the AST corpus, so
    with no corpus its "nothing outside the scope" line would be an artefact of
    not having looked. The caveat is appended rather than the section suppressed,
    because the scope facts it reports are still true and still worth reading.

    @brief Build the index_scope report, caveated when there is no corpus.
    @version 1
    """
    section = report_not_indexed(ctx, detected)
    if ctx.corpus.files_parsed:
        return section
    return replace(
        section,
        notes=(
            *section.notes,
            "CAVEAT: no C/C++ source was parsed, so the directory list above is empty "
            "because nothing was scanned — not because nothing is outside the scope.",
        ),
    )


## @brief Freshness and usability summary for the index a proposal measures against.
## @param db_path Path to the index, or None when there is none.
## @return Mapping with the path, existence, usability, stamped version and staleness.
## @version 3
## @req REQ-DDB-CONFIG-001
def db_status_summary(db_path: Path | None) -> dict[str, Any]:
    """Surfaced in the rendered header because every MEASURED number in the draft
    is a number FROM this database. A proposal measured against a stale index is
    still useful, but the reader has to know that is what they are holding — and a
    file that is not a clew index at all has to be named as rejected rather
    than silently treated as absent.

    @brief Summarise the measuring index.
    @version 3
    """
    if db_path is None or not db_path.is_file():
        return {"path": str(db_path) if db_path else None, "exists": False, "usable": False}
    defect = index_defect(db_path)
    version = read_build_signature(db_path)
    return {
        "path": str(db_path),
        "exists": True,
        "usable": not defect,
        "defect": defect,
        "build_version": version,
        "expected_build_version": CLEW_BUILD_VERSION,
        "stale": version != CLEW_BUILD_VERSION,
    }


## @brief Scope and corpus summary for the rendered header.
## @param ctx Shared detector inputs.
## @return Mapping describing the derived scope and what was parsed.
## @version 2
## @req REQ-DDB-CONFIG-001
def scope_summary(ctx: Context) -> dict[str, Any]:
    """Reports the C/C++ subset separately from the parsed total: the parser
    router also covers Python, and only the C/C++ count describes what the R1 AST
    detectors were able to read.

    @brief Summarise the derived scope and the scanned corpus.
    @version 2
    """
    return {
        "source": ctx.scope.source,
        "reason": ctx.scope.reason,
        "derived": ctx.scope.is_derived(),
        "roots": len(ctx.scope.roots),
        "excludes": len(ctx.scope.excludes),
        "files_parsed": ctx.corpus.files_parsed,
        "files_in_scope": ctx.corpus.files_in_scope,
        "ast_readable_in_scope": ast_readable_in_scope(ctx.files, ctx.in_scope),
        "corpus_truncated": ctx.corpus.truncated,
    }


## @brief Every `.clew.yaml` section this registry accounts for.
## @return Section names in render order.
## @version 1
## @req REQ-DDB-CONFIG-001
def section_names() -> tuple[str, ...]:
    """Exists so a test can assert the registry covers the declaration module's
    whole surface — the guarantee that a newly-added section cannot be silently
    omitted from a draft.

    @brief List the sections the proposer reports on.
    @version 1
    """
    return (*(name for name, _ in _DETECTED), *HAND_DECLARED, INDEX_SCOPE_SECTION)
