# SPDX-License-Identifier: MIT
"""Auto-detect a starter `.clew.yaml` for any repo (clew issue #54).

`.clew.yaml` lets any repo state its own conventions, which is what keeps
clew free of hardcoded assumptions — but it also means a repo answers nothing
until someone works out what to write in it. This package reads the repo and
proposes a DRAFT: a fully commented declaration in which every entry carries the
evidence it was derived from and the measured effect of applying it.

Its whole design problem is the opposite of a missing feature. A plausible,
wrong pattern that gets committed silently reshapes a repo's graph, and nothing
downstream can tell a fabricated edge from a real one. So every candidate is
gated on a DRY RUN — the candidate section is applied to a throwaway copy of the
index by the pipeline's own import function and the delta is counted (`dryrun`) —
and a candidate that does not pay off is REJECTED, with the reason printed in the
draft. Projection was tried and measured wrong by 67-87%; running the real code
has no such gap.

Layers, bottom up::

    astdefs / scanning     tree-sitter corpus: definitions, forwarding calls,
                           accessor-shaped call sites (never a text regex)
    sharedkey_detect       accessor families -> arity-gated writer/reader pairs
    threads_detect         transitive spawn-wrapper fixpoint
    dryrun                 apply a candidate to a copy of the index, count it
    *_report / notindexed  gate, judge, and write the evidence prose
    registry               run every section, assemble the Proposal
    render                 emit the all-comments draft (and `uncomment` it back)
    command                `clew propose`

@brief Public surface of the declaration proposer.
@version 1
"""

from __future__ import annotations

from .command import propose_main
from .context import Context
from .model import Entry, Proposal, Rejection, SectionProposal, SectionStatus
from .notindexed import report_not_indexed
from .registry import (
    HAND_DECLARED,
    build_context,
    db_status_summary,
    propose,
    scope_summary,
    section_names,
)
from .render import (
    YAML_MARKER,
    marked_lines,
    render_declaration,
    statement_from_draft,
    uncomment,
)
from .sharedkey_detect import split_accessor
from .sharedkey_report import propose_shared_key_patterns
from .threads_detect import propose_thread_patterns

__all__ = [
    "HAND_DECLARED",
    "YAML_MARKER",
    "Context",
    "Entry",
    "Proposal",
    "Rejection",
    "SectionProposal",
    "SectionStatus",
    "build_context",
    "db_status_summary",
    "marked_lines",
    "propose",
    "propose_main",
    "propose_shared_key_patterns",
    "propose_thread_patterns",
    "render_declaration",
    "report_not_indexed",
    "scope_summary",
    "section_names",
    "statement_from_draft",
    "split_accessor",
    "uncomment",
]
