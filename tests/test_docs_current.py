# SPDX-License-Identifier: MIT
"""The documentation says what 2.0.0 does (round 3, P6; owner: "all documentation up to date
before the cut").

The facts several documents state — which tools the server serves, which languages the index
reads — are GENERATED between markers by `scripts/sync_metadata.py`, from the same sources the
code reads, and `--check` (a pre-commit hook) fails on drift. A sentence a human types goes
stale: the docs pass found "the four tools" after one was retired, "21 languages" hard-coded,
and a refresh cadence ("every 15 s") two releases out of date.

@brief Tests that the docs state current facts.
@version 1
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_the_tool_clause_names_exactly_what_the_server_serves() -> None:
    """@brief Generated from the description files the server loads: tools, then prompts."""
    sys.path.insert(0, str(REPO / "scripts"))
    from sync_metadata import tools_clause

    from clew.mcp_server.server import PROMPTS, TIER0_TOOLS
    from clew.mcp_server.tools_query import TIER1_TOOLS

    clause = tools_clause()
    for name in (*TIER1_TOOLS, *TIER0_TOOLS, *PROMPTS):
        assert f"`{name}`" in clause, name
    assert f"{len(TIER1_TOOLS) + len(TIER0_TOOLS)} tools" in clause.replace("three", "3")


def test_the_generated_facts_are_in_sync_across_the_docs() -> None:
    """@brief README and SKILLS carry the tool clause, SKILLS the language clause; all current."""
    for name, marks in (
        ("README.md", ("clew:tools",)),
        ("SKILLS.md", ("clew:tools", "clew:langs")),
    ):
        text = (REPO / name).read_text()
        for mark in marks:
            assert f"<!-- {mark} -->" in text, (name, mark)
    done = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "sync_metadata.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_no_document_states_a_retired_fact() -> None:
    """@brief Phrases 2.0.0 made false appear in no shipped document."""
    docs = [*REPO.glob("*.md"), *(REPO / "docs").glob("*.md")]
    stale = (
        "every 15 s",
        "four tools",
        "21 languages",
        "index(action='stats')",
        "index(action='cull')",
    )
    found = [(d.name, s) for d in docs for s in stale if s in d.read_text()]
    found = [(n, s) for n, s in found if not (n == "SECURITY.md" and s == "index(action='cull')")]
    assert found == [], found


def test_the_declaration_example_names_every_section() -> None:
    """THE EXAMPLE A READER COPIES is held to the code's own section list: a section missing from
    it is a capability nobody learns exists (the docs pass found six missing).

    @brief OVERVIEW's `.clew.yaml` example covers every section.
    """
    import re

    from clew.declaration import KNOWN_SECTIONS, NON_DECLARATION_SECTIONS

    text = (REPO / "docs" / "OVERVIEW.md").read_text()
    block = text[text.index("# a --declare document, or <repo>/.clew.yaml") :].split("```", 1)[0]
    keys = set(re.findall(r"^([a-z_]+):", block, re.M))
    assert set(KNOWN_SECTIONS) | set(NON_DECLARATION_SECTIONS) <= keys, sorted(
        (set(KNOWN_SECTIONS) | set(NON_DECLARATION_SECTIONS)) - keys
    )


def test_the_wiki_guide_documents_every_key() -> None:
    """THE REFERENCE A READER CONFIGURES FROM covers every key the section accepts — the round-3
    keys were missing from it entirely.

    @brief WIKI.md names every `wiki:` and `tests:` key.
    """
    from clew.declaration import TESTS_KEYS
    from clew.wiki.config import _TOP

    text = (REPO / "docs" / "WIKI.md").read_text()
    block = text[text.index("```yaml\nwiki:") :].split("```", 2)[1]
    missing = [k for k in _TOP if not re.search(rf"^\s+{k}:", block, re.M)]
    assert missing == [], missing
    ## 2.0.0 (R5-CFG F20): the evidence keys are the top-level `tests:` section's, documented in
    ## their own block.
    tests = text[text.index("```yaml\ntests:") :].split("```", 2)[1]
    missing = [k for k in TESTS_KEYS if not re.search(rf"^\s+{k}:", tests, re.M)]
    assert missing == [], missing


def test_the_human_guides_are_visual() -> None:
    """OWNER 2026-11-15: "human documentation should be FAR more visual". Each human guide opens
    its subject with a diagram GitHub renders (Mermaid).

    @brief Human guides carry a diagram.
    """
    for name in ("README.md", "docs/OVERVIEW.md", "docs/WIKI.md", "docs/GUARD.md"):
        assert "```mermaid" in (REPO / name).read_text(), name


def test_clew_documents_itself_with_its_own_wiki() -> None:
    """DOGFOOD: clew's own `.clew.yaml` builds its wiki — every shipped doc has a kind, the agent
    docs are kept apart, and the MCP tool handlers are declared as product flows.

    @brief clew's own wiki section.
    """
    from clew.wiki.adr import doc_kind
    from clew.wiki.config import load_wiki_config

    config, problems = load_wiki_config(REPO)
    assert problems == []
    docs = [*REPO.glob("*.md"), *(REPO / "docs").glob("*.md")]
    kinds = {
        d.relative_to(REPO).as_posix(): doc_kind(d.relative_to(REPO).as_posix(), config.doc_kinds)
        for d in docs
    }
    assert all(kinds.values()), {k: v for k, v in kinds.items() if not v}
    assert kinds["AGENTS.md"] == "agents" and kinds["SKILLS.md"] == "agents"
    assert {(f.entry, f.file) for f in config.flows} >= {
        ("dossier", "clew/mcp_server/tools_query.py"),
        ("search", "clew/mcp_server/tools_query.py"),
        ("index", "clew/mcp_server/server.py"),
    }
