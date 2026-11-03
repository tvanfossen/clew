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
