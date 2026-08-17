# SPDX-License-Identifier: MIT
"""A STRUCTURED ZERO IS EVIDENCE — what the build looked for and did NOT find.

The pipeline computes its discovery diagnostics and used to throw them into the build
LOG, which is gone by the time anyone queries the index. That is the same defect scope
provenance and coverage each had, one layer over: computed, logged, discarded.

  * accessor FAMILIES no active shared-key pattern covers — the dataflow a repo has
    but has not declared, so its causal layer is silently sparse or empty.
  * xrefitem ALIAS tags no active event vocabulary claims — a repo documenting its bus
    as `@broadcasts`/`@reacts` produces zero event rows and says nothing, which is
    indistinguishable from a repo with no bus at all.
  * acquire/release PAIRS no active lock pattern covers (gh#385) — the LOCK layer's
    counterpart, and it was MISSING while the other two existed. mbedtls reported ONE
    lock identity, scope unknown, for a repository with five named global mutexes and
    38 lock sites, and a graded agent copied that into its answer as fact. Declaring the
    one primitive takes the layer to 10 identities and 46 acquisitions; nothing told the
    owner that. The number of these is deliberately EXPECTED to be small — measured, 1
    on mbedtls undeclared, 0 once declared, 0 on this repo — because a hint that fires
    often is one a reader learns to skip.

WHY THE ZERO IS THE POINT. "The diagnostic is silent" carries no information, and this
project has read a silent zero as a fact about a repository three times — most sharply
when a target's real accessors turned out to be MACROS with 1,093 call sites and zero
`kind='function'` rows, so the detector was structurally blind and the empty layer got
written down as a correct negative. Declaring two prefixes then produced 499 edges over
146 keys.

So a count of zero is WRITTEN and REPORTED, and it is reported beside the size of the
corpus it was measured over. `0 uncovered families over 3,784 examined names` is a
measurement. An absent key is not — it cannot be told apart from a diagnostic that never
ran, or an index built before the diagnostic existed.

EVERY VALUE IS RE-DERIVED HERE rather than threaded out of the stages that log it. Both
detectors are pure apart from reading one file each, and `cli` already documents this
choice for `key_alias_prefixes`: widening three stage signatures to carry a metadata row
is the worse trade. It is safe here for a reason that does NOT generalise — no column in
the database can disagree with these values, because what they describe is precisely the
rows that were never written. Where a stamped value does have a column to agree with
(gh#335's external roots) the opposite rule applies and the stage's own return is stamped.

@brief Collect and persist the build's discovery diagnostics, including their zeros.
@version 1
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .event_edges import DEFAULT_EVENT_TAGS, classify_aliases
from .locks import detect_undeclared_lock_primitives, load_lock_patterns
from .threads import detect_undeclared_spawn_primitives, load_thread_patterns
from .shared_key_edges import (
    ACCESSOR_CORPUS_KINDS,
    AccessorFamily,
    detect_undeclared_accessor_families,
    resolve_shared_key_patterns,
)

## The `build_meta` prefix these rows are stamped under, imported by both the writer and
## the reader so a drifted spelling cannot leave one of them silently reading nothing.
META_PREFIX = "diagnostics"

## How many names to spell out in a payload that rides along on every `status` call. The
## COUNT is always exact, so a truncated list is visible as `count > len(named)` rather
## than passing for the whole set — a cap that cannot be seen is how a bounded answer
## comes to read as a complete one.
MAX_NAMED = 8

## Which tier of vocabulary was in force, as a token a consumer can branch on. The point
## is not the word: an operator who declares `event_tags` and sees `built-in` here knows
## their declaration did not arrive, which no count can tell them.
SOURCE_DECLARED = "declared"
SOURCE_BUILT_IN = "built-in"


## @brief One build's discovery diagnostics, with the corpus each was measured over.
## @version 1
## @req REQ-DDB-CONFIG-007
@dataclass(frozen=True)
class BuildDiagnostics:
    """Frozen because it is a MEASUREMENT of one build. Every field defaults to the empty
    or zero case, so a caller that can only answer half of this still produces a valid
    record rather than omitting the section — an omitted section reads as "not recorded",
    which is the very ambiguity this exists to remove.

    @brief The diagnostics one build produced.
    @version 1
    """

    accessor_families: tuple[AccessorFamily, ...] = ()

    ## gh#385. Acquire/release pairs no active lock pattern covers — the LOCK layer's
    ## counterpart to `accessor_families`, and it exists because that counterpart was missing:
    ## mbedtls reported ONE lock identity for five global mutexes and 38 lock sites, and
    ## nothing told the owner that declaring `mbedtls_mutex_lock` would take it to 10 and 46.
    undeclared_lock_primitives: tuple[tuple[str, str], ...] = ()

    ## The THREAD layer's counterpart, added because the same gap was found here one issue
    ## later: `DEFAULT_SPAWN_PATTERNS` had no Windows entry while `_roster_meaning` told a
    ## reader to quote its count as the repository's thread count.
    ##
    ## READ ITS LIMIT BEFORE TRUSTING AN EMPTY LIST. It finds primitives this repository
    ## DECLARES, so a project's own spawn wrapper lands and an EXTERNAL platform API it
    ## merely calls does not — measured: run against mbedtls with no patterns it names
    ## `thread_create` and NOT `_beginthread`, the gap that prompted it. Empty therefore
    ## means 'nothing declared here looks like one', never 'coverage is complete'.
    undeclared_spawn_primitives: tuple[str, ...] = ()
    accessor_names_examined: int = 0
    unclaimed_aliases: tuple[str, ...] = ()
    event_vocabulary_source: str = SOURCE_BUILT_IN
    event_vocabulary_size: int = field(default=len(DEFAULT_EVENT_TAGS))

    ## @brief Flatten to string values for build_meta persistence.
    ## @return Mapping of unprefixed diagnostics keys to string values.
    ## @version 4
    ## @req REQ-DDB-CONFIG-007
    ## @req REQ-DDB-QUERY-011
    def as_meta(self) -> dict[str, str]:
        """Values are STRINGS, and the counts are non-negotiably strings, because
        `write_build_signature` DROPS falsy values: `0` vanishes and `"0"` survives. The
        whole requirement here is that a measured zero is recorded, so passing an int
        would reproduce the silent zero one layer down — in the persistence rather than
        in the detector. `coverage.as_meta` learned the same thing.

        The NAMED lists are allowed to be empty and therefore dropped, because their
        `_count` companion carries the measurement. That asymmetry is deliberate: a name
        list is evidence, a count is the claim, and only the claim must always be present.

        `accessor_families` NAMES ONLY THIS REPO'S (gh#352 half 3), while
        `accessor_families_count` keeps counting ALL of them and
        `accessor_families_external_count` says how many of that total are somebody else's. So
        the three keys still reconcile — first party + external == count — and a reader who
        sees `count: 9` beside an EMPTY name list learns the honest thing: nine were found and
        none are yours to declare. Measured across both public targets, that is exactly the
        state 11 of 11 families were in.

        @brief Diagnostics as build_meta values.
        @return Unprefixed key → string value.
        @version 3
        """
        ours = [f for f in self.accessor_families if not f.external_root]
        return {
            "accessor_families": ", ".join(
                f"{f.prefix}* ({f.keys} keys)" for f in ours[:MAX_NAMED]
            ),
            "accessor_families_count": str(len(self.accessor_families)),
            "accessor_families_first_party_count": str(len(ours)),
            "accessor_families_external_count": str(len(self.accessor_families) - len(ours)),
            "accessor_names_examined": str(self.accessor_names_examined),
            ## gh#385. The ACQUIRE side is what an operator declares, so that is what is
            ## named; the release half is derivable and would double the bytes to say it.
            "undeclared_lock_primitives": ", ".join(
                acquire for acquire, _release in self.undeclared_lock_primitives
            ),
            "undeclared_lock_primitives_count": str(len(self.undeclared_lock_primitives)),
            ## Capped like the alias list: a hint is a starting point, not an inventory.
            "undeclared_spawn_primitives": ", ".join(self.undeclared_spawn_primitives[:MAX_NAMED]),
            "undeclared_spawn_primitives_count": str(len(self.undeclared_spawn_primitives)),
            "unclaimed_event_aliases": ", ".join(self.unclaimed_aliases[:MAX_NAMED]),
            "unclaimed_event_aliases_count": str(len(self.unclaimed_aliases)),
            "event_vocabulary_source": self.event_vocabulary_source,
            "event_vocabulary_size": str(self.event_vocabulary_size),
        }


## @brief Count the DISTINCT memberdef names the accessor diagnostic searches.
## @param conn Open connection to the built database.
## @return Number of distinct names in the corpus, over the same kinds the detector reads.
## @version 1
## @req REQ-DDB-CONFIG-007
def accessor_corpus_size(conn: sqlite3.Connection) -> int:
    """THE DENOMINATOR, and it reads `ACCESSOR_CORPUS_KINDS` rather than restating the
    predicate. A zero measured against the wrong corpus is worse than no denominator at
    all: it would report that thousands of names were searched when the search read a
    different set, which is a false reassurance rather than a missing one.

    @brief Size of the corpus the accessor diagnostic examined.
    @return Distinct name count.
    @version 1
    """
    placeholders = ",".join("?" * len(ACCESSOR_CORPUS_KINDS))
    row = conn.execute(
        f"SELECT COUNT(DISTINCT name) FROM memberdef WHERE kind IN ({placeholders})",
        ACCESSOR_CORPUS_KINDS,
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


## @brief Measure both discovery diagnostics against a freshly built database.
## @param db_path Path to the built clew.db.
## @param doxyfile The Doxyfile whose ALIASES the event layer read.
## @param patterns_path Declared shared-key patterns document, or None for the built-in defaults.
## @param wrappers Second patterns document merged over the first (the dispatch manifest's wrappers).
## @param event_tags Declared event vocabulary REPLACING the built-in verbs, or None.
## @return The diagnostics for this build.
## @version 1
## @req REQ-DDB-CONFIG-007
def collect(
    db_path: Path | str,
    doxyfile: Path,
    patterns_path: Path | None,
    wrappers: Any | None,
    event_tags: dict[str, str] | None,
    lock_patterns: Path | dict | None = None,
    thread_patterns: Path | dict | None = None,
) -> BuildDiagnostics:
    """CALLED WITH THE SAME INPUTS THE STAGES GOT, which is the whole correctness
    argument for re-deriving rather than carrying. `cli` hoists both patterns arguments
    into locals for exactly this reason — two separately-built expressions can drift into
    resolving different things and one local cannot.

    NO try/except AROUND THE DATABASE. This runs immediately after the same process built
    and wrote that file, so an unreadable one is a real build failure; swallowing it would
    turn "cannot tell" into a healthy-looking zero, which is the failure mode the whole
    module exists to remove. An unreadable DOXYFILE is different and is handled inside
    `classify_aliases`: a synthesised Doxyfile legitimately has no ALIASES, and zero of
    each is the true answer for it.

    @brief Collect this build's discovery diagnostics.
    @return The measured diagnostics.
    @version 1
    """
    writers, readers, _aliases = resolve_shared_key_patterns(patterns_path, wrappers)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        families = detect_undeclared_accessor_families(conn, [*writers, *readers])
        examined = accessor_corpus_size(conn)
        ## gh#385, the LOCK layer's counterpart to the accessor hint. Re-derived from the same
        ## declaration the stage got, for the reason this function's docstring already gives:
        ## two separately-built expressions drift, one local does not.
        lock_pairs = detect_undeclared_lock_primitives(conn, load_lock_patterns(lock_patterns))
        ## Same re-derivation rule as the lock hint above: built from the declaration the
        ## stage got, not from a second expression that could resolve differently.
        spawn_names = detect_undeclared_spawn_primitives(
            conn, load_thread_patterns(thread_patterns)
        )
    finally:
        conn.close()
    _claimed, unclaimed = classify_aliases(doxyfile, event_tags)
    return BuildDiagnostics(
        accessor_families=tuple(families),
        accessor_names_examined=examined,
        undeclared_lock_primitives=tuple(lock_pairs),
        undeclared_spawn_primitives=tuple(spawn_names),
        unclaimed_aliases=unclaimed,
        event_vocabulary_source=SOURCE_BUILT_IN if event_tags is None else SOURCE_DECLARED,
        event_vocabulary_size=len(DEFAULT_EVENT_TAGS if event_tags is None else event_tags),
    )
