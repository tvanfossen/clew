# SPDX-License-Identifier: MIT
"""`clew export` — write an index's TIER-1 STATEMENTS back out as a declaration.

THE LAST HALF OF "YAML IS AN IMPORT/EXPORT FORMAT" (plan item 4.19). `build_meta` is the source of
truth: a caller states options at call time, the build records them, and a later rebuild replays
them (gh#366). `--declare FILE` reads a YAML document IN. Nothing wrote one OUT, so a statement
made through the MCP surface — by an agent with no shell, against a third-party repo it must not
modify — existed only inside one index. A team could not commit what they had discovered.

ONLY WHAT WAS STATED, WHICH IS THE WHOLE DESIGN DECISION HERE. The effective configuration of a
build is tier 1 over tier 2 over the built-in floor, and exporting all of it would be actively
harmful in two distinct ways:

  * It would write a file asserting that the team DECLARED things they never said — a tier-5
    default and a deliberate statement are different facts, and this project's recurring failure is
    exactly a derived value read later as a stated one.
  * It would FREEZE the built-in defaults into that repo. Every later improvement to a default —
    a widened accessor family, a new spawn primitive — would then be shadowed by a committed file
    nobody remembers writing. A declaration should say what a repo knows about ITSELF.

So the export is the recorded tier-1 set and nothing else, and an index carrying no statement
exports an EMPTY document rather than a plausible one. `stated_options` is the same derived summary
the replay uses, so the export cannot disagree with what a rebuild would replay.

ROUND TRIP IS THE POINT AND IT IS TESTED AS ONE: export -> `--declare` that file -> an index whose
recorded statements are identical. Anything the export drops or reshapes shows up there, which is
why the test asserts the second index's `build_meta` rather than the file's text.

@brief Export an index's tier-1 statements as a declaration document.
@version 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ._common import logger
from .query._common import meta_section
from .tiers import (
    OPTIONS_META_PREFIX,
    recorded_document,
    recorded_explicit,
    stated_options,
)

## The command word `main()` dispatches on, kept beside the others it joins.
EXPORT_COMMAND = "export"


## @brief The declaration mapping an index's recorded tier-1 statements reproduce.
## @param db Path to a built index.
## @return {option: value} in the shape `--declare` / `options` accepts; empty when none.
## @version 1
## @req REQ-DDB-CONFIG-001
def stated_declaration(db: Path) -> dict[str, Any]:
    """READ THROUGH THE SAME HELPERS THE REPLAY USES — `stated_options`, `recorded_explicit`,
    `recorded_document` — rather than querying `build_meta` directly. A second reader of the same
    rows is a second notion of what a statement IS, and the two would eventually disagree about a
    withdrawal: `{}` removes the record, and code that looked for the row rather than asking these
    helpers would export a stale value the replay has already dropped.

    A LIST OPTION AND A DOCUMENT OPTION ARE ASKED FOR SEPARATELY because the stored forms differ —
    `.explicit` holds a comma-joined list, a document holds canonical JSON or a path — and
    guessing from the string's shape would misread a one-element list as a scalar.

    @brief Reconstruct the declaration from an index's records.
    @return The stated mapping.
    @version 1
    """
    from .buildoptions import INLINE_LIST_OPTIONS

    ## THE PREFIX MUST COME OFF, and getting this wrong is why the first version of this function
    ## raised on its own control. Every `tiers` reader takes a section whose keys have already had
    ## `options.` stripped — `_options_meta` does that — so a raw `build_meta` read hands them keys
    ## like `options.predefined.tier`, `stated_options` reports the option as `options.predefined`,
    ## the `INLINE_LIST_OPTIONS` membership test misses, and the list is then decoded as a JSON
    ## document. It failed loudly here only because a comma-joined list is not valid JSON; an
    ## option whose stored value happened to parse would have exported silently wrong.
    section = meta_section(db, OPTIONS_META_PREFIX)

    out: dict[str, Any] = {}
    for option in stated_options(section):
        if option in INLINE_LIST_OPTIONS:
            values = recorded_explicit(section, option)
            if values:
                out[option] = list(values)
            continue
        document = recorded_document(section, option)
        if document is not None:
            out[option] = document
    return out


## @brief Render a declaration mapping as YAML, with a header saying where it came from.
## @param declaration The stated mapping.
## @param db The index it was read from.
## @return The document text, newline-terminated.
## @version 1
## @req REQ-DDB-CONFIG-001
def render(declaration: dict[str, Any], db: Path) -> str:
    """THE HEADER IS NOT DECORATION. This file will be committed into a repository and read months
    later by someone who did not run the export, and the two questions they will have are "did a
    human write this or a tool" and "does it cover everything the build did". The second is the
    dangerous one: this document holds the TIER-1 statements only, so a reader who assumes it is
    the whole configuration will be wrong about every default. Saying so in the file is the only
    place that warning survives.

    An EMPTY declaration still renders the header and an explicit note, because a zero-byte file
    reads as a failed command. "This index recorded no statements" is a result.

    @brief Render the export document.
    @return YAML text.
    @version 1
    """
    import yaml

    head = (
        "# Generated by `clew export` — the TIER-1 STATEMENTS recorded in an index.\n"
        f"# source index: {db.name}\n"
        "#\n"
        "# This is NOT the build's full configuration. It holds only what a caller STATED; the\n"
        "# built-in defaults are deliberately absent, so that improving a default still reaches\n"
        "# this repository instead of being shadowed by a value nobody remembers committing.\n"
        "#\n"
        "# Re-apply with: clew --repo-root <repo> --declare <this file>\n"
    )
    if not declaration:
        return head + "#\n# This index recorded NO tier-1 statements — nothing was stated.\n"
    return head + yaml.safe_dump(declaration, sort_keys=True, default_flow_style=False)


## @brief `clew export` entry point.
## @param argv Arguments after the command word.
## @return Process exit status.
## @version 2
## @req REQ-DDB-CLI-001
def export_main(argv: list[str]) -> int:
    """WRITES TO STDOUT BY DEFAULT, and `--output` is opt-in. The common use is piping into the
    repo's own `.clew.yaml` under review, and a command that silently created that file
    would be a command that overwrites a curated declaration — the one file in this design a human
    is expected to have edited by hand.

    REFUSES AN OUTPUT PATH THAT EXISTS, for the same reason, unless `--force`. `init` prompts before
    touching a CLAUDE.md on the identical argument: a config can be regenerated, a curated document
    cannot.

    @brief Parse arguments and emit the export.
    @return Exit status.
    @version 2
    """
    parser = argparse.ArgumentParser(
        prog=f"clew {EXPORT_COMMAND}",
        description="Write an index's tier-1 statements out as a declaration document.",
    )
    parser.add_argument("--index", required=True, help="path to a built clew.db")
    parser.add_argument("--output", help="write here instead of stdout")
    parser.add_argument(
        "--force", action="store_true", help="overwrite --output if it already exists"
    )
    args = parser.parse_args(argv)

    db = Path(args.index).expanduser().resolve()
    if not db.is_file():
        logger.error("export: no index at %s", db)
        return 1
    text = render(stated_declaration(db), db)
    if not args.output:
        sys.stdout.write(text)
        return 0
    target = Path(args.output).expanduser().resolve()
    if target.exists() and not args.force:
        logger.error(
            "export: %s already exists — pass --force to overwrite it. A declaration is a "
            "curated file; regenerating one on top of hand-written content is not recoverable.",
            target,
        )
        return 1
    target.write_text(text, encoding="utf-8")
    logger.info("export: wrote %s", target)
    return 0
