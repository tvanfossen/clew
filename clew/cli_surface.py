# SPDX-License-Identifier: MIT
"""The covered command line, generated from the parsers (PS2, owner Q/A 2026-11-19).

`docs/OVERVIEW.md` "What semver covers" listed the `clew` verbs and their flags as covered, and
nothing checked it. PS2 adds `clew guard` and `clew wiki` (they are wired into pre-commit and CI)
and pins the whole surface the way `docs/wire-keys.json` pins the wire keys: this module walks each
covered verb's argparse parser — positionals, option strings, subcommands, recursively — and
`docs/cli-surface.json` is compared with it by a test. A removed or renamed verb or flag fails the
test and is a major bump; an added one is additive — regenerate.

Regenerate: `.venv/bin/python -m clew.cli_surface > docs/cli-surface.json`.

@brief Generate the covered CLI surface.
@version 1
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


## @brief One parser's surface: its positionals, its option strings, and its subcommands.
## @param parser The parser.
## @return {"positionals": [...], "options": [...], "subcommands": {name: surface}}.
## @version 1
## @req REQ-DDB-CLI-001
def parser_surface(parser: argparse.ArgumentParser) -> dict[str, Any]:
    """`-h/--help` is argparse's own, not clew's, so it is left out.

    @brief Walk a parser.
    @return Surface.
    """
    positionals, options, subs = [], [], {}
    for action in parser._actions:  # noqa: SLF001 — argparse exposes no public walk
        if isinstance(action, argparse._HelpAction):  # noqa: SLF001
            continue
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            for name, sub in sorted(action.choices.items()):
                subs[name] = parser_surface(sub)
        elif action.option_strings:
            options.extend(action.option_strings)
        else:
            positionals.append(action.dest)
    out: dict[str, Any] = {"positionals": positionals, "options": sorted(options)}
    if subs:
        out["subcommands"] = subs
    return out


## @brief The covered surface of every `clew` verb.
## @return {verb: surface}.
## @version 1
## @req REQ-DDB-CLI-001
def cli_surface() -> dict[str, Any]:
    """@brief Every covered verb. @return Surface."""
    from .cli import _build_argparser
    from .export_command import _parser as export_parser
    from .guard.main import build_parser as guard_parser
    from .init_command import build_parser as init_parser
    from .propose.command import build_parser as propose_parser
    from .query_command import _parser as query_parser
    from .wiki.command import _parser as wiki_parser

    verbs = {
        "clew": _build_argparser,
        "clew init": init_parser,
        "clew propose": propose_parser,
        "clew export": export_parser,
        "clew query": query_parser,
        "clew guard": guard_parser,
        "clew wiki": wiki_parser,
    }
    return {verb: parser_surface(build()) for verb, build in verbs.items()}


if __name__ == "__main__":
    json.dump(cli_surface(), sys.stdout, indent=1)
    sys.stdout.write("\n")
