# SPDX-License-Identifier: MIT
"""R2 — stable query library over the enriched clew.db.

The public data API that R3 (MCP) serializes and R4 (HTML) renders. Every
function accepts a `Path | str | sqlite3.Connection` and returns frozen,
JSON-serializable dataclasses (via `dataclasses.asdict`) — never raw sqlite
rows, never HTML. Edge endpoints are resolved to NAMES.

@brief Public surface of the R2 query library.
@version 1
"""

from __future__ import annotations

from ..signature import (
    CLEW_BUILD_VERSION,
    index_unusable_reason,
    read_build_signature,
)
from .corpus import (
    directory_rollup,
    doc_scope,
    file_doc_rows,
    has_prose_corpus,
    member_doc_rows,
    has_file_docs,
    index_scope,
    indexed_extensions,
    list_files,
    lookup_class,
    search_prose,
    search_prose_graded,
)
from .dossier import MAX_BATCH_SYMBOLS, function_dossier, function_dossiers
from .graph import graph_stats
from .kconfig import kconfig_space
from .locks import (
    lock_nestings,
    lock_roster,
    locks_held_when,
    runs_under_lock,
    sections_in,
)
from .macros import macro_definitions
from .models import (
    SUBJECT_KINDS,
    BodyExcerpt,
    CallEdge,
    Chain,
    ChainNode,
    ClassCandidate,
    ClassEntry,
    ClassMember,
    CriticalSection,
    Dossier,
    EdgeCounts,
    ExternalCallee,
    FileCounts,
    FileEntry,
    GraphStats,
    Hop,
    Implementer,
    IndexScope,
    KconfigEntry,
    KconfigGate,
    KconfigSpace,
    KeyEdge,
    LayerStat,
    LockNesting,
    LockNestingPair,
    MacroDef,
    NameAmbiguity,
    OriginSplit,
    OverrideRef,
    ProseHit,
    ProseSearch,
    ReqEdge,
    ReqRef,
    ReqTrace,
    SectionCall,
    SourceListing,
    ## The subject-agnostic envelope and the two subject payloads that had no type
    ## before it — a variable and a lock are now describable, which is what let the
    ## MCP surface drop from nineteen tools to four.
    LockSubject,
    SubjectDossier,
    SymbolHit,
    SymbolRef,
    VariableSite,
    VariableSubject,
    Terminus,
    Thread,
    ThreadInventory,
)
from .source import DECLARATION_MAX_LINES, DEFAULT_BODY_LINES, declaration_excerpt, source
from .subject import (
    MAX_SUBJECT_DEPTH,
    dossier,
    dossiers,
    resolve_subject,
    unresolved_kinds,
)
from .symbols import (
    MAX_DIAGNOSED_TOKENS,
    SEARCHED_MEMBERDEF_KINDS,
    all_req_edges,
    callees,
    callers,
    name_ambiguity,
    overridden_by,
    overrides_of,
    req_trace,
    resolve_symbol,
    search,
    thread_of,
    thread_roster,
    token_hit_counts,
    unsearched_corpora,
)
from .traversal import chain_trace

__all__ = [
    # dataclasses
    ## The one-shot dossier panels — a bounded body excerpt and the callee names the
    ## index holds no function for.
    "BodyExcerpt",
    "ExternalCallee",
    "CallEdge",
    ## gh#8 — doxygen's override relation, reachable at last.
    "OverrideRef",
    "overrides_of",
    "overridden_by",
    "Chain",
    "ChainNode",
    "ClassCandidate",
    "ClassEntry",
    "ClassMember",
    "CriticalSection",
    ## The dossier body cap, exported because the MCP layer defaults its own argument to
    ## it rather than restating the number — one source for "how much body is a body".
    "DEFAULT_BODY_LINES",
    "Dossier",
    ## gh#7 — the whole-graph trust aggregate and its three nested sections.
    "EdgeCounts",
    "FileCounts",
    "GraphStats",
    "LayerStat",
    "graph_stats",
    "FileEntry",
    "Hop",
    "Implementer",
    "IndexScope",
    "KconfigEntry",
    "KconfigGate",
    "KconfigSpace",
    "kconfig_space",
    "KeyEdge",
    "LockNesting",
    ## The COLLAPSED nesting identity carried by `lock_roster`, beside the per-site
    ## `LockNesting` that `lock_nestings` still returns. Both are exported because they
    ## answer different questions: how many nestings are there, and where are they.
    "LockNestingPair",
    ## gh#373 — the preprocessor layer, indexed since the beginning and reachable now.
    "MacroDef",
    "macro_definitions",
    "ProseHit",
    "ProseSearch",
    "SectionCall",
    "ReqEdge",
    "ReqRef",
    "ReqTrace",
    "SourceListing",
    ## gh#26/gh#372 — the subject-agnostic surface. `SUBJECT_KINDS` is the vocabulary a
    ## consumer branches on; `resolve_subject` says which kinds a name is; and
    ## `subject_dossier` builds the one that answers.
    "SUBJECT_KINDS",
    "SubjectDossier",
    "LockSubject",
    "VariableSite",
    "VariableSubject",
    "MAX_SUBJECT_DEPTH",
    "resolve_subject",
    ## Answers "is this miss an ABSENCE or a kind I cannot describe?" — exported because the
    ## honest wording of a negative depends on it (gh#6).
    "unresolved_kinds",
    ## Returns None for any subject that is not a function; `dossier` takes any kind.
    "function_dossier",
    "function_dossiers",
    ## The declaration-site excerpt a VARIABLE needs, beside the body excerpt a function
    ## needs. Exported together because a consumer choosing between them is choosing on
    ## the subject's kind, which this module also publishes.
    "DECLARATION_MAX_LINES",
    "declaration_excerpt",
    "SymbolHit",
    "SymbolRef",
    "OriginSplit",
    "Terminus",
    "Thread",
    "ThreadInventory",
    # functions
    "MAX_DIAGNOSED_TOKENS",
    ## The covered set `search` reads and `emptiness` words its reply from — exported so
    ## the two cannot name different corpora (gh#374).
    "SEARCHED_MEMBERDEF_KINDS",
    "unsearched_corpora",
    "all_req_edges",
    "callees",
    "NameAmbiguity",
    "callers",
    "name_ambiguity",
    "chain_trace",
    "dossier",
    ## The batch form and its refusal threshold. Exported together because a caller that
    ## cannot see the cap can only discover it by tripping it.
    "MAX_BATCH_SYMBOLS",
    "dossiers",
    "file_doc_rows",
    "has_prose_corpus",
    "member_doc_rows",
    "has_file_docs",
    "index_scope",
    "indexed_extensions",
    "directory_rollup",
    "doc_scope",
    "list_files",
    "lock_nestings",
    "lock_roster",
    "locks_held_when",
    "lookup_class",
    "req_trace",
    "resolve_symbol",
    "runs_under_lock",
    "search",
    "sections_in",
    "search_prose",
    "search_prose_graded",
    "source",
    "thread_of",
    "thread_roster",
    "token_hit_counts",
    # STALENESS — re-exported so the advice in README ("detect a stale index by
    # comparing CLEW_BUILD_VERSION") points at a COVERED symbol. It previously
    # pointed at `clew.signature`, which the same README classes as an
    # uncovered internal, so the only documented way to check freshness was
    # simultaneously promised and disclaimed.
    "CLEW_BUILD_VERSION",
    "read_build_signature",
    "index_unusable_reason",
]
