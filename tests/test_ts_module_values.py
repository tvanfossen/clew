# SPDX-License-Identifier: MIT
"""A module-level constant and a type alias are definitions.

FROM THE 1.3.0-TS-FIX2 TRANSCRIPTS. Index-only agents asked `dossier("SearchRef")` and
`search("REACTION_ADDED")` and were told, definitively, that neither exists — while a shell agent
read `export type SearchRef = {...}` and `const WebsocketEvents = {REACTION_ADDED: ...}` straight
from the file. Measured on mattermost-mobile at 4d842026 (grep over `app/`): 1,341 type aliases
and about 2,700 module-level non-function constants were absent from every corpus but the code
text. A definition the index does not hold is a definitive negative that is false.

A CONSTANT IS A `variable` row and an alias a `typedef` row, with their declared type, so
`dossier` shows the declaration as it does for a C variable. Only MODULE-LEVEL bindings: a
function's locals are its body, which `dossier` already returns. A binding whose value is a
function is a function, written elsewhere.

@brief Tests for TS module constants and type aliases as definitions.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.mcp_server.tools_query import QueryTools

_SOURCE = """\
export type SearchRef = {
    focus: () => void;
    blur: () => void;
};

export const WebsocketEvents = {
    REACTION_ADDED: 'reaction_added',
};

const POST_TIME_TO_FAIL = 10000;

export const handler = () => POST_TIME_TO_FAIL;

export function screen() {
    const localOnly = 3;
    return localOnly;
}
"""


## @brief Build the fixture and return tools bound to it.
## @param tmp_path Pytest temporary directory.
## @return QueryTools.
## @version 1
def _tools(tmp_path: Path) -> QueryTools:
    """@brief Build. @return Tools."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/search.ts").write_text(_SOURCE, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return QueryTools(lambda: out, lambda: repo)


## @brief A module-level constant is a variable with its declaration.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_module_constant_is_a_variable(tmp_path: Path) -> None:
    """@brief WebsocketEvents and POST_TIME_TO_FAIL resolve; a local and a function do not.
    @return None.
    @version 1
    """
    tools = _tools(tmp_path)
    reply = tools.dossier("WebsocketEvents")
    assert reply.get("subject_kind") == "variable", reply
    assert "REACTION_ADDED" in str(reply), reply
    assert tools.dossier("POST_TIME_TO_FAIL").get("subject_kind") == "variable"
    assert tools.dossier("handler").get("subject_kind") == "function"
    assert tools.dossier("localOnly").get("found") is False


## @brief A type alias is a typedef subject carrying its declaration.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 2
def test_a_type_alias_is_a_typedef_with_its_declaration(tmp_path: Path) -> None:
    """@brief dossier("SearchRef") shows its whole declaration.
    @return None.
    @version 2
    """
    reply = _tools(tmp_path).dossier("SearchRef")
    assert reply.get("subject_kind") == "typedef", reply
    lines = reply["sites"][0]["declaration"]["lines"]
    ## THE WHOLE STATEMENT, not its first member: a type's members end in `;` too, and the
    ## excerpt stopped at the first one — measured on mattermost, `SearchRef` showed one member.
    assert any("blur" in ln for ln in lines) and lines[-1].strip() == "};", lines


## @brief A typed module constant is not receiver evidence for another file's member call.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_typed_module_constant_does_not_type_another_files_receiver(tmp_path: Path) -> None:
    """CAUGHT ON MATTERMOST BEFORE COMMIT: writing module constants with their types fed them into
    receiver typing, which is keyed by the bare member NAME — so a test file's
    `const client: Other` contradicted every `client.getRoute()` in the tree, and 370 functions'
    refused-site counts vanished (1,276 -> 906) with call edges unchanged. Receiver typing reads a
    CLASS MEMBER's declared type; a module constant is not one.

    @brief ClientBase.getRoute keeps its refused site.
    @return None.
    @version 1
    """
    import sqlite3

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/base.ts").write_text(
        "export class ClientBase { getRoute() { return 1; } }\n"
        "export class Other { other() { return 2; } }\n",
        encoding="utf-8",
    )
    (repo / "src/fixture.ts").write_text("const client: Other = new Other();\n", encoding="utf-8")
    (repo / "src/use.ts").write_text(
        "export function use(client: any) { return client.getRoute(); }\n", encoding="utf-8"
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    conn = sqlite3.connect(out)
    rows = conn.execute(
        "SELECT m.definition FROM memberdef m WHERE m.name = 'getRoute' AND ("
        "m.rowid IN (SELECT callee_rowid FROM unresolved_inbound) OR "
        "m.rowid IN (SELECT callee_rowid FROM call_edges))"
    ).fetchall()
    assert rows, "the client.getRoute() site was dropped by an unrelated module constant's type"


## @brief An interface signature candidate reports its own line, never the bodiless sentinel.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_signature_candidate_reports_its_line(tmp_path: Path) -> None:
    """FROM THE 1.3.0-TS-FIX2 TRANSCRIPTS: every `dossier("createPost")` listed
    `ClientPostsMix.createPost` with `line_start: -1` — the `bodystart` a bodiless signature row
    is written with, leaking onto the wire as if it were a line. A declaration reports where it is
    declared.

    @brief The signature's candidate line is its declaration line.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/posts.ts").write_text(
        "export interface PostsMix {\n    createPost: (p: string) => number;\n}\n"
        "export function createPost(p: string) { return 1; }\n",
        encoding="utf-8",
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    reply = QueryTools(lambda: out, lambda: repo).dossier("createPost")
    lines = {c["qualified"]: c["line_start"] for c in reply["candidates"]}
    assert lines.get("src.posts.PostsMix.createPost") == 2, reply["candidates"]


_EVENTS = "export const Events = {\n" + "".join(f"    E{i}: 'e{i}',\n" for i in range(12)) + "};\n"
_MANAGER = """\
export class Manager {
    private DEFAULT_CONFIG = {
        retryPolicyConfiguration: {retryLimit: 3},
    };
    run() { return 1; }
}
"""


## @brief Build a fixture of a long constants object and a class with an untyped config field.
## @param tmp_path Pytest temporary directory.
## @return QueryTools.
## @version 1
def _extent_tools(tmp_path: Path) -> QueryTools:
    """@brief Build. @return Tools."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/events.ts").write_text(_EVENTS, encoding="utf-8")
    (repo / "src/manager.ts").write_text(_MANAGER, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return QueryTools(lambda: out, lambda: repo)


## @brief A code hit inside a constant or a class field names that binding, not `__module__`.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_code_hit_inside_a_binding_names_the_binding(tmp_path: Path) -> None:
    """FROM THE 1.3.0-TS-FIX2 TRANSCRIPTS: `retryPolicyConfiguration` in mattermost's
    `NetworkManagerSingleton.DEFAULT_CONFIG` came back as `network_manager.__module__`, a whole
    file, so an agent had nothing to hand to `dossier` but the file.

    @brief E7 -> Events; retryLimit -> DEFAULT_CONFIG (an UNTYPED field, which was not indexed).
    @return None.
    @version 1
    """
    tools = _extent_tools(tmp_path)
    hit = tools.search("E7", corpus="code")["results"][0]
    assert (hit["name"], hit["kind"]) == ("Events", "variable"), hit
    hit = tools.search("retryLimit", corpus="code")["results"][0]
    assert (hit["name"], hit["kind"]) == ("DEFAULT_CONFIG", "variable"), hit
    assert tools.dossier("DEFAULT_CONFIG").get("subject_kind") == "variable"


## @brief A constant's declaration excerpt is its whole statement, as recorded, not 8 lines.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_constant_excerpt_covers_its_recorded_extent(tmp_path: Path) -> None:
    """FROM THE SAME RUN: `WebsocketEvents` came back truncated at eight lines — the cap that
    bounds a GUESSED statement end. A parse-built binding's end is known, so the excerpt reads to
    it under the ordinary body cap.

    @brief Events' excerpt ends with `};` and is not truncated.
    @return None.
    @version 1
    """
    site = _extent_tools(tmp_path).dossier("Events")["sites"][0]["declaration"]
    assert site["lines"][-1] == "};" and site["truncated"] is False, site
    assert len(site["lines"]) == 14, site
