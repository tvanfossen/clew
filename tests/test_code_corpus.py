# SPDX-License-Identifier: MIT
"""`search(corpus='code')` finds the functions whose BODY contains the words.

FOUND BY THE 1.3.0 GRID. On mattermost-mobile Q1 an index-only agent had to say whether a failed
post is retried, and the answer is a literal inside a function body:

    retryPolicyConfiguration: {type: RetryTypes.EXPONENTIAL_RETRY, retryLimit: 3}

in `NetworkManagerSingleton.createClient`. No symbol is named for it, `search` read names and
briefs only, and an index-only agent has no grep — so the fact was unreachable however the agent
asked. A shell agent found it with one grep. The owner chose the general fix: full-text over every
indexed function's body, for every language.

A ROW IS A FUNCTION, so its `kind` goes straight back to `dossier` for the body and both edge
directions. Module-level text — a constants object, HOC wiring — is in the corpus through the
file's `__module__` row. ABSENT IS NOT EMPTY: an index built before this corpus existed has no
table, and the reply says so rather than reporting "no matches".

@brief Tests for the code-text search corpus.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.mcp_server.tools_query import QueryTools

_NETWORK = """\
export class NetworkManagerSingleton {
    createClient(url: string) {
        const config = {
            retryPolicyConfiguration: {type: 'EXPONENTIAL_RETRY', retryLimit: 3},
        };
        return buildClient(url, config);
    }
    other() { return 1; }
}
"""
_CONSTANTS = "export const ClientConstants = { POST_TIME_TO_FAIL: 10000 };\n"


## @brief Build the fixture and return tools bound to it.
## @param tmp_path Pytest temporary directory.
## @return QueryTools.
## @version 1
def _tools(tmp_path: Path) -> QueryTools:
    """@brief Build. @return Tools."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/network.ts").write_text(_NETWORK, encoding="utf-8")
    (repo / "src/constants.ts").write_text(_CONSTANTS, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return QueryTools(lambda: out, lambda: repo)


## @brief A literal inside a function body finds that function.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_body_literal_finds_its_function(tmp_path: Path) -> None:
    """THE INNERMOST FUNCTION RANKS FIRST: `createClient` holds the text, and the file's
    `__module__` row also contains it; the smaller unit is the answer.

    @brief retryLimit -> createClient.
    @return None.
    @version 1
    """
    rows = _tools(tmp_path).search("retryLimit", corpus="code")["results"]
    assert rows and rows[0]["name"] == "createClient", rows
    assert rows[0]["kind"] == "function", rows[0]
    assert "retryLimit" in rows[0]["snippet"], rows[0]
    assert "other" not in {r["name"] for r in rows}, rows


## @brief A constant in a module-level object is found through the file's `__module__`.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_module_level_constant_is_found(tmp_path: Path) -> None:
    """@brief POST_TIME_TO_FAIL -> constants.ts.
    @return None.
    @version 1
    """
    rows = _tools(tmp_path).search("POST_TIME_TO_FAIL", corpus="code")["results"]
    assert rows and rows[0]["file"] == "src/constants.ts", rows


## @brief An index without the corpus says so, rather than reporting no matches.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_an_index_without_the_corpus_says_it_is_missing(tmp_path: Path) -> None:
    """ABSENT IS NOT EMPTY: an index built before the corpus existed must not answer "no
    function contains this", which would be a measurement of nothing.

    @brief Missing corpus is disclosed.
    @return None.
    @version 1
    """
    import sqlite3

    tools = _tools(tmp_path)
    with sqlite3.connect(str(tools.db())) as conn:
        conn.execute("DROP TABLE code_text")
    reply = tools.search("retryLimit", corpus="code")
    assert reply["results"] == [] and "no code corpus" in reply["note"], reply


_RETRY_SRC = """\
export function buildRequestOptions(options: {noRetry?: boolean}) {
    if (options.noRetry) {
        return {retryPolicyConfiguration: {retryLimit: 0}};
    }
    return {};
}
"""
_E2E_SRC = "export function retry() { return 1; }\n"


## @brief A plain word finds the identifiers it is part of, and production code ranks above e2e.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_word_matches_inside_identifiers_and_e2e_ranks_last(tmp_path: Path) -> None:
    """FROM THE 1.3.0-TS-FIX TRANSCRIPTS. Q1's index-only agents DID use this corpus — three
    searches, for `retries`, `retry`, `createPost failed` — and missed because identifiers were
    indexed whole: `retry` matched neither `retryLimit` nor `noRetry`, the two tokens that hold the
    answer. And the smallest-body-first ranking put a one-line e2e helper named `retry` above
    everything. Now a compound identifier also contributes its parts, and test-scope code — which
    includes an `e2e/` directory — ranks below production code.

    @brief `retry` finds buildRequestOptions first.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "e2e/support").mkdir(parents=True)
    (repo / "src/tracking.ts").write_text(_RETRY_SRC, encoding="utf-8")
    (repo / "e2e/support/helpers.ts").write_text(_E2E_SRC, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    rows = QueryTools(lambda: out, lambda: repo).search("retry", corpus="code")["results"]
    assert rows and rows[0]["name"] == "buildRequestOptions", rows
    assert rows[-1]["file"].startswith("e2e/"), rows


## @brief An index without `test_scope` still answers a code search.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_code_search_works_without_the_test_scope_table(tmp_path: Path) -> None:
    """@brief Missing test_scope -> ranked without it, not an error.
    @return None.
    @version 1
    """
    import sqlite3

    tools = _tools(tmp_path)
    with sqlite3.connect(str(tools.db())) as conn:
        conn.execute("DROP TABLE test_scope")
    rows = tools.search("retryLimit", corpus="code")["results"]
    assert rows and rows[0]["name"] == "createClient", rows


## @brief An inflected word finds its stem: `retries` matches `retry`.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_an_inflected_word_finds_its_stem(tmp_path: Path) -> None:
    """FROM THE TRANSCRIPTS: one Q1 replicate searched `retries`, and identifiers say `retry`.

    @brief retries -> buildRequestOptions.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/tracking.ts").write_text(_RETRY_SRC, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    rows = QueryTools(lambda: out, lambda: repo).search("retries", corpus="code")["results"]
    assert rows and rows[0]["name"] == "buildRequestOptions", rows


## @brief A dotted query — a member access as the reader saw it — matches, never errors.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_dotted_query_matches_its_parts(tmp_path: Path) -> None:
    """FROM THE 1.3.0-TS-FIX2 TRANSCRIPTS: `props.failed` and `WebsocketEvents.REACTION_ADDED`
    raised inside the tool. The tokenizer splits on `.`, so a quoted token became a PHRASE, and a
    `detail=none` table cannot answer a phrase. A member access is what a reader copies out of a
    body, across every language (`ssl->state`, `self.config`), so it must match its parts.

    @brief config.retryPolicyConfiguration -> createClient.
    @return None.
    @version 1
    """
    rows = _tools(tmp_path).search("config.retryPolicyConfiguration", corpus="code")["results"]
    assert rows and rows[0]["name"] == "createClient", rows


## @brief An empty symbol search names the code corpus as where a key or literal lives.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_an_empty_symbol_search_points_at_the_code_corpus(tmp_path: Path) -> None:
    """FROM THE 1.3.0-TS-FIX2 TRANSCRIPTS: `search("REACTION_ADDED")` — an object property — read
    "definitive empty" and named only the prose corpus, so agents fell back to reading files.

    @brief The note names corpus='code'.
    @return None.
    @version 1
    """
    reply = _tools(tmp_path).search("retryLimit")
    assert reply["count"] == 0, reply
    assert "corpus='code'" in reply["note"], reply["note"]


## @brief A C function only AST recovery finds is in the corpus too.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_recovered_c_function_body_is_searchable(tmp_path: Path) -> None:
    """FROM THE 1.3.0-FINAL GRID: mbedtls's code corpus held 1,052 of 4,127 function bodies. The
    corpus was built before `recover_ast_symbols`, so every function doxygen's preprocessor skipped
    — all 234 in `library/ssl_tls.c`, under `#if defined(...)` — was invisible to code search, and
    index-only agents spent turns on empty results.

    @brief A body under an undefined `#if` is found by its literal.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/guarded.c").write_text(
        "#if defined(FEATURE_UNSET)\n"
        "int guarded_send(void)\n{\n    return GUARDED_RETRY_LIMIT_MARKER;\n}\n#endif\n",
        encoding="utf-8",
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    rows = QueryTools(lambda: out, lambda: repo).search(
        "GUARDED_RETRY_LIMIT_MARKER", corpus="code"
    )["results"]
    assert rows and rows[0]["name"] == "guarded_send", rows


## @brief A query word is a prefix: `MBEDTLS_ERR_` finds a body using `MBEDTLS_ERR_SSL_BAD_INPUT`.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_query_word_matches_as_a_prefix(tmp_path: Path) -> None:
    """FROM THE 1.3.0-FINAL GRID: mbedtls index-only agents searched `MBEDTLS_ERR_` and `mbedtls_ct_`
    — a family by its prefix, the way C names families — and got nothing, because the tokenizer
    keeps `_` inside a word and a word matched only whole. Every one of those empty replies cost
    the agent more turns of guessing.

    @brief A trailing-underscore family prefix finds its members.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/err.c").write_text(
        "int check(int x)\n{\n    if (x) return MBEDTLS_ERR_SSL_BAD_INPUT;\n    return 0;\n}\n",
        encoding="utf-8",
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    rows = QueryTools(lambda: out, lambda: repo).search("MBEDTLS_ERR_", corpus="code")["results"]
    assert rows and rows[0]["name"] == "check", rows
    assert "MBEDTLS_ERR_SSL_BAD_INPUT" in rows[0]["snippet"], rows[0]


## @brief A macro used only in a file-scope preprocessor line is found, as a file hit.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_preprocessor_line_outside_any_function_is_searchable(tmp_path: Path) -> None:
    """1.3.10, FROM THE MBEDTLS RE-MEASURE: every code search that still came back empty named a
    macro — `MBEDTLS_ALLOW_PRIVATE_ACCESS`, `MBEDTLS_CONSTANT_FLOW` — that appears only in
    `#if`/`#define` lines at file scope, outside every function body the corpus held. The file's
    uncovered text is now indexed too, and a match there is a `kind: "file"` hit naming the file
    and the matching line — a subject `dossier` accepts.

    @brief A file-scope `#if` is found by the macro it tests.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/gate.h").write_text(
        "#ifndef GATE_H\n#define GATE_H\n"
        "#if defined(FILE_SCOPE_ONLY_MARKER)\n#define GATE_ON 1\n#endif\n"
        "int gate_open(void)\n{\n    return 1;\n}\n#endif\n",
        encoding="utf-8",
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    rows = QueryTools(lambda: out, lambda: repo).search("FILE_SCOPE_ONLY_MARKER", corpus="code")[
        "results"
    ]
    assert rows, "a macro tested at file scope must be findable by code search"
    assert rows[0]["kind"] == "file" and rows[0]["file"] == "src/gate.h", rows
    assert rows[0]["line"] == 3 and "FILE_SCOPE_ONLY_MARKER" in rows[0]["snippet"], rows
