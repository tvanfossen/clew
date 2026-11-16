# SPDX-License-Identifier: MIT
"""The 2.0.0 MCP surface (round 3, P4c-2b; owner 2026-11-16).

Owner rulings: retire `propose_declaration` from the tool list (it becomes an MCP PROMPT and stays
the `clew propose` CLI), trim `index` to refresh / status / targets (`stats` -> `clew query
stats`, `cull` -> `clew cull`), serve the wiki through MCP RESOURCES rather than a new tool —
and ship it as 2.0.0, because README declares MCP tool names semver-covered.

Measured before the change (`.claude/tmp/served_bytes.py`, build_server on an empty registry):
instructions 1,342 + tools 9,384 = 10,726 characters served every turn; `propose_declaration`
693 of them, `index`'s stats/cull text about 300.

@brief Tests for the 2.0.0 tool, prompt and resource surface.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clew.mcp_server import state as st
from clew.mcp_server.server import build_server

## The served-text baseline above, less the measured saving it was cut for.
_SERVED_CEILING = 10_726 - 900


async def _served(mcp: object) -> int:
    tools = await mcp.list_tools()  # type: ignore[attr-defined]
    return len(mcp.instructions or "") + sum(  # type: ignore[attr-defined]
        len(json.dumps(t.model_dump(exclude_none=True))) for t in tools
    )


@pytest.mark.anyio
async def test_the_tools_are_dossier_search_and_index(tmp_path: Path) -> None:
    """@brief Three tools; the proposer is a prompt; the wiki is a resource template."""
    mcp, _state = build_server(st.TargetRegistry(tmp_path / "state"))
    assert {t.name for t in await mcp.list_tools()} == {"index", "dossier", "search"}
    assert "propose_declaration" in {p.name for p in await mcp.list_prompts()}
    templates = {t.uri_template for t in await mcp.list_resource_templates()}
    assert {"clew://wiki/{slug}/llms.txt", "clew://wiki/{slug}/flow/{name}"} <= templates
    assert await _served(mcp) <= _SERVED_CEILING


@pytest.mark.anyio
async def test_index_refuses_stats_and_cull_and_names_their_cli(tmp_path: Path) -> None:
    """A RETIRED ACTION IS REFUSED BY NAME with the route that replaced it — never a silent
    fall-through, never a bare "unknown action".

    @brief Retired index actions.
    """
    mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    for action, route in (("stats", "clew query stats"), ("cull", "clew cull")):
        with pytest.raises(ValueError) as exc:
            await state.index(None, action=action)
        assert route in str(exc.value), action
    index = next(t for t in await mcp.list_tools() if t.name == "index")
    assert "max_age_days" not in index.input_schema["properties"]
    assert "stats" not in json.dumps(index.model_dump()) and "cull" not in json.dumps(
        index.model_dump()
    )


def _indexed(tmp_path: Path) -> tuple[Path, st.Target]:
    from clew.cli import _build_argparser, _run_pipeline

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.py").write_text('def alpha():\n    """Alpha."""\n    return 1\n')
    target = st.TargetRegistry(tmp_path / "state").register(repo)
    _run_pipeline(
        _build_argparser().parse_args(["--output", target.db_path, "--repo-root", str(repo)])
    )
    return repo, target


def test_stats_and_cull_are_cli_verbs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """@brief `clew query stats` grades an index; `clew cull` sweeps the registry."""
    from clew.cull_command import cull_main
    from clew.query_command import query_main

    _repo, target = _indexed(tmp_path)
    capsys.readouterr()  # the build's own output, not the verb's
    assert query_main(["stats", "--index", target.db_path]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert "edges" in json.dumps(stats) or "edge" in json.dumps(stats)
    monkeypatch.setenv("CLEW_STATE_HOME", str(tmp_path / "state"))
    assert cull_main(["--max-age-days", "100000"]) == 0
    swept = json.loads(capsys.readouterr().out)
    assert swept["remaining"] == 1 and swept["culled"] == []


@pytest.mark.anyio
async def test_the_proposer_is_a_prompt(tmp_path: Path) -> None:
    """@brief The prompt returns the draft declaration for a named repository."""
    repo, _target = _indexed(tmp_path)
    mcp, _state = build_server(st.TargetRegistry(tmp_path / "state"))
    result = await mcp.get_prompt("propose_declaration", {"repo": str(repo)})
    text = " ".join(m.content.text for m in result.messages)
    assert "clew.yaml" in text and "#" in text


@pytest.mark.anyio
async def test_the_wiki_is_a_resource(tmp_path: Path) -> None:
    """A BUILT WIKI IS READ, an unbuilt one SAYS so — never an empty resource.

    @brief Wiki resources.
    """
    from clew.mcp_server.wikihub import wiki_site_dir

    _repo, target = _indexed(tmp_path)
    mcp, _state = build_server(st.TargetRegistry(tmp_path / "state"))
    unbuilt = await mcp.read_resource(f"clew://wiki/{target.slug}/llms.txt")
    assert "not built" in "".join(c.content for c in unbuilt)
    site = wiki_site_dir(target)
    (site / "exports" / "flows").mkdir(parents=True)
    (site / "llms-full.txt").write_text("# Demo\nREQ-1 [PASS]\n")
    (site / "exports" / "flows" / "flow-main.mmd").write_text("sequenceDiagram\n")
    built = await mcp.read_resource(f"clew://wiki/{target.slug}/llms.txt")
    assert "REQ-1 [PASS]" in "".join(c.content for c in built)
    flow = await mcp.read_resource(f"clew://wiki/{target.slug}/flow/flow-main")
    assert "sequenceDiagram" in "".join(c.content for c in flow)
    ## A path that climbs out is refused — by the SDK's own parameter check before the handler
    ## runs, or by the handler's confinement; either way nothing outside the wiki is served.
    try:
        escape = await mcp.read_resource(f"clew://wiki/{target.slug}/flow/..%2F..%2Fstate")
    except Exception:  # noqa: BLE001, S110 — the SDK refuses it (security check, then not-found)
        pass
    else:
        assert "sequenceDiagram" not in "".join(c.content for c in escape)
