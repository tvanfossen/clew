# SPDX-License-Identifier: MIT
"""Audit the SERVED surface for names a client cannot call.

Why a script and not only a test: the blast radius has to be readable BEFORE the gate is
written. `tests/test_descriptions.py::test_served_text_names_only_registered_tools` already
exists, is green, and misses every instance this finds — it scans `INSTRUCTIONS` plus the tool
descriptions and requires a BACKTICKED open paren, while the live defects are bare names inside
runtime payload constants. A guard that fires on some of the real cases is worse than no guard,
so this script measures first and the gate is widened against what it reports.

WHAT COUNTS AS SERVED. Three surfaces, and the existing guard covers only the first:
  1. `INSTRUCTIONS` and the rendered tool descriptions — read once, at connect.
  2. The description JSON files and their shared templates — the same text, before rendering.
  3. RUNTIME PAYLOAD STRINGS — emptiness notes, freshness/staleness prose, truncation hints.
     These fire on exactly the events a struggling reader hits, which is when a wrong
     instruction costs the most.

Usage:
    .venv/bin/python scripts/served_text_audit.py scan
    .venv/bin/python scripts/served_text_audit.py scan --json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

## Modules whose string literals reach a client. Not the whole package: `state.py` and
## `_sdk.py` are plumbing. Listed rather than globbed so adding a served surface is a
## deliberate act with a name attached.
RUNTIME_SERVED_MODULES = (
    "clew/mcp_server/emptiness.py",
    "clew/mcp_server/freshness.py",
    "clew/mcp_server/tools_query.py",
    "clew/mcp_server/server.py",
)

DESCRIPTIONS_DIR = REPO / "clew/mcp_server/descriptions"

## A call the reader is being told to make. NO backtick requirement — the shipped guard has
## one, and it is why `resolve_symbol()` inside an f-string went unseen.
##
## `(?!s\))` excludes the ENGLISH PLURAL IDIOM: "3 indexed source file(s) have changed" is
## not an instruction to call `file`. Without it this fired four times on `file(s)` alone,
## and a report whose majority is noise is one a reader learns to skip.
CALL = re.compile(r"\b([a-z_][a-z0-9_]*)\((?!s\))")

## RULE B's list, and it is a list because a BARE name has no shape for rule A to match.
## The first version of this file made the denylist the PRIMARY rule and it failed twice in
## one run: it missed `lock_roster()` because the name was not on it, and it fired on `cull`
## which is a live `index` ACTION. Both failures are cured by deriving the allowed set from
## the code (see `_allowed`) and demoting this to a backstop for bare mentions only.
RETIRED_HISTORICAL = frozenset(
    {
        "build_or_refresh",
        "list_targets",
        "set_target",
        "list_files",
        "search_prose",
        "search_symbols",
        "chain_trace",
        "req_trace",
        "thread_of",
        "resolve_symbol",
        "lookup_class",
        "runs_under_lock",
        "lock_roster",
        "thread_roster",
    }
)

## Names that are ALSO payload fields, so a served string may legitimately mention them as
## data rather than as a call. Kept out of `RETIRED_HISTORICAL` entirely rather than
## reported-and-excused: 16 FIELD rows of noise is how a reader learns to skip the report.
PAYLOAD_FIELDS = frozenset({"callers", "callees", "graph_stats", "source", "candidates"})

## THE ONE LEGITIMATE BARE MENTION. `INSTRUCTIONS` says "There is no set_target tool" — a
## NEGATIVE statement, and the only way to answer a reader who remembers the old surface.
##
## Recorded as (name, the exact phrase that makes it legitimate) rather than as a bare name,
## so the exemption cannot silently widen: if that sentence is ever reworded, the phrase stops
## matching and the mention is reported again. `_stale_negations` closes the other half —
## an entry whose phrase is gone anywhere in the served text is itself an error, so this
## cannot rot into a permanent hole.
NEGATED = (("set_target", "There is no set_target tool"),)


## @brief Every string literal in a module that is not a docstring.
## @param path Repo-relative path to a Python source file.
## @return List of (line, text) pairs.
## @version 1
def _string_literals(path: Path) -> list[tuple[int, str]]:
    """Collect non-docstring string literals via AST, so comments never reach the scan.

    f-strings are `JoinedStr` and their literal halves are `Constant` children, which is how
    `f"... or resolve_symbol() first"` gets seen at all.

    @brief String literals of a module.
    @param path Source file.
    @return (line, text) pairs.
    @version 1
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                out.append((node.lineno, node.value))
    return out


## @brief Every string in the shipped description JSON, keyed by file and pointer.
## @return List of (where, text) pairs.
## @version 1
def _description_strings() -> list[tuple[str, str]]:
    """Walk the description JSON and its templates, returning every leaf string.

    @brief Description strings.
    @return (where, text) pairs.
    @version 1
    """
    out: list[tuple[str, str]] = []

    def walk(node: object, where: str) -> None:
        if isinstance(node, str):
            out.append((where, node))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{where}[{i}]")

    ## ONLY THE KEYS THAT REACH A CLIENT. `_entry` renders `description`, `_from_template`
    ## renders a template's `text`, and NOTHING renders `why` or `used_by` — those are
    ## authoring rationale. Scanning them made this audit report a `chain_trace` reference
    ## as served when it is a comment, which is the same class of error the audit exists to
    ## catch: a claim about what a reader sees, made without checking what is rendered.
    for path in sorted(DESCRIPTIONS_DIR.rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        rel = str(path.relative_to(REPO))
        for key in ("description", "text"):
            if key in doc:
                walk(doc[key], f"{rel}.{key}")
    return out


## @brief Every name a served string may legitimately put in call position.
## @return (registered tools, full allowed set).
## @version 2
def _allowed() -> tuple[set[str], set[str]]:
    """Derive what is callable from the code, never from a restated list.

    THREE VOCABULARIES, all imported: the registered TOOLS, the `index` ACTIONS, and the
    `search` CORPORA. A served string saying `action='cull'` or `corpus='prose'` is correct
    even though neither is a tool, and the first version of this audit flagged three such
    lines because it only knew about tools.

    Deriving rather than listing is also what makes rule A survive the next rename — which is
    the reasoning the shipped guard states and then undercuts by requiring a backtick.

    @brief Allowed callable names.
    @return (tools, tools|actions|corpora).
    @version 2
    """
    sys.path.insert(0, str(REPO))
    from clew.mcp_server.server import INDEX_ACTIONS, TIER0_TOOLS
    from clew.mcp_server.tools_query import CORPORA, TIER1_TOOLS

    tools = set(TIER0_TOOLS) | set(TIER1_TOOLS)
    return tools, tools | set(INDEX_ACTIONS) | set(CORPORA)


## @brief Every served surface as (where, text) pairs.
## @return List of (where, text).
## @version 1
def served_surfaces() -> list[tuple[str, str]]:
    """Runtime payload literals plus the rendered description keys, in one list.

    @brief The served surface.
    @return (where, text) pairs.
    @version 1
    """
    ## WHITESPACE IS COLLAPSED BEFORE ANY RULE SEES THE TEXT. A triple-quoted constant wraps
    ## "There is no set_target tool" across a line break, so the `NEGATED` phrase did not
    ## match its own source and the exemption reported STALE while the mention it exempts
    ## reported live — one edit looking like two unrelated defects. What a client receives is
    ## the joined text, so matching the joined text is also the more faithful check.
    out: list[tuple[str, str]] = []
    for rel in RUNTIME_SERVED_MODULES:
        for line, text in _string_literals(REPO / rel):
            out.append((f"{rel}:{line}", " ".join(text.split())))
    out.extend((where, " ".join(text.split())) for where, text in _description_strings())
    return out


## @brief `NEGATED` entries whose justifying phrase no longer appears anywhere served.
## @return List of stale (name, phrase) pairs.
## @version 1
def stale_negations() -> list[tuple[str, str]]:
    """THE OTHER HALF OF THE EXEMPTION, and the half that is normally forgotten.

    An allowlist that is only checked in one direction rots into a permanent hole: the
    sentence gets reworded, the entry stops matching anything, and the name it exempts is
    now exempt everywhere for no reason. So an entry whose phrase is absent from the whole
    served surface is itself an error.

    @brief Stale negation entries.
    @return Stale (name, phrase) pairs.
    @version 1
    """
    texts = [text for _where, text in served_surfaces()]
    return [(name, phrase) for name, phrase in NEGATED if not any(phrase in t for t in texts)]


## @brief Every served string naming something a client cannot call.
## @return List of finding dicts with where/kind/name/text.
## @version 1
def collect() -> list[dict]:
    """Apply rule A (derived call shape) and rule B (retired bare names) to every surface.

    @brief Collect findings.
    @return Findings.
    @version 1
    """
    registered, allowed = _allowed()
    if not registered:
        raise RuntimeError("no tools registered — the scan would pass vacuously")

    findings: list[dict] = []

    def inspect(where: str, text: str) -> None:
        ## RULE A — shape, fully derived. Anything in call position that is not a tool, an
        ## action or a corpus is an instruction the reader cannot follow.
        for name in CALL.findall(text):
            if name not in allowed:
                findings.append({"where": where, "kind": "CALL", "name": name, "text": text})
        ## RULE B — bare mentions of names that were once callable. A backstop, not the
        ## primary rule; `PAYLOAD_FIELDS` never reaches here by construction.
        for name in RETIRED_HISTORICAL:
            if name in allowed or name in PAYLOAD_FIELDS:
                continue
            if any(n == name and phrase in text for n, phrase in NEGATED):
                continue
            if re.search(rf"\b{re.escape(name)}\b", text) and not re.search(
                rf"\b{re.escape(name)}\(", text
            ):
                findings.append({"where": where, "kind": "BARE", "name": name, "text": text})

    for where, text in served_surfaces():
        inspect(where, text)
    return findings


## @brief Report every served string naming something a client cannot call.
## @param as_json Emit machine-readable output instead of a table.
## @return Process exit code: 1 if anything was found.
## @version 2
def cmd_scan(as_json: bool) -> int:
    """Print the findings and the stale-negation check, and exit non-zero on either.

    @brief Scan the served surface.
    @param as_json Machine-readable output.
    @return Exit code.
    @version 2
    """
    registered, _allowed_names = _allowed()
    findings = collect()
    stale = stale_negations()

    if as_json:
        print(json.dumps({"findings": findings, "stale_negations": stale}, indent=2))
    else:
        by_kind: dict[str, int] = {}
        for f in findings:
            by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
        for f in findings:
            snippet = f["text"].replace("\n", " ")
            print(f"{f['kind']:<5} {f['name']:<18} {f['where']}")
            print(f"      {snippet}")
        for name, phrase in stale:
            print(f"STALE {name:<18} NEGATED entry's phrase is gone: {phrase!r}")
        print()
        print(f"registered tools: {sorted(registered)}")
        print(f"findings: {len(findings)}  by kind: {by_kind}  stale negations: {len(stale)}")
        print("CALL = tells a client to invoke a tool that 404s.")
        print("BARE = names a retired tool in prose; a reader may still try it.")
        print("Rule A (CALL) is derived from tools+actions+corpora. Rule B (BARE) is a named set.")
    return 1 if (findings or stale) else 0


## @brief CLI entry point.
## @return Exit code.
## @version 1
def main() -> int:
    """Dispatch subcommands.

    @brief Entry point.
    @return Exit code.
    @version 1
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    scan = sub.add_parser("scan", help="report served strings naming unreachable tools")
    scan.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    if args.cmd == "scan":
        return cmd_scan(args.json)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
