# SPDX-License-Identifier: MIT
"""The seven queries that misled a real agent, as tests, on this repo's own index.

Every query below is a VERBATIM query from a dogfooding session, with the answer
that session should have received. They are used rather than easier invented
equivalents because that is the whole evidence base: each one returned a
confident zero, each zero was wrong about the repository, and the note attached
to it told the agent not to check.

These run against a REAL SELF-INDEX — the integration tier's session `self_index_db`, built
cold from this checkout — and never skip. ROUND 4, R14: they used to read the operator's
canonical self-index and `pytest.skip` when it was absent, which under the gate (an isolated
state directory) was always: 8 skips in every gate run, the 3 the 2026-11-16 demo wiki showed.
No fixture reproduces "a query phrased as a concept against a
codebase whose functions are named for mechanics", and a unit-scale substitute
would pass while the property it stands in for regressed. The unit-scale halves
live in `test_filedocs.py` and `test_emptiness.py`.

@brief Conceptual-search regression tests against the built self-index.
@version 2
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.query import search


## The query, and a file that MUST appear among its hits. Each pairing is the
## "what exists" column of gh#10's own table, or the symbol named in gh#21/gh#31.
CONCEPT_CASES = [
    ## gh#10: five files discuss deadlock; `query/locks.py`'s brief says "lock nesting".
    ## The issue's "Done means" is this exact reachability.
    ("deadlock", "clew/query/locks.py"),
    ## gh#10: a module whose docstring is an essay on resolving function-pointer calls,
    ## while every function in it is named for a mechanic (`_harvest_registration`).
    ("function pointer", "clew/callback_edges.py"),
    ## gh#10: literally the mechanism that module implements.
    ("callback assignment", "clew/callback_edges.py"),
    ## gh#31: `_roots`, `_target_from_roots`, `_roots_askable` and `ensure_target` all live
    ## here and were all indexed while the three-token query returned zero.
    ("roots target resolution", "clew/mcp_server/server.py"),
    ## gh#10: `search("guard config")` gave 12 hits and adding one token gave none.
    ## FIXTURE CHANGED (round 4, R14), the property kept: the original pair named
    ## tests/test_guard_config_discovery.py, deleted by 35049cfd when the guard config moved to
    ## one fixed location (`guard:` in .clew.yaml) and "discovery" stopped existing. The skip hid
    ## that for six weeks. The added token is now one the concept still has.
    ("guard config section", "clew/guardconfig.py"),
    ## gh#10: `search("self edge")` reached the six relevant functions; adding tokens did not.
    ("self-edge guard recursion", "tests/test_self_edges.py"),
]


## @brief A conceptual query reaches the code that is about that concept.
## @param query The verbatim query from the dogfooding session.
## @param expected_file The repo-relative file that must appear among the hits.
## @param self_index_db The integration tier's cold self-index (R14: no skip).
## @return None.
## @version 2
@pytest.mark.parametrize(("query", "expected_file"), CONCEPT_CASES)
def test_a_conceptual_query_reaches_the_relevant_file(
    query: str, expected_file: str, self_index_db: Path
) -> None:
    """Asserts on the FILE and not on a rank position. Ranking is allowed to move as the
    corpus grows; reachability is the contract, and pinning "first hit" would make an
    unrelated new module a test failure."""
    db = self_index_db
    hits = search(db, query, limit=25)
    files = {hit.file for hit in hits}
    assert files, f"{query!r} returned nothing at all"
    assert expected_file in files, f"{query!r} reached {sorted(files)}, not {expected_file}"


## @brief The seventh query is honestly reported as over-specified, not as absent.
## @param self_index_db The integration tier's cold self-index (R14: no skip).
## @return None.
## @version 2
def test_an_over_specified_query_is_reported_not_answered(self_index_db: Path) -> None:
    """The one documented query the fix does NOT turn into hits, recorded as such rather
    than quietly dropped from the list. Five tokens, each matching something on its own,
    no single unit carrying all five. The right outcome is an empty result that says it
    is not definitive and hands over the per-token counts — which
    `test_emptiness.test_a_miss_with_every_token_matching_advises_fewer_tokens` pins at
    unit scale. Here the claim is only that it is still empty, so nobody reads the
    before/after table as if all seven became hits."""
    db = self_index_db
    assert search(db, "server entry command args build") == []
    ## And the shorter form a caller is now told to retry does work.
    assert search(db, "server entry", limit=25)


## @brief A file hit is labelled as a file, so it cannot be mistaken for a symbol.
## @param self_index_db The integration tier's cold self-index (R14: no skip).
## @return None.
## @version 2
def test_file_hits_are_labelled_and_do_not_displace_symbols(self_index_db: Path) -> None:
    """Two properties at once. A `kind == 'file'` hit must never be handed to `dossier`
    as if it were a function name, so the label has to be there; and on a query that
    matches a real symbol strongly, the symbol must still come first — the file corpus
    exists to make a concept findable, not to bury the function that implements it."""
    db = self_index_db
    hits = search(db, "ingest_file_docs", limit=10)
    assert hits[0].kind == "function"
    assert hits[0].name == "ingest_file_docs"
    for hit in hits:
        assert hit.kind != "file" or hit.provenance == "file_doc"
