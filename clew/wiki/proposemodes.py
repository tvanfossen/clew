# SPDX-License-Identifier: MIT
"""A reviewed draft of which assertion fails into which declared mode, and its application.

2.2, the test flowchart's F4 (owner Q/A 2026-11-25). `clew wiki propose-modes` prints, as YAML,
each test in test code that covers a requirement with declared failure modes: those candidate
modes (each with its meaning) and every assertion that carries no `fails_when:` marker yet, as

    - line: 9
      statement: assert add(2, 3) == 5
      proposed: null
      status: unreviewed

An agent fills `proposed` (the clew-wiki skill says how); a person sets `status: accepted` on what
they agree with. `--apply FILE` writes ONLY accepted entries, as inline markers on the assertion's
line, and refuses one whose line no longer reads as the assertion it was proposed for. NOTHING HERE
CHOOSES A MODE: clew makes no model call, and an unreviewed draft changes no file.

@brief Draft and apply per-assertion failure-mode markers.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .checkpins import pin_checks
from .flowchart import marker

## The marker's comment, by file suffix; anything else is a C-family file.
_COMMENT = {".py": "#", ".sh": "#", ".cmake": "#"}


## @brief The draft: per test covering a requirement with declared modes, its unmarked assertions.
## @param db The index.
## @param repo_root The repository.
## @param files Repo-relative test files to limit the draft to, or None for all.
## @return Entries in file and line order; empty when no requirement declares a mode.
## @version 1
## @req REQ-DDB-WIKI-043
def proposals(db: Path, repo_root: Path, files: list[str] | None = None) -> list[dict[str, Any]]:
    """@brief Draft. @return Entries."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        tests = _covering_tests(conn)
        meanings = dict(conn.execute("SELECT mode_id, meaning FROM failure_modes"))
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    out = []
    for (name, file, start, end), modes in sorted(tests.items(), key=lambda t: (t[0][1], t[0][2])):
        if files is not None and file not in files:
            continue
        unmarked = _unmarked(repo_root, file, start, end)
        if unmarked:
            out.append(
                {
                    "test": name,
                    "file": file,
                    "line": start,
                    "modes": [{"id": m, "meaning": meanings.get(m, "")} for m in modes],
                    "assertions": unmarked,
                }
            )
    return out


## @brief Each test in test code and the declared modes it is a candidate for.
## @param conn Open index connection.
## @return {(name, file, first line, last line): [mode ids]}.
## @version 1
## @utility
def _covering_tests(conn: sqlite3.Connection) -> dict[tuple[str, str, int, int], list[str]]:
    """THE CANDIDATES are the modes of every requirement the test covers (`req_test_edges`), plus
    any mode it already names (`test_failure_modes`), in id order.

    @brief Candidate modes per test.
    @return Map.
    """
    rows = conn.execute(
        "SELECT m.name, p.name, m.line, m.bodyend, f.mode_id FROM req_test_edges t "
        "JOIN failure_modes f ON f.req_id = t.req_id "
        "JOIN memberdef m ON m.rowid = t.test_memberdef_rowid "
        "JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        "UNION SELECT m.name, p.name, m.line, m.bodyend, x.mode_id FROM test_failure_modes x "
        "JOIN memberdef m ON m.rowid = x.test_memberdef_rowid "
        "JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id)"
    ).fetchall()
    out: dict[tuple[str, str, int, int], list[str]] = {}
    for name, file, line, end, mode in sorted(rows, key=lambda r: str(r[4])):
        key = (str(name), str(file), int(line or 0), int(end or line or 0))
        if mode not in out.setdefault(key, []):
            out[key].append(str(mode))
    return out


## @brief A test's assertions that carry no marker yet, each unproposed.
## @param repo_root The repository.
## @param file The test's file.
## @param start Its first line.
## @param end Its last line.
## @return Entries; empty when every assertion is marked or the file cannot be read.
## @version 1
## @utility
def _unmarked(repo_root: Path, file: str, start: int, end: int) -> list[dict[str, Any]]:
    """@brief Unmarked assertions. @return Entries."""
    try:
        lines = (repo_root / file).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    body = lines[start - 1 : end]
    return [
        {"line": p.line, "statement": p.statement, "proposed": None, "status": "unreviewed"}
        for p in pin_checks(body, file, set(), start)
        if p.line and marker(lines[p.line - 1]) is None
    ]


## @brief Write the accepted proposals as inline markers.
## @param repo_root The repository.
## @param entries The reviewed draft.
## @return (markers written, refusals naming file:line and why).
## @version 1
## @req REQ-DDB-WIKI-043
def apply(repo_root: Path, entries: list[dict[str, Any]]) -> tuple[int, list[str]]:
    """ONLY `status: accepted` with a `proposed` id is written. A line that no longer starts with
    the assertion's statement (the file moved on since the draft) is refused and named, never
    rewritten in place; so is one that already carries a marker.

    @brief Apply a reviewed draft.
    @return Count and refusals.
    """
    written, refused = 0, []
    by_file: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        for item in entry.get("assertions") or []:
            if item.get("status") == "accepted" and item.get("proposed"):
                by_file.setdefault(str(entry["file"]), []).append(item)
    for file, items in by_file.items():
        count, problems = _apply_file(repo_root / file, file, items)
        written += count
        refused += problems
    return written, refused


## @brief Write one file's accepted markers.
## @param path The file.
## @param file Its repository-relative name, for refusals.
## @param items Its accepted assertions.
## @return (markers written, refusals).
## @version 1
## @utility
def _apply_file(path: Path, file: str, items: list[dict[str, Any]]) -> tuple[int, list[str]]:
    """@brief Apply to one file. @return Count and refusals."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    comment = _COMMENT.get(path.suffix, "//")
    written, refused = 0, []
    for item in items:
        index = int(item["line"]) - 1
        text = lines[index].rstrip("\n") if 0 <= index < len(lines) else ""
        first = (
            str(item.get("statement", "")).splitlines()[0].strip() if item.get("statement") else ""
        )
        if not first or not text.strip().startswith(first) or marker(text) is not None:
            refused.append(
                f"{file}:{item['line']}: the line no longer reads `{first}`, or is marked"
            )
            continue
        lines[index] = f"{text}  {comment} fails_when: {item['proposed']}\n"
        written += 1
    if written:
        path.write_text("".join(lines), encoding="utf-8")
    return written, refused
