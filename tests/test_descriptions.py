# SPDX-License-Identifier: MIT
"""Tests for the JSON tool-description loader.

A tool description is the only thing a model reads before choosing a tool, so a
description that silently comes back empty, stale or half-rendered is a live defect
that no other test can see — every existing assertion compares `TIER1_TOOLS` to
itself or to what it happens to contain. These tests cover the two things that
matter: the SHIPPED files are complete and correspond exactly to the registered
tools, and every malformed input FAILS rather than degrading.

The fail-loud cases are modelled on `dispatch._reject_unknown`, whose absence let a
singular/plural slip parse into an empty manifest and build green.

@brief Tests for clew.mcp_server.descriptions.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clew.mcp_server import descriptions as d


## @brief Write a JSON document into a descriptions-shaped directory.
## @param root Directory acting as `descriptions/`.
## @param name File stem.
## @param doc Document contents.
## @return None.
## @version 1
def _put(root: Path, name: str, doc: dict) -> None:
    """@brief Write one description file into a fixture directory.
    @return None.
    @version 1
    """
    (root / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")


## @brief Point the loader at a fixture directory instead of the shipped one.
## @param monkeypatch pytest monkeypatch fixture.
## @param root Directory to use as `descriptions/`.
## @return None.
## @version 1
def _redirect(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Both module constants are repointed, because a template lives under the
    descriptions directory and a test that moved only one would exercise a state
    the real layout never has.

    @brief Repoint the loader's directories at a fixture.
    @return None.
    @version 1
    """
    monkeypatch.setattr(d, "DESCRIPTIONS_DIR", root)
    monkeypatch.setattr(d, "TEMPLATES_DIR", root / "_templates")


# ─── the shipped files ───────────────────────────────────────────────────────


## @brief Every registered tier-1 tool has a description file, and vice versa.
## @return None.
## @version 1
def test_shipped_descriptions_correspond_exactly_to_the_registered_tools() -> None:
    """Correspondence in BOTH directions. A tool with no file cannot be described to
    a model; a file with no tool is prose nobody reads, which then drifts and later
    gets copied back in as though it were current.

    ACROSS BOTH TIERS since 2026-08-10, and the union is what makes this test survive the
    change rather than be weakened by it: the five tier-0 descriptions moved out of
    `server.py` string literals into files here, so comparing the directory against the
    tier-1 set alone would now report five "files-without-tools" — or, if the set were
    quietly swapped for the directory itself, would compare the directory to itself and
    assert nothing at all."""
    from clew.mcp_server.server import TIER0_TOOLS
    from clew.mcp_server.tools_query import TIER1_TOOLS

    registered = set(TIER1_TOOLS) | set(TIER0_TOOLS)
    assert not set(TIER1_TOOLS) & set(TIER0_TOOLS), "a tool belongs to exactly one tier"
    on_disk = {p.stem for p in d.DESCRIPTIONS_DIR.glob("*.json") if not p.name.startswith("_")}
    assert on_disk == registered, (
        "description files and registered tools disagree: "
        f"files-without-tools={sorted(on_disk - registered)}, "
        f"tools-without-files={sorted(registered - on_disk)}"
    )


## @brief No shipped description is empty or left with an unfilled placeholder.
## @return None.
## @version 1
def test_shipped_descriptions_are_rendered_and_substantial() -> None:
    """An unfilled `{placeholder}` reaching a model's tool list is the specific
    failure the template mechanism can produce, and it looks like working prose
    until you read it closely.

    BOTH TIERS, because `load_descriptions()` defaults to tier 1 and a bare call would
    silently stop covering the five tier-0 files the moment they arrived — a coverage hole
    that looks exactly like a passing test. It caught real prose on the way in: the moved
    `build_or_refresh` text wrote `options=` with braces and a literal tag-to-role mapping,
    which this assertion reads as an unrendered placeholder, so the wording was changed
    rather than the invariant."""
    loaded = {**d.load_descriptions(tier=1), **d.load_descriptions(tier=0)}
    for name, text in loaded.items():
        assert len(text) > 40, f"{name}: description is suspiciously short"
        assert "{" not in text and "}" not in text, f"{name}: unrendered placeholder"
        assert not text.startswith(" ") and not text.endswith(" "), f"{name}: stray edge space"
        assert "  " not in text, f"{name}: double space — a description line ended with one"


## @brief Every shipped snippet is included by at least one shipped tool.
## @return None.
## @version 2
def test_no_shipped_snippet_is_orphaned() -> None:
    """WHAT THIS REPLACES, and why the replacement is stricter. It used to assert that
    `callers` and `callees` shared one template body — a real invariant for two tools that
    differed only in direction, and dead the moment gh#372 folded both into `dossier`.
    Deleting it outright would have removed the ONLY assertion touching the shipped
    template/snippet mechanism, leaving it covered exclusively by tmp_path fixtures that
    never read a file this package ships.

    The orphan is the failure that actually happens here: `neighbours.json` described a
    payload shape that stopped existing, and an unread snippet drifts and then gets copied
    back in as though it were current. Both directions are covered — `_snippet` already
    refuses an include naming a file that is absent, so this is the other half.

    @brief Every `_templates/*.json` is reachable from a shipped description.
    @return None.
    @version 2
    """
    included: set[str] = set()
    for path in d.DESCRIPTIONS_DIR.glob("*.json"):
        if path.name.startswith("_"):
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        included |= set(doc.get("include") or ())
        if "template" in doc:
            included.add(doc["template"])
    on_disk = {p.stem for p in d.TEMPLATES_DIR.glob("*.json")}
    assert on_disk == included, (
        f"orphaned snippets={sorted(on_disk - included)}, "
        f"missing snippets={sorted(included - on_disk)}"
    )


## @brief Declared priority orders registration; dossier leads.
## @return None.
## @version 2
def test_registration_order_follows_declared_priority() -> None:
    """Order is part of how the tool list reads, and `dossier` leading is deliberate —
    its description opens with CALL THIS FIRST.

    @brief The tier-1 list is ordered by declared priority.
    @return None.
    @version 2
    """
    assert list(d.load_descriptions()) == ["dossier", "search"]


# ─── every malformed input fails loudly ──────────────────────────────────────


## @brief Every row-returning tool states the absent-vs-null rule, from one source.
## @return None.
## @version 1
def test_row_returning_tools_all_carry_the_shared_rows_note() -> None:
    """The rule is load-bearing and easy to get wrong in BOTH directions: a model that
    tests `row.crosses_thread is None` hits a KeyError, and one that reads a missing key
    as a negative answer reports "this edge does not cross threads" for an edge nobody
    measured. MCP has no shared preamble, so the sentence is paid per tool on the wire —
    the point of the `include` is that the WORDING has one source, and this test is what
    stops a new row-returning tool from shipping without it."""
    loaded = d.load_descriptions()
    for name in ("dossier", "search"):
        assert "ABSENT, not null" in loaded[name], f"{name} omits the row-field rule"


## @brief The neighbours template no longer claims a key row's confidence is null.
## @return None.
## @version 1
def test_no_description_claims_an_elided_field_is_null() -> None:
    """A REGRESSION TEST for a real contradiction: the template said `confidence` is
    null on a 'key' row, and that became false when `wire` began eliding fields carrying
    no value. A description that contradicts the payload is worse than a vague one,
    because a model acts on it."""
    for text in d.load_descriptions().values():
        assert "is null" not in text, "a description claims a field is null; it is absent"


## @brief An unknown snippet name is refused.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_missing_snippet_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief A typo'd include must fail rather than silently append nothing."""
    _redirect(monkeypatch, tmp_path)
    _put(tmp_path, "dossier", {"description": ["Body."], "include": ["row"]})
    with pytest.raises(ValueError, match="no such snippet"):
        d.load_descriptions()


## @brief A snippet containing a placeholder is refused.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_snippet_with_a_placeholder_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An include takes no vars, so a placeholder in a snippet would reach a model's
    tool list as a literal brace. Refused with the fix named — use `template`."""
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "_templates").mkdir()
    (tmp_path / "_templates" / "s.json").write_text(
        json.dumps({"text": ["needs {a}"]}), encoding="utf-8"
    )
    _put(tmp_path, "dossier", {"description": ["Body."], "include": ["s"]})
    with pytest.raises(ValueError, match="use 'template' instead"):
        d.load_descriptions()


## @brief An empty descriptions directory raises instead of returning {}.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_empty_directory_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """This is the packaging failure: a wheel built without the data files would
    otherwise start a server advertising nothing, with no explanation."""
    _redirect(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="no tool descriptions"):
        d.load_descriptions()


## @brief An unknown key is refused rather than ignored.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_unknown_key_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`descriptio` for `description` must not parse to a tool with no text. Same
    reasoning as the dispatch manifest's entry-level rejection."""
    _redirect(monkeypatch, tmp_path)
    _put(tmp_path, "dossier", {"tool": "dossier", "descriptio": ["typo"]})
    with pytest.raises(ValueError, match="unknown key"):
        d.load_descriptions()


## @brief A file whose declared tool disagrees with its filename is refused.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_filename_and_declared_tool_must_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise a copied-and-edited file describes one tool under another's name,
    and the correspondence test above would still pass because the FILENAME set is
    right."""
    _redirect(monkeypatch, tmp_path)
    _put(tmp_path, "callers", {"tool": "callees", "description": ["mismatched"]})
    with pytest.raises(ValueError, match="declares tool"):
        d.load_descriptions()


## @brief A template name that does not exist is refused.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_missing_template_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief A typo'd template name must fail, not yield empty text."""
    _redirect(monkeypatch, tmp_path)
    _put(tmp_path, "callers", {"tool": "callers", "template": "neighbour", "vars": {}})
    with pytest.raises(ValueError, match="no such template"):
        d.load_descriptions()


## @brief A template var the text never uses is refused.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_unused_var_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The subtle half of the template contract. A RENAMED placeholder still renders —
    the old var is simply ignored and the new `{brace}` stays literal — so refusing an
    unused var is what turns that into an error instead of prose a model reads."""
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "_templates").mkdir()
    (tmp_path / "_templates" / "t.json").write_text(
        json.dumps({"text": ["hello {lead}"]}), encoding="utf-8"
    )
    _put(tmp_path, "callers", {"template": "t", "vars": {"lead": "x", "stale": "y"}})
    with pytest.raises(ValueError, match="not used by template"):
        d.load_descriptions()


## @brief A template var the text needs but the file omits is refused.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_missing_var_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief An unsupplied placeholder must fail rather than render a brace."""
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "_templates").mkdir()
    (tmp_path / "_templates" / "t.json").write_text(
        json.dumps({"text": ["hello {lead} and {seam}"]}), encoding="utf-8"
    )
    _put(tmp_path, "callers", {"template": "t", "vars": {"lead": "x"}})
    with pytest.raises(ValueError, match="needs var"):
        d.load_descriptions()


## @brief Malformed JSON names the file it is in.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_bad_json_names_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare `JSONDecodeError` gives a line and column but not a filename, and these
    are hand-edited content files — the filename is the first thing you need."""
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "dossier.json").write_text('{"tool": "dossier",}', encoding="utf-8")
    with pytest.raises(ValueError, match="dossier.json is not valid JSON"):
        d.load_descriptions()


## @brief A non-string description value is refused.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_non_string_description_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers the absent case too: `description` missing entirely arrives here as
    None, and must not join to an empty string."""
    _redirect(monkeypatch, tmp_path)
    _put(tmp_path, "dossier", {"tool": "dossier", "description": [1, 2]})
    with pytest.raises(ValueError, match="must be a string or a list"):
        d.load_descriptions()

    _put(tmp_path, "dossier", {"tool": "dossier", "priority": 1})
    with pytest.raises(ValueError, match="must be a string or a list"):
        d.load_descriptions()


## @brief A one-sentence description may be a bare string.
## @param tmp_path Temporary directory.
## @param monkeypatch pytest monkeypatch fixture.
## @return None.
## @version 1
def test_a_bare_string_description_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list form exists for diff readability, not as a ceremony a short
    description has to perform."""
    _redirect(monkeypatch, tmp_path)
    _put(tmp_path, "dossier", {"tool": "dossier", "description": "Just the one line."})
    assert d.load_descriptions() == {"dossier": "Just the one line."}


## @brief Every tool a served string tells a client to call must be a registered tool.
## @return None.
## @version 1
def test_served_text_names_only_registered_tools() -> None:
    """THE HIGHEST-SEVERITY DEFECT AN OUTSIDE CONSUMER COULD HIT, and nothing guarded it.

    `INSTRUCTIONS` is delivered to every client at connect and told a model to call
    `build_or_refresh()`, `list_targets` and `status` — seven references across four paragraphs,
    none of them a registered tool. All three were folded into `index(action=...)` and the served
    text was never updated. The worst instance was the FIRST-RUN path: "if the tool list looks
    short, call build_or_refresh() and re-read it" is exactly what a stranger with no index reads,
    and it names a tool that 404s.

    `tests/test_init.py` already asserts that no digit appears in the guidance block, on the
    reasoning that measured figures belong in `INSTRUCTIONS` instead. That reasoning is sound and
    the guard is good — and it left the file it nominated as the safe home with no guard of its
    own. Zero tests referenced `INSTRUCTIONS` before this one.

    THE RULE IS SHAPE, NOT A BLOCKLIST. A `name(` or `name(action=` occurrence inside backticks is
    a call the reader is being told to make; anything matching that shape must be a registered
    tool. A list of currently-wrong names would need updating at the next rename, which is the
    failure being prevented.

    METHOD NAMES ARE STILL FINE IN CODE. `build_or_refresh` and `list_targets` remain bound
    methods and internal docstrings may name them. This checks only the strings a CLIENT receives.

    @brief Served text names only registered tools.
    @return None.
    @version 1
    """
    import re

    from clew.mcp_server.server import INSTRUCTIONS, TIER0_TOOLS
    from clew.mcp_server.tools_query import TIER1_TOOLS

    registered = set(TIER0_TOOLS) | set(TIER1_TOOLS)
    assert registered, "no tools registered — the check would pass vacuously"

    served = {"INSTRUCTIONS": INSTRUCTIONS}
    served.update({f"description:{name}": text for name, text in TIER0_TOOLS.items()})
    served.update({f"description:{name}": text for name, text in TIER1_TOOLS.items()})

    ## A backticked call: `name(` or `name()`. Bare mentions are prose and are not checked,
    ## because "the index" and "a dossier" are ordinary English in this text.
    call = re.compile(r"`([a-z_][a-z0-9_]*)\(")
    offenders = [
        (where, name)
        for where, text in served.items()
        for name in call.findall(text)
        if name not in registered
    ]
    assert not offenders, (
        f"served text tells a client to call something that is not a registered tool "
        f"{sorted(registered)}: {offenders}"
    )
