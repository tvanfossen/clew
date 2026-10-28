# SPDX-License-Identifier: MIT
"""THE LANGUAGE CLAUSE IS GENERATED, NOT MAINTAINED.

**WHY A GENERATOR AND NOT A TEST.** clew grew JavaScript, TypeScript, shell and CMake front ends.
Five public strings named its languages; two were updated, three were not, and a registry crawler
found the gap before the gate did. The first fix attempt wrote today's correct sentence into those
files by hand and added a test to catch the next drift — which is the same arrangement that just
failed, with a tripwire. A sentence a human types can go stale; a sentence a build step produces
cannot.

So the clause between the markers is an ARTIFACT. This script writes it from `clew.languages`,
which derives the set from the routing tables that decide what is actually read. `--check` makes
it a gate: the hook regenerates, and a file that changed means the committed text had fallen
behind. Exactly how `ruff-format` treats a source file.

**TWO CLAUSES, BECAUSE CLEW DOES TWO THINGS.** A HARVESTED language contributes symbols, bodies
and call edges. A REGISTERED-ONLY type is in the file set and findable by name and contributes
nothing. Collapsing them is how "clew supports Perl" becomes a claim `dossier` cannot meet.

**MARKER-DELIMITED, SO THE PROSE AROUND IT STAYS HUMAN.** The generator owns the span between
`<!-- clew:langs -->` and `<!-- /clew:langs -->` (or the TOML/JSON equivalents) and nothing else.
A file with no marker is reported rather than rewritten — silently skipping one is how a
generator comes to cover three files while claiming five.

Usage:
    .venv/bin/python scripts/sync_metadata.py            # write
    .venv/bin/python scripts/sync_metadata.py --check    # fail if writing would change anything
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clew.languages import harvested_phrase, registered_phrase  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

## The marker pair, in the comment syntax each file accepts. The NAME is identical across them so
## one grep finds every generated span.
MARK = "clew:langs"


##
# @brief The generated clause: what is harvested, and what is only named.
# @return One sentence, no trailing full stop so a caller can place it.
# @version 1
def clause() -> str:
    """ONE SENTENCE FOR BOTH SETS, because a reader who sees only the first concludes clew parses
    nothing else, and a reader who sees them merged concludes it parses everything listed.

    @brief Build the derived language clause.
    @return The clause.
    @version 1
    """
    return (
        f"Harvests symbols from {harvested_phrase()}; "
        f"registers {registered_phrase()} files by name without parsing them"
    )


##
# @brief Replace a marker-delimited span in one file.
# @param path The file to rewrite.
# @param open_mark Opening marker, in that file's comment syntax.
# @param close_mark Closing marker.
# @param body The generated text to place between them.
# @param write False to report what would change without touching the file.
# @return (changed, reason) — reason is non-empty when the file could not be handled.
# @version 1
def replace_span(
    path: Path, open_mark: str, close_mark: str, body: str, *, write: bool = True
) -> tuple[bool, str]:
    """REPORTS A MISSING MARKER RATHER THAN SKIPPING IT. A generator that quietly covers three of
    five files is the failure this whole script exists to remove, one level up.

    @brief Rewrite one marker span.
    @return Whether the file changed, and why it could not be handled.
    @version 1
    """
    if not path.is_file():
        return False, f"{path}: not found"
    text = path.read_text("utf-8")
    pattern = re.compile(re.escape(open_mark) + r".*?" + re.escape(close_mark), re.S)
    if not pattern.search(text):
        return False, f"{path}: no {MARK} marker"
    new = pattern.sub(f"{open_mark}{body}{close_mark}", text)
    if new == text:
        return False, ""
    ## `--check` MUST NOT MUTATE THE TREE. A gate that fixes what it is checking reports success
    ## on the second run and leaves an uncommitted edit behind — which is how a "green" check
    ## comes to mean "I changed it for you".
    if write:
        path.write_text(new, "utf-8")
    return True, ""


##
# @brief Rewrite the `description` of a JSON manifest's own plugin entry.
# @param path The manifest.
# @param body The generated clause.
# @param write False to report what would change without touching the file.
# @return (changed, reason).
# @version 1
def replace_json_description(path: Path, body: str, *, write: bool = True) -> tuple[bool, str]:
    """JSON CARRIES NO COMMENTS, so there is nowhere to put a marker. The sentence is identified
    by its own shape instead: the clause is the LAST sentence of `description`, and it is replaced
    wholesale. Identified by the generated prefix rather than by position, so a description a
    human reorders still has its clause found.

    @brief Rewrite a manifest description's trailing generated clause.
    @return Whether the file changed, and why it could not be handled.
    @version 1
    """
    if not path.is_file():
        return False, f"{path}: not found"
    data = json.loads(path.read_text("utf-8"))
    entries = data.get("plugins") if "plugins" in data else [data]
    changed = False
    for entry in entries:
        desc = entry.get("description")
        if not isinstance(desc, str):
            return False, f"{path}: entry has no description"
        stripped = re.sub(r"\s*Harvests symbols from .*?without parsing them\.", "", desc)
        want = f"{stripped.rstrip()} {body}."
        if want != desc:
            entry["description"] = want
            changed = True
    if changed and write:
        path.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
    return changed, ""


##
# @brief Regenerate every derived metadata span.
# @param check True to report drift without writing.
# @return Process exit status.
# @version 1
def main(check: bool) -> int:
    """@brief Sync or check the derived metadata.
    @return 0 when in sync, 1 on drift under --check, 2 when a target could not be handled.
    @version 1
    """
    body = clause()
    changed: list[str] = []
    problems: list[str] = []

    for path, (o, c) in {
        REPO / "pyproject.toml": (f"# <{MARK}>", f"# </{MARK}>"),
        REPO / "README.md": (f"<!-- {MARK} -->", f"<!-- /{MARK} -->"),
    }.items():
        did, why = replace_span(path, o, c, body, write=not check)
        ## `did` IS THE CONDITION, not `why`. The first version appended on an empty `why`, so
        ## every marker file read as drifted on every run — a check that always fails teaches the
        ## reader to ignore it, which is worse than no check.
        if why:
            problems.append(why)
        elif did:
            changed.append(str(path.relative_to(REPO)))
    for path in (REPO / ".claude-plugin/plugin.json", REPO / ".claude-plugin/marketplace.json"):
        did, why = replace_json_description(path, body, write=not check)
        if why:
            problems.append(why)
        elif did:
            changed.append(str(path.relative_to(REPO)))

    print(f"derived clause: {body}")
    ## NAMED, NEVER COUNTED AS DONE. A target this script could not handle is a target whose
    ## metadata is unmanaged, which is indistinguishable from in-sync unless it is printed.
    for why in problems:
        print(f"  UNHANDLED  {why}")
    for name in changed:
        print(f"  {'DRIFTED' if check else 'wrote'}    {name}")
    if problems:
        return 2
    if check and changed:
        print(
            "\nThese files' language clause had fallen behind the routers. It is GENERATED: run\n"
            "  .venv/bin/python scripts/sync_metadata.py\n"
            "and commit the result. Do not hand-edit the clause — that is what went stale."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--check" in sys.argv[1:]))
