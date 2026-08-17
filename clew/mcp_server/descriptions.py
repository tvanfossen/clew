# SPDX-License-Identifier: MIT
"""Loader for the MCP tool descriptions, which live in JSON — not in Python.

A tool description is the ONLY thing a model reads before choosing a tool, so it is
content, not code: it gets reworded far more often than the wrapper it describes, by
whoever is tuning how the tools land. Keeping ~180 lines of prose inline made
`tools_query.py` mostly text, put every wording tweak in a Python diff, and meant a
stray quote or paren could break the server.

One file per tool, in `descriptions/`, so a reword touches exactly one file:

    { "tool": "dossier",
      "tier": 1,
      "priority": 10,
      "description": ["first sentence ...", "second ..."] }

`tier` says WHICH SURFACE the tool belongs to — 1 for the query tools that appear once
an index exists, 0 for the always-available ones (`build_or_refresh`, `status`,
`list_targets`, `cull`, `propose_declaration`). It defaults to 1, so the twenty files
that predate it are unchanged. It is declared here rather than inferred from which
Python module registers the tool, because the tier-0 descriptions lived as inline string
literals in `server.py` until 2026-08-10 — the exact arrangement this module exists to
prevent, and one that had already grown a 1.5 KB blob in a Python diff before anyone
noticed. Descriptions and their metadata belong beside each other in data, separate from
source; that is the isolation of responsibility this file is for.

`description` is a LIST joined with single spaces. A single long JSON string is
unreadable and produces a one-line diff for a one-word change; a list keeps the diff
on the sentence that moved. Trailing spaces are therefore neither needed nor wanted.

`priority` orders registration (lower first, ties broken by name), because the order
a model sees the tool list in is part of how the list reads — `dossier` and
`chain_trace` are meant to come first. Default 50.

DRY: `callers` and `callees` differ only in direction, and their shared text had
already drifted once when it was duplicated. So a file may instead say

    { "tool": "callers", "template": "neighbours", "vars": {...} }

naming a template in `descriptions/_templates/` whose `{placeholder}`s the vars fill.

A file may also `"include": ["rows"]`, appending shared snippets from the same
directory. That exists because some facts belong to EVERY tool returning a given
shape — "a field carrying no value is absent, not null" is true of every row-bearing
response — and MCP has no shared preamble, so the text is paid per tool on the wire
whatever we do. Including it means the wording has ONE source even though the wire
carries N copies; writing it out per file would mean N copies to keep in step, which
is how `callers`/`callees` drifted into a false claim the first time.

Every failure here is LOUD. A description silently falling back to "" would ship a
tool a model cannot choose correctly, which is worse than not starting: an unknown
key, a missing template, a missing var, or an unused var is an error, on the same
reasoning as `dispatch._reject_unknown` — a singular/plural slip that parses to an
empty manifest builds green and answers wrongly.

@brief Load per-tool MCP descriptions from JSON.
@version 2
"""

from __future__ import annotations

import json
from pathlib import Path

DESCRIPTIONS_DIR = Path(__file__).parent / "descriptions"
TEMPLATES_DIR = DESCRIPTIONS_DIR / "_templates"

## Registration rank for a file that declares none. Mid-range so a tool can be pulled
## forward or pushed back without renumbering the others.
DEFAULT_PRIORITY = 50

_ALLOWED_KEYS = frozenset(
    {"tool", "tier", "priority", "description", "template", "vars", "include"}
)

## The tier a file that declares none belongs to. 1 — the query tools — because they are
## the twenty that existed before tiers were declared here, so their files stay untouched
## and an omitted key keeps meaning what it already meant.
DEFAULT_TIER = 1


## @brief Read one JSON document, failing with the file named.
## @param path File to read.
## @return The parsed document.
## @version 1
## @dg_internal
def _read(path: Path) -> dict:
    """`json.JSONDecodeError` alone names a line and column but not a FILE, and these
    are edited by hand.

    @brief Parse a JSON file, naming it on failure.
    @return Parsed document.
    @version 1
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} is not valid JSON: {exc}") from exc


## @brief Join a description's sentence list into one string.
## @param value The `description` (or template `text`) value.
## @param where File name, for the error message.
## @return The joined text.
## @version 1
## @dg_internal
def _joined(value: object, where: str) -> str:
    """A bare string is accepted so a one-sentence description need not be a
    one-element list, but a list is the norm.

    @brief Normalise a description value to a single string.
    @return Joined text.
    @version 1
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return " ".join(value)
    raise ValueError(f"{where}: description must be a string or a list of strings")


## @brief Fill a named template with a file's vars, refusing any mismatch.
## @param name Template name (file stem in `_templates/`).
## @param variables Placeholder values.
## @param where Owning file name, for the error message.
## @return The filled text.
## @version 1
## @dg_internal
def _from_template(name: str, variables: dict, where: str) -> str:
    """A missing var raises `KeyError` from `format`, which is re-raised naming both
    files. An UNUSED var is also an error: it is how a renamed placeholder goes
    unnoticed, leaving the template's own `{brace}` text in a model's tool list.

    @brief Render a shared description template.
    @return Filled text.
    @version 1
    """
    path = TEMPLATES_DIR / f"{name}.json"
    if not path.is_file():
        raise ValueError(f"{where}: no such template '{name}' in {TEMPLATES_DIR.name}/")
    text = _joined(_read(path).get("text"), path.name)
    try:
        filled = text.format(**variables)
    except KeyError as exc:
        raise ValueError(f"{where}: template '{name}' needs var {exc}") from exc
    for var in variables:
        if "{" + var + "}" not in text:
            raise ValueError(f"{where}: var '{var}' is not used by template '{name}'")
    return filled


## @brief One tool's (tier, priority, name, description) from its JSON file.
## @param path The tool's description file.
## @return Tuple of tier, priority, tool name and description text.
## @version 3
## @dg_internal
def _entry(path: Path) -> tuple[int, int, str, str]:
    """@brief Parse one tool description file.
    @return (tier, priority, tool name, description).
    @version 3
    """
    doc = _read(path)
    unknown = set(doc) - _ALLOWED_KEYS
    if unknown:
        raise ValueError(f"{path.name}: unknown key(s) {sorted(unknown)}")
    name = doc.get("tool") or path.stem
    if name != path.stem:
        raise ValueError(f"{path.name}: declares tool '{name}' but is named '{path.stem}'")
    if "template" in doc:
        text = _from_template(doc["template"], doc.get("vars") or {}, path.name)
    else:
        text = _joined(doc.get("description"), path.name)
    for snippet in doc.get("include") or ():
        text = f"{text} {_snippet(snippet, path.name)}"
    return (
        int(doc.get("tier", DEFAULT_TIER)),
        int(doc.get("priority", DEFAULT_PRIORITY)),
        name,
        text,
    )


## @brief One shared snippet's text, by name.
## @param name Snippet name (file stem in `_templates/`).
## @param where Owning file name, for the error message.
## @return The snippet text.
## @version 1
## @dg_internal
def _snippet(name: str, where: str) -> str:
    """A snippet takes no vars — if it needed them it would be a template. Kept
    separate from `_from_template` for exactly that reason: a snippet silently
    accepting and ignoring vars is the drift this whole loader refuses elsewhere.

    @brief Read a shared, var-free description snippet.
    @return Snippet text.
    @version 1
    """
    path = TEMPLATES_DIR / f"{name}.json"
    if not path.is_file():
        raise ValueError(f"{where}: no such snippet '{name}' in {TEMPLATES_DIR.name}/")
    text = _joined(_read(path).get("text"), path.name)
    if "{" in text:
        raise ValueError(f"{where}: snippet '{name}' has a placeholder; use 'template' instead")
    return text


## @brief Every description declared for one tier, in registration order.
## @param tier Which tier to load — 1 for the query tools, 0 for the always-available ones.
## @return Ordered map of tool name to description text.
## @version 2
## @req REQ-DDB-MCP-001
def load_descriptions(tier: int = DEFAULT_TIER) -> dict[str, str]:
    """Reads every `*.json` in `descriptions/` except the `_templates/` subdirectory,
    keeps those declaring the requested TIER, and orders them by declared priority then
    name. An empty result raises rather than returning `{}` — a packaging mistake that
    dropped the data files would otherwise present as a server with no tools and no
    explanation, and a mistyped tier as a server with no tier-0 surface.

    THE TIER IS DECLARED IN THE TOOL'S OWN FILE, not inferred from which Python module
    registers it. The tier-0 tools' descriptions used to be inline string literals in
    `server.py` — the one arrangement this module exists to prevent — and the reason they
    survived there is mechanical rather than principled: this loader returned EVERY file
    it found and `tools_query` assigned that straight to `TIER1_TOOLS`, so a tier-0 file
    dropped in beside the others would have been registered as a query tool.

    Tier-0 REGISTRATION order stays fixed in `build_server`, which names each function
    explicitly, so `priority` is read for tier 1 and carried harmlessly for tier 0.

    @brief Load one tier's tool descriptions from JSON.
    @return Ordered {tool: description}.
    @version 2
    """
    files = sorted(p for p in DESCRIPTIONS_DIR.glob("*.json") if not p.name.startswith("_"))
    if not files:
        raise ValueError(f"no tool descriptions found in {DESCRIPTIONS_DIR}")
    entries = sorted(e for e in (_entry(p) for p in files) if e[0] == tier)
    if not entries:
        raise ValueError(f"no tool descriptions declare tier {tier} in {DESCRIPTIONS_DIR}")
    return {name: text for _, _, name, text in entries}
