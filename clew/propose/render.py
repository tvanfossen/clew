# SPDX-License-Identifier: MIT
"""Render a Proposal as a `.clew.yaml` draft a human can audit.

The rendering carries as much of this feature's weight as the detection does. A
proposed declaration is a claim about how a repo works, it gets committed, and
from then on it silently shapes every answer the graph gives — so a draft nobody
can check is worse than no draft. Every emitted entry is therefore printed under
the EVIDENCE it was derived from and the MEASURED delta it produced against a
real index, and every refused candidate is printed with the reason it was
refused. `sharedkey_report` says exactly this about its own gate; this module is
where the reader gets to see it.

**The document is ALL comments.** Written into a repo verbatim it changes
nothing, which is the property that makes a confidently wrong proposal
survivable. Activation is one mechanical edit: the YAML lines — and ONLY the YAML
lines — carry the marker `#| `, so deleting that prefix from a block turns it on
and nothing else in the file can be mistaken for it. `uncomment()` is the same
transform, and it is what lets a test prove the draft parses as the sections it
claims to propose.

@brief Render a Proposal as a commented, auditable `.clew.yaml` draft.
@version 1
"""

from __future__ import annotations

import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .model import Entry, Rejection, SectionProposal, SectionStatus

## The gutter that marks an activatable YAML line, and NOTHING else in the file.
## A reader (or `uncomment`) can therefore separate the proposal from the prose
## about it without parsing either.
YAML_MARKER = "#| "

## Comment width. Evidence lines are pre-formatted columns and are never wrapped;
## only prose is.
_WIDTH = 92

_TOP = "# " + "═" * (_WIDTH - 2)
_MID = "# " + "─" * (_WIDTH - 2)

_CONTRACT = (
    "EVERY LINE IN THIS FILE IS A COMMENT. Copied into a repo verbatim it changes "
    "NOTHING — deliberately: a wrong declaration does not fail a build, it silently "
    "reshapes the graph, so nothing here takes effect until a human turns it on. "
    "Until then clew will log that this file holds no mapping and it is using "
    "defaults; that log line is the confirmation that nothing here is in effect."
)

_ACTIVATE = (
    "TO ACTIVATE a block: delete the leading '" + YAML_MARKER + "' from each of its "
    "lines. Do that only after reading the EVIDENCE above it and the MEASURED numbers "
    "it produced. Re-run `clew propose` after any change to the index scope — every "
    "number here is computed against the CURRENT scope."
)

_STATUS_MEANING: dict[SectionStatus, str] = {
    SectionStatus.PROPOSED: "review the evidence below, then activate",
    SectionStatus.NO_CANDIDATES: "the detector RAN and found nothing to propose",
    SectionStatus.NOT_ANALYSED: "no detection happened — declare by hand if it applies",
    SectionStatus.NOT_APPLICABLE: "cannot apply to this repo",
    SectionStatus.ALREADY_DECLARED: "the repo already declares this",
    SectionStatus.REPORT_ONLY: "findings below, deliberately no YAML",
}


## @brief Render a whole proposal as a commented `.clew.yaml` draft.
## @param repo_root Repo the proposal describes.
## @param db_status Measuring-index summary (from registry.db_status_summary).
## @param scope Derived-scope summary (from registry.scope_summary).
## @param sections Every section's result, in render order.
## @return The complete draft text, ending in a newline.
## @version 1
## @req REQ-DDB-CONFIG-001
def render_declaration(
    repo_root: Path,
    db_status: Mapping[str, Any],
    scope: Mapping[str, Any],
    sections: Sequence[SectionProposal],
) -> str:
    """@brief Assemble the header, the section index and every section block."""
    lines = [*_header(repo_root, db_status, scope), *_summary(sections)]
    for section in sections:
        lines.extend(_section_block(section))
    return "\n".join(lines) + "\n"


## @brief The YAML lines a draft marks as activatable, marker removed.
## @param text A draft produced by render_declaration (or an edited copy of one).
## @return The unmarked YAML lines, in document order.
## @version 1
## @req REQ-DDB-CONFIG-001
def marked_lines(text: str) -> list[str]:
    """A line must START with the marker to count. The header's own instruction
    quotes the marker mid-sentence, and a substring test would pick that prose up
    as YAML — which is exactly the confusion the marker exists to remove.

    @brief Extract a draft's marked YAML lines.
    @version 1
    """
    marker = YAML_MARKER.rstrip()
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith(YAML_MARKER):
            out.append(line[len(YAML_MARKER) :])
        elif line.strip() == marker:
            out.append("")
    return out


## @brief Recover the active YAML from a rendered draft.
## @param text A draft produced by render_declaration (or an edited copy of one).
## @return The YAML formed by the marked lines, with the marker removed.
## @version 2
## @req REQ-DDB-CONFIG-001
def uncomment(text: str) -> str:
    """The exact transform an owner performs by hand, so a test can prove the
    draft parses to the sections it claims. Anything not carrying the marker is
    prose ABOUT the proposal and is dropped — which is why the marker exists.

    @brief Strip the activation marker, yielding real YAML.
    @version 2
    """
    lines = marked_lines(text)
    return "\n".join(lines) + ("\n" if lines else "")


## @brief The draft's activatable YAML as the mapping a build option accepts.
## @param text A draft produced by render_declaration (or an edited copy of one).
## @return Section name → section document; empty when the draft proposes nothing.
## @version 1
## @req REQ-DDB-CONFIG-008
def statement_from_draft(text: str) -> dict[str, Any]:
    """THE MACHINE PATH FROM A DRAFT TO A STATEMENT (gh#360), and the reason it is a
    separate function rather than a mode of the renderer: the draft stays all-comments and
    stays non-authoritative. `uncomment` performs the same transform an owner performs by
    hand; this parses the result into the exact `{section: document}` shape
    `buildoptions.apply_options` takes, so an agent can state a proposal on the next build
    without writing a file into a repository it does not own.

    IT IS STILL A PROPOSAL. Nothing here applies anything — a caller has to pass the value
    to `build_or_refresh(options=…)`, where it is validated as strictly as a parsed file.
    The draft being readable by a machine does not make it authoritative; an explicit
    statement is what counts, which is the whole distinction the all-comments contract
    exists to hold.

    A draft that proposes nothing yields `{}`, not an error: no candidate survived the dry
    run, which is a result. A recovered document that is not a mapping RAISES, because that
    could only mean this renderer emitted something malformed.

    @brief Parse a draft's activatable YAML into a statable options mapping.
    @return Section name → document.
    @version 1
    """
    import yaml

    body = uncomment(text)
    if not body.strip():
        return {}
    data = yaml.safe_load(body)
    if not isinstance(data, dict):
        raise ValueError(
            f"a draft's activatable lines did not parse to a mapping but to "
            f"{type(data).__name__} — the renderer emitted something malformed"
        )
    return data


## @brief The document header: what this is, what it was measured against.
## @param repo_root Repo the proposal describes.
## @param db_status Measuring-index summary.
## @param scope Derived-scope summary.
## @return Header comment lines.
## @version 2
## @dg_internal
def _header(repo_root: Path, db_status: Mapping[str, Any], scope: Mapping[str, Any]) -> list[str]:
    """@brief Render the draft's provenance header and its two contracts."""
    return [
        _TOP,
        "#  .clew.yaml — PROPOSED starter declaration (a DRAFT, not a config)",
        "#",
        f"#    repo:        {repo_root}",
        f"#    index scope: {_scope_line(scope)}",
        f"#    measured vs: {_db_line(db_status)}",
        "#",
        *_wrap(_CONTRACT, "#  "),
        "#",
        *_wrap(_ACTIVATE, "#  "),
        _TOP,
        "",
    ]


## @brief One-line description of the derived index scope.
## @param scope Derived-scope summary.
## @return The scope line.
## @version 3
## @dg_internal
def _scope_line(scope: Mapping[str, Any]) -> str:
    """The C/C++ count is stated separately from the parsed count because the
    parser router covers Python too: on a Python codebase the two differ, and only the
    first number describes what the R1 AST detectors could read.

    @brief Describe the scope every measured number was computed against.
    @version 3
    """
    head = (
        f"{scope['source']} — {scope['roots']} root(s), {scope['excludes']} exclude(s); "
        f"{scope['files_in_scope']} of {scope['files_parsed']} parsed source file(s) in scope, "
        f"{scope['ast_readable_in_scope']} of them C/C++"
    )
    return head if scope["derived"] else f"{head}   [NOT DERIVED: {scope['reason']}]"


## @brief One-line description of the index the proposal was measured against.
## @param db_status Measuring-index summary.
## @return The database line.
## @version 3
## @dg_internal
def _db_line(db_status: Mapping[str, Any]) -> str:
    """A missing index is stated rather than implied: it is the reason a gated
    section refuses to propose, and a reader who does not see it will read the
    refusal as "clew found nothing".

    @brief Describe the measuring index and its freshness.
    @version 2
    """
    if not db_status.get("usable"):
        return (
            "NO USABLE INDEX — nothing was measured, so every dry-run-gated section "
            "refuses to propose. Build the index and re-run."
            + (
                f"  [{db_status['path']} was REJECTED: it {db_status.get('defect')}]"
                if db_status.get("exists")
                else ""
            )
        )
    line = f"{db_status['path']} (build version {db_status.get('build_version')})"
    if db_status.get("stale"):
        line += (
            f"   [STALE: current pipeline is version "
            f"{db_status.get('expected_build_version')} — rebuild for exact numbers]"
        )
    return line


## @brief The section index: one row per section with its status and counts.
## @param sections Every section's result.
## @return Comment lines for the summary table.
## @version 1
## @dg_internal
def _summary(sections: Sequence[SectionProposal]) -> list[str]:
    """Up front because it is the only view that makes an OMISSION visible: every
    declaration section appears here, so a reader can see that a section was
    considered even when it produced nothing.

    @brief Render the per-section status table.
    @version 1
    """
    width = max((len(s.name) for s in sections), default=0)
    rows = [
        f"#    {s.name:<{width}}  {s.status.value:<16} {len(s.entries):>3} proposed"
        f" {len(s.rejections):>3} rejected"
        for s in sections
    ]
    return ["#  SECTIONS", *rows, "#", _MID, ""]


## @brief One section's whole block: status, evidence, YAML, rejections, notes.
## @param section The section result.
## @return Comment lines for that section.
## @version 1
## @dg_internal
def _section_block(section: SectionProposal) -> list[str]:
    """@brief Render one declaration section."""
    meaning = _STATUS_MEANING.get(section.status, "")
    return [
        f"# ══ {section.name} " + "═" * max(0, _WIDTH - 6 - len(section.name)),
        f"#  STATUS: {section.status.value.upper()}" + (f"  ({meaning})" if meaning else ""),
        *_wrap(section.reason, "#  WHY:   ", "#         "),
        *_checked(section.checked),
        "#",
        *_entries(section.entries),
        *_yaml_block(section),
        *_rejections(section.rejections),
        *_notes(section.notes),
        "",
    ]


## @brief The `checked` counters as one wrapped line.
## @param checked Counter mapping from the detector.
## @return Zero or more comment lines.
## @version 1
## @dg_internal
def _checked(checked: Mapping[str, Any]) -> list[str]:
    """@brief Render what a detector examined, so an empty result stays legible."""
    if not checked:
        return []
    body = ", ".join(f"{key}={value}" for key, value in checked.items())
    return _wrap(body, "#  CHECKED: ", "#           ")


## @brief The evidence for every accepted entry, numbered.
## @param entries Accepted entries.
## @return Comment lines.
## @version 1
## @dg_internal
def _entries(entries: Sequence[Entry]) -> list[str]:
    """Numbered and printed BEFORE the YAML block because the block is a single
    merged section — an owner activating it is activating all of them, and needs
    to have read each one's derivation first.

    @brief Render each accepted entry's evidence.
    @version 1
    """
    lines: list[str] = []
    for index, entry in enumerate(entries, start=1):
        lines.append(f"#  ── EVIDENCE {index} of {len(entries)} " + "─" * 20)
        lines.extend(f"#     {line}" for line in entry.evidence)
        lines.append("#")
    return lines


## @brief The activatable YAML block for a section, marked with the gutter.
## @param section The section result.
## @return Comment lines carrying the YAML, or a note that there is none.
## @version 1
## @dg_internal
def _yaml_block(section: SectionProposal) -> list[str]:
    """A section's block is its `yaml_header` followed by every entry's
    `yaml_lines`, in order — the one composition rule, so a new section brings its
    own shape and needs no branch here.

    @brief Render a section's YAML behind the activation marker.
    @version 1
    """
    body = [*section.yaml_header, *(line for entry in section.entries for line in entry.yaml_lines)]
    if not body:
        return []
    return [
        "#  ── ACTIVATE (delete the leading '" + YAML_MARKER.rstrip() + " ') " + "─" * 18,
        *(YAML_MARKER + line for line in body),
        "#",
    ]


## @brief Every refused candidate, with its reason and evidence.
## @param rejections The section's rejections.
## @return Comment lines.
## @version 2
## @dg_internal
def _rejections(rejections: Sequence[Rejection]) -> list[str]:
    """Part of the deliverable, not debug output. A candidate an owner EXPECTED to
    see is the one they will go looking for, and the refusal reason is the answer
    to "why not mine?" — without it the only available conclusion is that clew
    missed it.

    @brief Render the refused candidates.
    @version 2
    """
    if not rejections:
        return []
    lines = [f"#  ── REJECTED — {len(rejections)} candidate(s) considered and REFUSED " + "─" * 6]
    for index, item in enumerate(rejections, start=1):
        lines.append(f"#     {index}. {item.name}")
        lines.extend(_wrap(item.reason, "#        WHY: ", "#             "))
        lines.extend(f"#        {line}" for line in item.evidence)
        lines.append("#")
    return lines


## @brief A section's free-standing notes, wrapped.
## @param notes The section's notes.
## @return Comment lines.
## @version 1
## @dg_internal
def _notes(notes: Sequence[str]) -> list[str]:
    """@brief Render the section-level notes (NOT-DETECTED prose, conflicts)."""
    if not notes:
        return []
    lines = ["#  ── NOTES " + "─" * 30]
    for note in notes:
        lines.extend(_wrap(note, "#     ", "#     "))
    return lines


## @brief Wrap prose into comment lines at the document width.
## @param text The prose to wrap.
## @param first Prefix for the first line.
## @param rest Prefix for continuation lines (defaults to `first`).
## @return The wrapped comment lines.
## @version 1
## @dg_internal
def _wrap(text: str, first: str, rest: str | None = None) -> list[str]:
    """Only prose is wrapped. Evidence lines are pre-formatted columns and are
    emitted verbatim — wrapping them would destroy the alignment that makes a
    before/after measurement readable at a glance.

    @brief Wrap one prose paragraph into comment lines.
    @version 1
    """
    continuation = first if rest is None else rest
    wrapped = textwrap.wrap(
        text,
        width=_WIDTH,
        initial_indent=first,
        subsequent_indent=continuation,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped or [first.rstrip()]
