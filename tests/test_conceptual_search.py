# SPDX-License-Identifier: MIT
"""The seven queries that misled a real agent, as tests, on this repo's own index.

Every query below is a VERBATIM query from a dogfooding session, with the answer
that session should have received. They are used rather than easier invented
equivalents because that is the whole evidence base: each one returned a
confident zero, each zero was wrong about the repository, and the note attached
to it told the agent not to check.

These run against the CANONICAL SELF-INDEX and skip when it has not been built.
That is a real limitation and it is
the honest one: no fixture reproduces "a query phrased as a concept against a
codebase whose functions are named for mechanics", and a unit-scale substitute
would pass while the property it stands in for regressed. The unit-scale halves
live in `test_filedocs.py` and `test_emptiness.py`.

@brief Conceptual-search regression tests against the built self-index.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.query import search

REPO_ROOT = Path(__file__).resolve().parents[1]


## @brief The built self-index, or skip when nothing has been built.
## @return Path to the self-index.
## @version 1
def _self_index_or_skip() -> Path:
    """@brief Resolve the canonical self-index, skipping when absent.
    @return Index path.
    @version 1
    """
    from clew.mcp_server.state import target_for

    db = Path(target_for(REPO_ROOT).db_path)
    if not db.exists():
        pytest.skip(f"no built self-index at {db} — build to enable the conceptual assertions")
    return db


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
    ("guard config discovery", "tests/test_guard_config_discovery.py"),
    ## gh#10: `search("self edge")` reached the six relevant functions; adding tokens did not.
    ("self-edge guard recursion", "tests/test_self_edges.py"),
]


## @brief A conceptual query reaches the code that is about that concept.
## @param query The verbatim query from the dogfooding session.
## @param expected_file The repo-relative file that must appear among the hits.
## @return None.
## @version 1
@pytest.mark.parametrize(("query", "expected_file"), CONCEPT_CASES)
def test_a_conceptual_query_reaches_the_relevant_file(query: str, expected_file: str) -> None:
    """Asserts on the FILE and not on a rank position. Ranking is allowed to move as the
    corpus grows; reachability is the contract, and pinning "first hit" would make an
    unrelated new module a test failure."""
    db = _self_index_or_skip()
    hits = search(db, query, limit=25)
    files = {hit.file for hit in hits}
    assert files, f"{query!r} returned nothing at all"
    assert expected_file in files, f"{query!r} reached {sorted(files)}, not {expected_file}"


## @brief The seventh query is honestly reported as over-specified, not as absent.
## @return None.
## @version 1
def test_an_over_specified_query_is_reported_not_answered() -> None:
    """The one documented query the fix does NOT turn into hits, recorded as such rather
    than quietly dropped from the list. Five tokens, each matching something on its own,
    no single unit carrying all five. The right outcome is an empty result that says it
    is not definitive and hands over the per-token counts — which
    `test_emptiness.test_a_miss_with_every_token_matching_advises_fewer_tokens` pins at
    unit scale. Here the claim is only that it is still empty, so nobody reads the
    before/after table as if all seven became hits."""
    db = _self_index_or_skip()
    assert search(db, "server entry command args build") == []
    ## And the shorter form a caller is now told to retry does work.
    assert search(db, "server entry", limit=25)


## @brief A file hit is labelled as a file, so it cannot be mistaken for a symbol.
## @return None.
## @version 1
def test_file_hits_are_labelled_and_do_not_displace_symbols() -> None:
    """Two properties at once. A `kind == 'file'` hit must never be handed to `dossier`
    as if it were a function name, so the label has to be there; and on a query that
    matches a real symbol strongly, the symbol must still come first — the file corpus
    exists to make a concept findable, not to bury the function that implements it."""
    db = _self_index_or_skip()
    hits = search(db, "ingest_file_docs", limit=10)
    assert hits[0].kind == "function"
    assert hits[0].name == "ingest_file_docs"
    for hit in hits:
        assert hit.kind != "file" or hit.provenance == "file_doc"
