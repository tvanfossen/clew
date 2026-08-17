# SPDX-License-Identifier: MIT
## @brief Make a benchmark artifact publishable before it is ever written to disk.
## @version 1
"""Run data is the point of this harness, and run data that cannot be committed is
worth nothing. This module is the difference.

THE PROBLEM, CONCRETELY. Every artifact a cell produces carries this machine's
layout. The argv record holds `/home/<user>/Projects/<target>`; the generated MCP
config holds `/home/<user>/Projects/docs-db/.venv/bin/clew-mcp`; the
preserved transcript holds both, in the arguments of every tool call the agent
made. Committing a run directory verbatim would republish the disclosure that
already forced a build-version bump once.

THERE IS NO LONGER A PUBLISHABILITY GATE. A pre-commit audit of every tracked text
file for exactly that shape used to be the backstop behind this module; it is
DELETED, and nothing replaced it. So this module is not belt-and-braces any more —
it is the ONLY thing standing between a sweep and a leak, and a shape it fails to
rewrite reaches HEAD unchallenged.

WHY REWRITE RATHER THAN EXCLUDE. Dropping the argv and the transcripts from git
would destroy the evidence, which is the one thing the owner
asked to be able to vet. Rewriting the home prefix to `~` costs nothing a reviewer
needs: `~/Projects/<target>` is *more* reproducible than an absolute path, not
less, because it is the only one of the two that means anything on someone else's
disk.

WHAT THIS IS NOT. It is not a scrub of the answers' CONTENT. Nothing here removes a
symbol, a finding or a citation, and nothing here can make an unpublishable target
publishable — a benchmark against a private repository stays unpublishable no
matter what its paths say. This normalises machine layout, and that is all it
claims.

HONESTY NOTE FOR THE PRESERVED TRANSCRIPTS. `<cell>.transcript.jsonl` is described
elsewhere as the authoritative raw record. After this pass it is byte-for-byte the
session transcript EXCEPT that home-directory prefixes read `~`. The JSON structure,
the ordering, the tool calls and every result are untouched, so the narrative
remains re-derivable from it. That caveat is stated wherever the file is described,
because a record labelled "raw" that has been quietly edited is worse than one
labelled "normalised".
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

## The exact prefix belonging to the machine running the sweep. Substituted first and
## literally, so the common case produces a `~` a reader recognises rather than a
## redaction marker that tells them nothing.
_HOME = str(Path.home())

## Belt and braces for any OTHER user's home that reached an artifact — a path quoted
## out of a config, a stack trace from a subprocess. This regex used to be kept
## deliberately identical to the one a pre-commit publishability audit enforced, so that
## "the scrub passes" meant something. That audit is DELETED and this pattern is now
## unchecked against anything: it is the definition, not a copy of one.
_FOREIGN_HOME = re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+")

## The replacement must NOT itself match the pattern above. The obvious choice — the same
## prefix with a placeholder username after it — failed the repo's own publishability gate
## the first time this file was committed, because that placeholder is not one of the
## sanctioned fictional users. A sanitiser built that way manufactures the very shape it
## exists to remove, in every artifact it touches.
##
## It then failed a SECOND time, on the comment explaining the first failure: writing the
## rejected string out as prose put it back in the file. Same trap the repo already
## records for a doc comment that names its own tag — describe the shape, never spell it.
_FOREIGN_REPLACEMENT = "<redacted-home>"

## File suffixes this module knows how to rewrite in place. Anything else in a run
## directory is left alone and REPORTED, never silently skipped: a sanitiser that
## quietly ignores a file type is how a leak survives a clean run.
TEXT_SUFFIXES = frozenset({".md", ".json", ".jsonl", ".csv", ".txt", ".yaml", ".yml"})


## @brief Normalise machine-specific home paths out of a text artifact.
## @param text Artifact content.
## @return Content with home directories rewritten.
## @version 1
def publishable(text: str) -> str:
    """@brief Rewrite home-directory prefixes to `~`.
    @return Normalised text.
    @version 1
    """
    return _FOREIGN_HOME.sub(_FOREIGN_REPLACEMENT, text.replace(_HOME, "~"))


## @brief Write a text artifact, normalised, creating parent directories.
## @param path Destination path.
## @param text Content to write.
## @return The path written.
## @version 1
def write(path: Path, text: str) -> Path:
    """The single write path for every benchmark artifact. A second, un-normalised
    write helper would reintroduce the problem the moment somebody adds an output —
    which is precisely how the transcript preservation shipped unsanitised.

    @brief Write one normalised artifact.
    @return The destination path.
    @version 1
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(publishable(text), encoding="utf-8")
    return path


## @brief Write a JSON artifact, normalised.
## @param path Destination path.
## @param payload Any JSON-serialisable object.
## @return The path written.
## @version 1
def write_json(path: Path, payload: Any) -> Path:
    """@brief Serialise and write one normalised JSON artifact.
    @return The destination path.
    @version 1
    """
    return write(path, json.dumps(payload, indent=2) + "\n")


## @brief Copy a file into the run directory, normalising it on the way.
## @param src Source file.
## @param dst Destination path.
## @return The path written.
## @version 1
def copy(src: Path, dst: Path) -> Path:
    """Replaces `shutil.copy2` for artifacts that leave this machine. `errors="replace"`
    because a transcript killed mid-write can end on a partial byte sequence, and losing
    a whole cell's history to one bad byte is the wrong trade.

    @brief Copy one file with normalisation.
    @return The destination path.
    @version 1
    """
    return write(dst, src.read_text(encoding="utf-8", errors="replace"))


## @brief Rewrite an existing run directory in place.
## @param root Run directory.
## @return (rewritten, skipped) — paths changed, and paths of unknown type.
## @version 1
def sanitise_tree(root: Path) -> tuple[list[Path], list[Path]]:
    """For run data produced BEFORE sanitisation existed, and as an idempotent
    belt-and-braces pass before committing any run. Re-running it is a no-op, so it is
    safe to make it a reflex.

    Unknown file types are RETURNED, not ignored. The caller reports them; a silent
    skip would let a leaking artifact sit inside a directory the operator believes was
    cleaned.

    @brief Normalise every artifact under a run directory.
    @return (rewritten paths, skipped paths).
    @version 1
    """
    rewritten: list[Path] = []
    skipped: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in TEXT_SUFFIXES:
            skipped.append(path)
            continue
        original = path.read_text(encoding="utf-8", errors="replace")
        cleaned = publishable(original)
        if cleaned != original:
            path.write_text(cleaned, encoding="utf-8")
            rewritten.append(path)
    return rewritten, skipped
