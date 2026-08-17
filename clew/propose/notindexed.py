# SPDX-License-Identifier: MIT
"""Report what is NOT indexed — and refuse to emit an `index_scope:` block.

This section is REPORT_ONLY by design, and the design is the finding. Two
measured facts kill the proposer that would otherwise live here:

1. **`index_scope.roots` REPLACES the whole scope, it does not extend it.**
   `scope.derive_scope` takes the declared branch as soon as one usable root is
   declared, and builds its roots from the declaration alone. An owner who
   uncomments a proposed `roots:` line they genuinely want therefore NARROWS the
   index to exactly that line — dropping everything the Doxyfile or the whole-repo
   tier was covering — and `derive_scope_logged` reports that as a SUCCESSFUL
   derivation. There is no emission format that makes this safe, because
   emission is the proposer's only output.

2. **Test and mock trees silently CHANGE existing answers.** In one reference
   repo, six test doubles collide with production definitions at BYTE-IDENTICAL
   signatures, so `query/_common.is_overloaded` (distinct signature count > 1)
   returns False and `dossier` can return the fake body with no candidates list.
   In another, the candidate tree defines 79 `main`s, and
   `reachability.DEFAULT_ENTRY_PATTERNS` seeds `main` — manufacturing false
   LIVES, which nothing surfaces.

So this module states the facts, names the hazards, and tells the owner to widen
the doxygen-guard `files:` pattern instead. It emits no YAML at all.

@brief Report-only findings about source outside the index scope.
@version 2
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..gitenv import git_env
from ..reachability import DEFAULT_ENTRY_PATTERNS
from ..scope import INDEX_SCOPE_SECTION
from .context import Context
from .model import SectionProposal, SectionStatus

## Directories listed in the report. Sorted by definition count, so the ones
## that would actually change the index come first.
_MAX_DIRS = 6

_REPLACE_SEMANTICS = (
    "clew will NOT write an `index_scope:` block, for two measured reasons: "
    "(1) `index_scope.roots` REPLACES the scope (clew/scope.py, derive_scope) "
    "— it does not extend it. Declaring the directories below would narrow the index "
    "to exactly those, dropping everything the Doxyfile INPUT or the whole-repo tier "
    "currently covers, and the build would log that as a successful derivation. "
    "(2) Test and mock trees redefine production symbols with identical "
    "signatures and add reachability entry points. Both silently CHANGE existing "
    "answers: clew would resolve a fake definition without flagging an "
    "overload, and dead code would start reporting as live. "
    "To widen the index today, add the directory to an `index_scope: roots:` list "
    "that also names everything already covered."
)


## @brief One directory holding git-tracked source outside the index scope.
## @version 1
@dataclass(frozen=True)
class NotIndexedDir:
    """@brief A candidate directory: its file/definition counts and hazards.

    @version 1
    """

    name: str
    files: int
    definitions: int
    shadowed: tuple[str, ...]
    entry_seeds: int


## @brief Git-tracked repo-relative paths, or None when git is unavailable.
## @param repo_root Repo root to query.
## @return Set of tracked repo-relative POSIX paths, or None.
## @version 3
## @req REQ-DDB-CONFIG-001
def tracked_files(repo_root: Path) -> frozenset[str] | None:
    """Tracked-only is what keeps submodule and vendored trees out of the
    report: a gitlink's contents are not listed by the superproject, so a
    third-party checkout never appears as a directory an owner should index.

    @brief List the repo's git-tracked files.
    @version 3
    """
    try:
        ## `env=git_env()`: an absolute `GIT_DIR` exported to a hook overrides `cwd`, so
        ## without it this lists the HOOK's repository and every file in the target repo
        ## reads as untracked. See `clew.gitenv`.
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            env=git_env(),
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return frozenset(part for part in proc.stdout.split("\0") if part)


## @brief Whether a name matches one of the reachability entry-point patterns.
## @param name Function name to test.
## @return True when the name would be seeded LIVE by mark_reachability.
## @version 2
## @req REQ-DDB-CONFIG-001
def seeds_reachability(name: str) -> bool:
    """Mirrors `reachability.DEFAULT_ENTRY_PATTERNS` as SQLite would apply it:
    LIKE is ASCII-case-insensitive and `%` is any run of characters.

    THE SECOND CONSUMER of that constant, and it reads the WHOLE default set on
    purpose. gh#319 split the constant into a tier-3 half (`ENTRY_PATTERN_FACTS` —
    `main`, `app_main`) and a tier-5 half (`ENTRY_PATTERN_HEURISTICS`); reading
    either half alone here would make the proposer and the reachability pass
    disagree about what an entry point is, and the disagreement would surface as a
    hazard warning that omits the very `main` collision this module exists to warn
    about. `DEFAULT_ENTRY_PATTERNS` is the composed set, so the two cannot drift —
    and `tests/test_tiers.py` pins the agreement against the resolver's own
    no-statement result rather than against the constant, so a change to how the
    default set is composed fails here too.

    Deliberately reads the DEFAULT set and not the resolved one: the proposer runs
    before any build and has no `args`, no declaration-driven resolution and no
    stamped record to consult. It is warning about what a build WOULD do absent a
    statement, which is exactly the default set.

    @brief Test a name against the reachability entry-point seeds.
    @version 2
    """
    lowered = name.lower()
    return any(_like(lowered, pattern) for pattern in DEFAULT_ENTRY_PATTERNS)


## @brief Apply one SQL LIKE pattern (only `%` wildcards) to a lowercased name.
## @param lowered The lowercased candidate name.
## @param pattern The LIKE pattern.
## @return True when the pattern matches the whole name.
## @version 1
## @dg_internal
def _like(lowered: str, pattern: str) -> bool:
    """@brief Evaluate a `%`-only LIKE pattern."""
    parts = pattern.lower().split("%")
    if len(parts) == 1:
        return lowered == parts[0]
    return _like_parts(lowered, parts)


## @brief Match the fixed segments of a `%`-split LIKE pattern in order.
## @param lowered The lowercased candidate name.
## @param parts The pattern split on `%`.
## @return True when every segment occurs in order with the anchors honoured.
## @version 1
## @dg_internal
def _like_parts(lowered: str, parts: list[str]) -> bool:
    """@brief Sequentially match a LIKE pattern's literal segments."""
    if not lowered.startswith(parts[0]) or not lowered.endswith(parts[-1]):
        return False
    pos = len(parts[0])
    for segment in parts[1:-1]:
        found = lowered.find(segment, pos)
        if found < 0:
            return False
        pos = found + len(segment)
    return pos <= len(lowered) - len(parts[-1])


## @brief Group out-of-scope definitions into candidate directories.
## @param ctx Shared detector inputs.
## @param tracked Git-tracked repo-relative paths, or None when unknown.
## @return Candidate directories, largest first.
## @version 1
## @req REQ-DDB-CONFIG-001
def candidate_dirs(ctx: Context, tracked: frozenset[str] | None) -> list[NotIndexedDir]:
    """@brief Summarise the source that sits outside the derived index scope."""
    in_scope_names = {
        name for name, defs in ctx.corpus.defs.items() if any(d.in_scope for d in defs)
    }
    buckets: dict[str, dict] = {}
    for name, defs in ctx.corpus.defs.items():
        for fdef in defs:
            if fdef.in_scope or (tracked is not None and fdef.rel_path not in tracked):
                continue
            bucket = buckets.setdefault(
                fdef.rel_path.split("/")[0],
                {"files": set(), "defs": 0, "shadowed": set(), "seeds": 0},
            )
            bucket["files"].add(fdef.rel_path)
            bucket["defs"] += 1
            bucket["seeds"] += 1 if seeds_reachability(name) else 0
            if name in in_scope_names:
                bucket["shadowed"].add(name)
    return _as_dirs(buckets)


## @brief Convert the grouping buckets into sorted NotIndexedDir records.
## @param buckets Directory name -> accumulated counts.
## @return Records sorted by definition count, largest first.
## @version 1
## @dg_internal
def _as_dirs(buckets: dict[str, dict]) -> list[NotIndexedDir]:
    """@brief Freeze the candidate-directory accumulator."""
    return sorted(
        (
            NotIndexedDir(
                name=name,
                files=len(data["files"]),
                definitions=data["defs"],
                shadowed=tuple(sorted(data["shadowed"])),
                entry_seeds=data["seeds"],
            )
            for name, data in buckets.items()
        ),
        key=lambda d: (-d.definitions, d.name),
    )


## @brief Warn when a proposed section's evidence reaches outside the index.
## @param sections Sections detected so far.
## @param dirs Candidate directories outside the index scope.
## @return Zero or more warning lines.
## @version 1
## @req REQ-DDB-CONFIG-001
def cross_section_conflicts(
    sections: Sequence[SectionProposal], dirs: Sequence[NotIndexedDir]
) -> tuple[str, ...]:
    """The proposals above are computed from the CURRENT scope. If an owner
    widens the index, the accessor families and spawn censuses change — so a
    proposal whose own evidence already mentions a not-indexed directory has to
    say that its numbers are conditional.

    @brief Cross-warn when a proposal's evidence crosses the scope boundary.
    @version 1
    """
    names = {d.name for d in dirs}
    hits = {
        line.strip()
        for section in sections
        for entry in section.entries
        for line in entry.evidence
        if "OUTSIDE the index scope" in line
    }
    if not hits or not names:
        return ()
    return (
        "CONFLICT: a proposal above has call sites outside the index scope. "
        "If you widen the index, RE-RUN this command — the proposals are "
        "computed from the current scope and will change.",
        *sorted(hits),
    )


## @brief Build the report-only `index_scope` section.
## @param ctx Shared detector inputs.
## @param sections Sections detected so far (for cross-section warnings).
## @return A REPORT_ONLY SectionProposal that never carries YAML.
## @version 1
## @req REQ-DDB-CONFIG-001
def report_not_indexed(ctx: Context, sections: Sequence[SectionProposal]) -> SectionProposal:
    """@brief Report out-of-scope source without proposing any index_scope YAML."""
    tracked = tracked_files(ctx.repo_root)
    dirs = candidate_dirs(ctx, tracked)
    notes = [
        f"Your derived scope is {ctx.scope.source} — {len(ctx.scope.roots)} root(s), "
        f"{len(ctx.scope.excludes)} exclude(s), covering "
        f"{ctx.corpus.files_in_scope} of {ctx.corpus.files_parsed} parsed source files.",
        *_dir_lines(dirs),
        _REPLACE_SEMANTICS,
        *cross_section_conflicts(sections, dirs),
    ]
    if tracked is None:
        notes.append(
            "NOTE: `git ls-files` was unavailable, so vendored/submodule trees "
            "could not be excluded from the directory list above."
        )
    return SectionProposal(
        name=INDEX_SCOPE_SECTION,
        status=SectionStatus.REPORT_ONLY,
        reason="NOT PROPOSED BY DESIGN — see the note below (report only, no YAML).",
        checked={
            "directories_outside_scope": len(dirs),
            "definitions_outside_scope": sum(d.definitions for d in dirs),
            "shadowed_symbols": sum(len(d.shadowed) for d in dirs),
        },
        notes=tuple(notes),
    )


## @brief One report line per candidate directory, with its hazards.
## @param dirs Candidate directories.
## @return Report lines.
## @version 1
## @dg_internal
def _dir_lines(dirs: Sequence[NotIndexedDir]) -> list[str]:
    """@brief Describe each out-of-scope directory and what indexing it would do."""
    if not dirs:
        return ["No git-tracked source sits outside the derived index scope."]
    lines = [
        f"{len(dirs)} director(ies) hold git-tracked source outside it. Largest, with hazards:"
    ]
    for entry in dirs[:_MAX_DIRS]:
        hazards = []
        if entry.shadowed:
            hazards.append(
                f"{len(entry.shadowed)} symbol(s) SHADOW in-scope definitions "
                f"({', '.join(entry.shadowed[:3])})"
            )
        if entry.entry_seeds:
            hazards.append(f"{entry.entry_seeds} reachability entry-pattern match(es)")
        lines.append(
            f"  {entry.name:<12} {entry.files} file(s) / {entry.definitions} definition(s)"
            + (f" — {'; '.join(hazards)}" if hazards else "")
        )
    return lines
