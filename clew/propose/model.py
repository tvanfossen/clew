# SPDX-License-Identifier: MIT
"""Frozen value types for a proposed `.clew.yaml`.

Pure data, no behaviour: the detectors produce these, the renderer consumes
them, and the MCP tool serialises them. Keeping the two surfaces on ONE set of
structures is what stops the CLI and the MCP tool from drifting into two
different answers about the same repo — the divergence class #49/#53/#56 were
all instances of.

The important shape decision is that a section reports what it did NOT find as
first-class data (`status` + `reason` + `checked` + `rejections`), not as prose
appended by the renderer. Silence about a section is then impossible to emit by
accident: `registry` enumerates every declaration section, and each one must
return a `SectionProposal` saying what happened.

@brief Frozen result types for the declaration proposer.
@version 1
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


## @brief What a detector concluded about one declaration section.
## @version 3
class SectionStatus(str, Enum):
    """Six outcomes, deliberately distinguished because they call for different
    owner actions: PROPOSED (review it), NO_CANDIDATES (the detector ran and
    found nothing), NOT_ANALYSED (no detector exists — declare by hand),
    NOT_APPLICABLE (the section cannot apply to this repo at all),
    ALREADY_DECLARED (the repo's own file already covers it) and REPORT_ONLY
    (findings exist but clew deliberately emits no YAML for them).

    A single "nothing here" status would collapse "we looked and there is
    nothing" into "we never looked", which is the difference between a measured
    absence and an omission.

    This was an `enum.StrEnum`, which is 3.11+ and therefore an import-time
    `ImportError` on this project's declared 3.10 floor — it killed the entire
    `propose` command rather than degrading it (gh#23).

    `(str, Enum)` is the obvious substitution and is NOT equivalent, which is why
    `__str__` and `__format__` are reassigned explicitly rather than inherited.
    `StrEnum.__str__` returns the member's VALUE; a plain mixin member renders as
    `SectionStatus.PROPOSED`, and 3.11 additionally changed `__format__` for mixin
    enums. Every `==` and `.value` comparison keeps passing either way, so the
    difference surfaces only in rendered output — a status interpolated into YAML,
    a log line or an MCP payload would have changed silently and no existing test
    would have noticed. `tests/test_py310_compat.py` pins the rendered form; it
    fails against the substitution without these two lines.

    @brief Outcome of one section's detection.
    @version 2
    """

    PROPOSED = "proposed"
    NO_CANDIDATES = "no_candidates"
    NOT_ANALYSED = "not_analysed"
    NOT_APPLICABLE = "not_applicable"
    ALREADY_DECLARED = "already_declared"
    REPORT_ONLY = "report_only"

    ## Restores `StrEnum` semantics. `__str__` is the load-bearing line; `__format__`
    ## is belt-and-braces and is DISCLOSED as redundant rather than left looking
    ## necessary, because deleting it fails no test and an unguarded mechanism that
    ## reads as load-bearing is how this repo has been misled before.
    ##
    ## Measured on 3.10.20 / 3.11.15 / 3.12.3 (`.claude/tmp/gh23_enum_probe.py`),
    ## rendering `str()`, f-string, `format()`, `%s`, `.format()` and `f"{x:>12}"`:
    ##
    ##   naive (str, Enum) : 3.10 wrong in str() and %s ONLY; 3.11+ wrong in ALL SIX
    ##   + __str__         : correct in all six on all three
    ##   + __format__ too  : identical — no path changes
    ##
    ## The asymmetry is the reason the test asserts every path separately instead of
    ## spot-checking one: on 3.10 an f-string alone would have PASSED the careless
    ## substitution, so a test written against the floor interpreter would have
    ## certified a bug that only appears on 3.11+. `__format__` stays because
    ## `Enum.__format__` deferring to an overridden `__str__` is CPython's internal
    ## coupling rather than a documented promise, and one line is a cheap way not to
    ## depend on it — but it is retained knowingly, not because anything measured
    ## needs it.
    __str__ = str.__str__
    __format__ = str.__format__


## @brief One proposed declaration entry: its YAML, its evidence, its measurement.
## @version 2
@dataclass(frozen=True)
class Entry:
    """`yaml_lines` are the raw (uncommented) YAML for this entry; the renderer
    comments them out. `evidence` is the human-readable derivation — where the
    thing is defined, what chain reaches a primitive, which call sites attribute
    it. `measured` holds the dry-run numbers, empty when no index was available.

    `yaml_lines` may be EMPTY, in which case the section carries the whole block
    in `yaml_header` and this entry contributes only evidence. That is not an
    omission: `shared_key_patterns` splits its entries across two sibling LISTS
    (`writers:` / `readers:`), so a per-entry block would repeat both mapping keys
    and YAML would silently keep only the last — deleting a real proposal with no
    error. A section whose entries interleave keys composes at section level.

    @brief One proposed entry with its evidence and measured yield.
    @version 2
    """

    yaml_lines: tuple[str, ...]
    evidence: tuple[str, ...] = ()
    measured: Mapping[str, object] = field(default_factory=dict)


## @brief A candidate the detector found and deliberately refused.
## @version 1
@dataclass(frozen=True)
class Rejection:
    """Rejections are part of the deliverable, not debug output: a C/POSIX library's
    strongest spawn wrapper is REJECTED (defined outside the index scope) and an
    owner who cannot see that will conclude clew missed it.

    @brief One refused candidate plus why.
    @version 1
    """

    name: str
    reason: str
    evidence: tuple[str, ...] = ()


## @brief One declaration section's full result.
## @version 2
@dataclass(frozen=True)
class SectionProposal:
    """`checked` carries the counts that make an empty `entries` legible (files
    scanned, call sites examined, families found). `notes` carry statements that
    belong to the section but are not tied to one entry — the NOT-DETECTED
    prose, the cross-section conflicts.

    @brief Detection result for one `.clew.yaml` section.
    @version 1
    """

    name: str
    status: SectionStatus
    reason: str
    checked: Mapping[str, object] = field(default_factory=dict)
    entries: tuple[Entry, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    notes: tuple[str, ...] = ()
    ## The section's own YAML preamble (`thread_patterns:` + its `spawns:` key) —
    ## or, for a section whose entries interleave sibling keys, the WHOLE block
    ## (see `Entry.yaml_lines`). It lives here rather than in the renderer so the
    ## renderer stays generic: a section's block is always this followed by every
    ## entry's `yaml_lines`, so a new section brings its own shape and needs no
    ## new branch.
    yaml_header: tuple[str, ...] = ()


## @brief A whole proposed starter declaration for one repo.
## @version 1
@dataclass(frozen=True)
class Proposal:
    """`yaml_text` is the rendered document and is ALWAYS entirely comments —
    written verbatim into a repo it changes nothing, which is the property that
    makes a confidently-wrong proposal survivable.

    @brief The complete proposal for one target repo.
    @version 1
    """

    repo_root: Path
    db_path: Path | None
    db_status: Mapping[str, object]
    scope: Mapping[str, object]
    sections: tuple[SectionProposal, ...]
    yaml_text: str
