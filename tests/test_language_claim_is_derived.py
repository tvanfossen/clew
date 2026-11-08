# SPDX-License-Identifier: MIT
"""THE LANGUAGE LIST WAS PROSE IN FIVE PLACES AND A CRAWLER FOUND IT BEFORE THE GATE DID.

`clew` grew JavaScript, TypeScript, shell and CMake front ends. Five public strings named the
languages it indexes; **two were updated and three were not**:

    .claude-plugin/plugin.json   "C, C++, Rust, Python, JavaScript or TypeScript"   current
    README.md                    "C, C++, Python, Rust, JavaScript or TypeScript"   current
    .claude-plugin/marketplace.json  "C, C++, Rust or Python"                       STALE
    pyproject.toml                   "C, C++, Rust and Python"                      STALE
    clew/mcp_server/server.py        "C, C++, Rust or Python"                       STALE

The MCP `INSTRUCTIONS` string is the worst of the three: it is the first thing every agent
reads, and it told them clew could not index four of the languages it indexes.

**AND "SIX" WOULD HAVE BEEN WRONG TOO.** `docs/languages/` holds six files, so six is the number
a reader counts — but `SCRIPT_INTEGRATION.md` is one file covering TWO languages clew harvests
symbols from, shell and CMake, with rows tagged `dg_source = 'parse'`. The honest harvested set
is eight. A hand-maintained list was wrong in both directions at once.

**SO THE LIST IS NOT MAINTAINED ANY MORE, IT IS DERIVED** — from the routing tables that decide
what actually gets read. `INSTRUCTIONS` interpolates it, and the four static files cannot
interpolate, so this test checks them instead. Adding a grammar without updating them fails the
gate, which is the only version of this that cannot rot.

**TWO SETS, NOT ONE, because clew does two different things.** A language it HARVESTS contributes
symbols to the namespace. A type it REGISTERS is in the file set, findable by name, and
contributes nothing — YAML and JSON by design, and since C5 `.pl`/`.pm`/`.mk`/`Makefile` because
no grammar reads them. Collapsing those into one count is how "clew supports Perl" becomes a
claim it cannot meet.

@brief What clew indexes is derived from the routers, and the public strings are checked.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clew.languages import HARVESTED, REGISTERED_ONLY, harvested_phrase

REPO = Path(__file__).resolve().parent.parent


## @brief The harvested set matches the routers it is derived from.
## @version 1
def test_the_harvested_set_is_derived_from_the_routers() -> None:
    """ASSERTED AGAINST THE TABLES, not against a literal list, because a literal here would be
    the sixth place to go stale. If a router gains an extension family this test's expectation
    moves with it; if the derivation stops reading a router, the set shrinks and the public
    strings stop matching.
    """
    assert "C" in HARVESTED and "C++" in HARVESTED, HARVESTED
    assert "Rust" in HARVESTED and "Python" in HARVESTED, HARVESTED
    assert "JavaScript" in HARVESTED and "TypeScript" in HARVESTED, HARVESTED
    assert "shell" in HARVESTED and "CMake" in HARVESTED, (
        f"shell and CMake are harvested for SYMBOLS (synth.SCRIPT_EXTS, dg_source='parse') and "
        f"must not be omitted the way docs/languages/ groups them: {HARVESTED}"
    )


## @brief Registered-only types are kept separate from harvested ones.
## @version 1
def test_registered_only_is_a_separate_claim() -> None:
    """COLLAPSING THE TWO IS HOW A FALSE CLAIM GETS MADE. A `.pl` file is in the file set and
    findable by name; nothing parses it. Listing Perl beside C would promise symbols, call edges
    and bodies that do not exist for it.
    """
    assert "YAML" in REGISTERED_ONLY and "JSON" in REGISTERED_ONLY, REGISTERED_ONLY
    assert "Perl" in REGISTERED_ONLY, REGISTERED_ONLY
    assert "Make" in REGISTERED_ONLY, REGISTERED_ONLY
    assert not (set(HARVESTED) & set(REGISTERED_ONLY)), (
        "a language is harvested or registered-only, never both"
    )


## @brief Every public description names the derived harvested set.
## @version 1
@pytest.mark.parametrize(
    "where",
    [
        pytest.param("pyproject.toml", id="pyproject"),
        pytest.param(".claude-plugin/plugin.json", id="plugin"),
        pytest.param(".claude-plugin/marketplace.json", id="marketplace"),
        pytest.param("README.md", id="readme"),
    ],
)
def test_the_public_strings_name_every_harvested_language(where: str) -> None:
    """THE MECHANISM, AND THE ONLY PART THAT STOPS THIS ROTTING. These four files cannot
    interpolate a derived value, so they are CHECKED against one. A front end added without
    touching them fails here rather than being found by a registry crawler.

    Asserted per language rather than on a phrase, because the four files word it differently —
    "C, C++, Rust, Python, JavaScript or TypeScript" against "C, C++, Python, Rust, ..." — and
    pinning a phrase would force four identical sentences where four accurate ones will do.
    """
    text = (REPO / where).read_text("utf-8")
    missing = [lang for lang in HARVESTED if lang not in text]

    assert not missing, (
        f"{where} does not name {missing}, which clew harvests symbols from. Public metadata is "
        f"what registries and crawlers ingest; this is the check that keeps it true."
    )


## @brief The served MCP instructions carry the derived phrase, not a literal.
## @version 1
def test_the_served_instructions_are_interpolated() -> None:
    """`INSTRUCTIONS` is the first thing every agent reads, and it claimed four languages when
    clew indexed eight. It now interpolates `harvested_phrase()`, so there is no literal left in
    it to fall behind.

    The 2,048-character cap is checked separately by
    `test_no_served_text_is_ever_truncated`; this asserts only that the phrase arrives.
    """
    from clew.mcp_server.server import INSTRUCTIONS

    assert harvested_phrase() in INSTRUCTIONS, (
        f"the served text does not carry the derived language phrase: {harvested_phrase()!r}"
    )
    for lang in HARVESTED:
        assert lang in INSTRUCTIONS, f"the served text omits {lang!r}"


## @brief The plugin and marketplace descriptions agree with each other.
## @version 1
def test_the_two_plugin_manifests_do_not_disagree() -> None:
    """They were written from one sentence and drifted apart — one updated, one not. Both are
    ingested by the same marketplace tooling, so a reader can be shown either.
    """
    plugin = json.loads((REPO / ".claude-plugin/plugin.json").read_text("utf-8"))
    market = json.loads((REPO / ".claude-plugin/marketplace.json").read_text("utf-8"))
    entry = next(p for p in market["plugins"] if p.get("name") == plugin["name"])

    for lang in HARVESTED:
        assert (lang in plugin["description"]) == (lang in entry["description"]), (
            f"the two manifests disagree about {lang!r}"
        )


## The generated clause opens with this, so everything before it in a description is hand-written.
_CLAUSE_OPENS = "Harvests symbols from"


## @brief The hand-written part of a manifest description, without the generated clause.
## @param desc A full description.
## @return The text before the generated clause.
## @version 1
def _hand_written(desc: str) -> str:
    """@brief Strip the generated clause.
    @return Hand-written remainder.
    @version 1
    """
    return desc.split(_CLAUSE_OPENS, 1)[0]


## @brief Every manifest description string, labelled.
## @return (label, description) pairs, including a missing top-level marketplace description.
## @version 1
def _manifest_descriptions() -> list[tuple[str, str | None]]:
    """@brief Collect the manifest descriptions.
    @return Labelled descriptions.
    @version 1
    """
    plugin = json.loads((REPO / ".claude-plugin/plugin.json").read_text("utf-8"))
    market = json.loads((REPO / ".claude-plugin/marketplace.json").read_text("utf-8"))
    return [
        ("plugin.json", plugin.get("description")),
        ("marketplace.json (top level)", market.get("description")),
        ("marketplace.json plugins[0]", market["plugins"][0].get("description")),
    ]


## @brief A manifest names languages only inside its generated clause.
## @version 1
def test_manifests_name_languages_only_inside_the_generated_clause() -> None:
    """LANGUAGES STATED TWICE IN ONE STRING, AND ONE COPY ALREADY STALE. Both manifests opened with
    a hand-written lead-in — "Index a C, C++, Rust or Python repository" — and ended with the
    generated clause. The marketplace copy omitted JavaScript and TypeScript while its own clause,
    one sentence later, named them. The owner's ruling on the GitHub description was that
    languages are stated in ONE place; this is that ruling made mechanical.

    @brief No language name outside the generated clause.
    @version 1
    """
    import re

    offenders = []
    for label, desc in _manifest_descriptions():
        if not desc:
            continue
        rest = _hand_written(desc)
        for lang in (*HARVESTED, *REGISTERED_ONLY):
            ## Bounded so `C` does not match inside `C++` or `CLEW_HOOK_DISABLE`.
            if re.search(rf"(?<![A-Za-z0-9+]){re.escape(lang)}(?![A-Za-z0-9+])", rest):
                offenders.append(f"{label}: '{lang}'")
    assert not offenders, (
        f"a language is named outside the generated clause, so it is maintained by hand and will "
        f"go stale: {offenders}"
    )


## @brief The marketplace catalog carries a top-level description.
## @version 1
def test_the_marketplace_has_a_top_level_description() -> None:
    """@brief The catalog describes itself, not only its plugin.
    @version 1
    """
    desc = dict(_manifest_descriptions())["marketplace.json (top level)"]
    assert desc and len(desc.split()) >= 5, f"no usable top-level description: {desc!r}"
