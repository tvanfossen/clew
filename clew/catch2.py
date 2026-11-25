# SPDX-License-Identifier: MIT
"""Catch2 test cases as covering tests: their titles, tags and `@req` comments (2.1, clew#74).

FOUND by entropic (clew 2.0.1): `dossier(REQ-LOOP-007)` returned `tests: []` for every
requirement. Catch2's `TEST_CASE("title", "[tag][REQ-LOOP-007]") { ... }` is a macro, so doxygen
records each case as a function NAMED `TEST_CASE` (982 of them in entropic's tree) and no `@req`
is ever read from it.

ONE READER, TWO USERS: the index links a case to the requirements it names
(`requirements.import_req_test_edges`), and `clew guard impact` reads the same cases straight from
the test tree, with no index, to list the tests covering each changed requirement.

A case NAMES a requirement two ways, both written by the test's author:
- a Catch2 tag that IS the id (`[REQ-LOOP-007]`), matched against the catalog by the caller;
- `@req ID` in the comment block directly above the macro.
The title is the case's name, which is what ctest and Catch2's own filter select on.

@brief Read Catch2 test cases from source lines.
@version 1
"""

from __future__ import annotations

import re
from dataclasses import dataclass

## The case-defining macros. `TEST_CASE_METHOD`'s first argument is the fixture class, which is
## not a string literal, so the first literal is still the title.
CASE_MACROS = ("TEST_CASE", "SCENARIO", "TEMPLATE_TEST_CASE", "TEST_CASE_METHOD")
## How far a macro's argument list may run past its first line before it is given up on.
_MAX_ARG_LINES = 8
## A C/C++ string literal (escapes kept as written).
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
## One Catch2 tag.
_TAG = re.compile(r"\[([^\]]+)\]")
## A `@req` / `\req` in a comment line.
_REQ = re.compile(r"[@\\]req\s+(\S+)")
## A line that is part of a comment block.
_COMMENT = re.compile(r"^\s*(//|/\*|\*)")
## The macro opening a case, at the start of a line.
_OPENS = re.compile(r"^\s*(" + "|".join(CASE_MACROS) + r")\s*\(")


## @brief One Catch2 test case.
## @version 1
@dataclass(frozen=True)
class Catch2Case:
    """@brief A test case's title, tags and comment `@req` ids. @version 1"""

    title: str
    tags: tuple[str, ...]
    reqs: tuple[str, ...]
    line: int


## @brief The Catch2 case whose macro opens on a given line, if one does.
## @param lines The file's lines.
## @param line The 1-based line of the macro (doxygen's `memberdef.line`).
## @return The case, or None when that line opens no case macro.
## @version 1
## @req REQ-DDB-SCHEMA-006
def read_case(lines: list[str], line: int) -> Catch2Case | None:
    """The arguments may span lines (a title on one, tags on the next), so the text is read up to
    the macro's closing parenthesis or `_MAX_ARG_LINES`, whichever comes first.

    @brief Read one case.
    @return Case or None.
    """
    if not 1 <= line <= len(lines) or not _OPENS.match(lines[line - 1]):
        return None
    args = _arguments(lines[line - 1 : line - 1 + _MAX_ARG_LINES])
    literals = _STRING.findall(args)
    title = literals[0] if literals else ""
    tags = tuple(_TAG.findall(literals[1])) if len(literals) > 1 else ()
    return Catch2Case(title=title, tags=tags, reqs=_comment_reqs(lines, line), line=line)


## @brief Every Catch2 case in a file.
## @param lines The file's lines.
## @return The cases, in file order.
## @version 1
## @req REQ-DDB-GUARD-010
def cases_in(lines: list[str]) -> list[Catch2Case]:
    """@brief All cases. @return Cases."""
    found = (read_case(lines, n) for n, text in enumerate(lines, 1) if _OPENS.match(text))
    return [c for c in found if c is not None]


## @brief The requirement ids a case names, from its tags and its comment.
## @param case The case.
## @param catalog The catalog's ids; a tag counts only when it is one.
## @return The ids, each once, tags first.
## @version 1
## @utility
def named_reqs(case: Catch2Case, catalog: set[str] | frozenset[str]) -> list[str]:
    """A TAG IS AN ID ONLY WHEN THE CATALOG SAYS SO: `[core]` and `[2.14.6]` are tags too. A
    comment `@req` is the author's explicit link and counts as written.

    @brief Named requirement ids.
    @return Ids.
    """
    out = [t for t in case.tags if t in catalog] + list(case.reqs)
    return list(dict.fromkeys(out))


## @brief A macro's argument text, up to its closing parenthesis.
## @param lines The lines from the macro's own onward.
## @return The text between the opening parenthesis and its match (or as far as was read).
## @version 1
## @utility
def _arguments(lines: list[str]) -> str:
    """Parentheses inside string literals are skipped, so a title like `"f(x) works"` does not
    end the argument list early.

    @brief Argument text.
    @return Text.
    """
    text = "\n".join(lines)
    start = text.find("(")
    depth, quoted, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if quoted:
            escaped, quoted = (False, True) if escaped else (ch == "\\", ch != '"')
            continue
        quoted = ch == '"'
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth == 0:
            return text[start + 1 : i]
    return text[start + 1 :]


## @brief The `@req` ids in the comment block directly above a line.
## @param lines The file's lines.
## @param line The 1-based line of the macro.
## @return The ids, in order.
## @version 1
## @utility
def _comment_reqs(lines: list[str], line: int) -> tuple[str, ...]:
    """DIRECTLY ABOVE: the block ends at the first line that is not a comment, a blank line
    included, so a comment belonging to the previous case is never borrowed.

    @brief Comment ids.
    @return Ids.
    """
    block: list[str] = []
    n = line - 2
    while n >= 0 and _COMMENT.match(lines[n]):
        block.append(lines[n])
        n -= 1
    return tuple(m for text in reversed(block) for m in _REQ.findall(text))
