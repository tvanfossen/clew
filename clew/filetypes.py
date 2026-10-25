# SPDX-License-Identifier: MIT
"""Skip files that are not text before anything parses or hashes them.

A file's extension says what it should be, not what it is: a 2 GB zip named `.c`, a
compiled object checked in as `.h`, or a PNG with a stray `.py` suffix all reached
doxygen and the tree-sitter harvest, and the tree scan sha256'd every byte of them on
each cold build. lang-parsing-substrate's `classify_file` decides from metadata and the
first 8 KiB (magic numbers plus NUL / control / invalid-UTF-8 ratios, calibrated on
~201K files with no C-family file misread) whether a file is text.

POLICY: a file classified BINARY is skipped by the index and the gate. Nothing else is:
an empty file (`__init__.py`) is legitimate source, and no size limit is applied,
because a large generated source file (an amalgamation such as `sqlite3.c`) is still
source and the index has always read it. A file that cannot be classified (unreadable,
not a regular file) is left to the reader that would have opened it, which reports it
the way it always has.

@brief Binary-file detection ahead of every parser.
@version 1
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._common import logger


## @brief One file the index or the gate did not read, and why.
## @version 1
@dataclass(frozen=True)
class SkippedFile:
    """@brief A skipped file's path and its classification."""

    path: Path
    binary_kind: str
    mime: str | None


## @brief The binary classification of one file, or None when it is text or unreadable.
## @param path File to classify.
## @return A SkippedFile when the file is binary, else None.
## @version 1
## @req REQ-DDB-PIPE-011
def binary_file(path: Path | str) -> SkippedFile | None:
    """@brief Classify one file, returning a SkippedFile only when it is binary."""
    from lang_parsing_substrate import classify_file

    try:
        found = classify_file(str(path))
    except OSError:
        return None
    if found.kind != "binary":
        return None
    return SkippedFile(Path(path), found.binary_kind or "unknown", found.mime)


## @brief Split files into the readable ones and the binaries to skip.
## @param paths Candidate files.
## @return The binaries, in input order.
## @version 1
## @req REQ-DDB-PIPE-011
def binary_files(paths: list[Path]) -> list[SkippedFile]:
    """Each skip is logged at INFO with its classification, because a file silently
    missing from an index is the failure this project has recorded most often.

    @brief Classify a batch and return the binaries.
    @return The skipped files.
    """
    skipped = [s for s in (binary_file(p) for p in paths) if s is not None]
    for s in skipped:
        logger.info(
            "file typing: skipping %s — %s binary%s, not source",
            s.path,
            s.binary_kind,
            f" ({s.mime})" if s.mime else "",
        )
    return skipped
