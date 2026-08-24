# SPDX-License-Identifier: MIT
"""A repo cannot smuggle a directive into the Doxyfile, nor declare a filter command.

THE THREAT. clew indexes UNTRUSTED third-party repositories. Doxygen's configuration is
line-based and its `INPUT_FILTER` / `FILTER_PATTERNS` values are COMMANDS doxygen runs over
each input file. So any repo-controlled byte that reaches the Doxyfile text as a directive is
arbitrary command execution as the developer, from indexing alone.

TWO PATHS, BOTH VERIFIED BY RENDERING THE CONFIG, both closed here.

1. INJECTION VIA A FILE NAME. POSIX allows every byte except NUL and `/` in a filename and
   git stores it, so a hostile repo can ship a file whose basename contains a NEWLINE.
   `INPUT += <path>` then terminates early and the remainder becomes a new directive:

       INPUT += /repo/a.c
       INPUT_FILTER = /bin/sh -c '...' #

   The incremental-refresh path (task #483) is what made this reachable: it is the first
   caller to feed every CHANGED FILE'S OWN NAME into `extra_input`, and it runs from a
   read-only query tool via `_auto_refresh`, so one `dossier` call against an already-indexed
   hostile repo is enough. Doxygen's config cannot REPRESENT such a path, so the file was
   never indexable either way — the only choice is whether we skip it or let it inject.

2. A HOSTILE DOXYFILE, WHICH NEEDS NO INJECTION AT ALL. The target's own Doxyfile is read and
   honoured, so a repo can simply DECLARE `INPUT_FILTER`. Forcing the filter directives off
   is the only thing that closes this, and it is why the fix is two-layered rather than one.

ORDERING IS WHY BOTH LAYERS ARE REQUIRED. The forced flags are concatenated BEFORE
`extra_input`, so a later injected directive would override a forced one. Forcing alone does
not stop path injection; rejecting paths alone does not stop a declared filter.
"""

from __future__ import annotations

from pathlib import Path

from clew.doxygen import _build_doxyfile_content


##
# @brief Directives an indexed repository must never be able to set.
_FILTER_DIRECTIVES = ("INPUT_FILTER", "FILTER_PATTERNS", "FILTER_SOURCE_FILES")


##
# @brief Assignments to a directive in rendered Doxyfile text, last one winning.
# @param text The rendered configuration.
# @param directive The directive name.
# @return Every assigned value for that directive, in order.
# @version 1
def _assignments(text: str, directive: str) -> list[str]:
    """@brief Collect a directive's assigned values.
    @return Assigned values in file order.
    @version 1
    """
    found = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(directive):
            rest = stripped[len(directive) :].lstrip()
            if rest.startswith("=") or rest.startswith("+="):
                found.append(rest.lstrip("+=").strip())
    return found


##
# @brief A newline in a file name must not become a Doxyfile directive.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_a_newline_in_a_path_cannot_inject_a_directive(tmp_path: Path) -> None:
    """@brief Path injection is neutralised.
    @return None.
    @version 1
    """
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text("PROJECT_NAME = probe\nINPUT = .\n", encoding="utf-8")
    hostile = "/repo/a.c\nINPUT_FILTER = /bin/sh -c 'pwn' #"

    text = _build_doxyfile_content(doxyfile, [hostile], None, True, tmp_path, "")

    ## The two COMMAND-valued directives must end up empty. `FILTER_SOURCE_FILES` is a
    ## boolean and its safe value is NO, not empty — asserting "empty" there was a bug in the
    ## first version of this test.
    for directive in ("INPUT_FILTER", "FILTER_PATTERNS"):
        for value in _assignments(text, directive):
            assert not value, (
                f"a file name injected a non-empty {directive} = {value!r}; doxygen runs that "
                f"as a command over every input file, so indexing a hostile repo executes it"
            )
    for value in _assignments(text, "FILTER_SOURCE_FILES"):
        assert value.upper() in ("", "NO"), (
            f"a file name set FILTER_SOURCE_FILES = {value!r}, re-enabling filtering"
        )
    assert "/bin/sh" not in text, "the injected command survived into the rendered configuration"


##
# @brief A target's own Doxyfile must not be able to declare a filter command.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_a_repos_own_doxyfile_cannot_declare_a_filter_command(tmp_path: Path) -> None:
    """NEEDS NO INJECTION. The repo just writes the directive into the Doxyfile it ships,
    which clew reads and honours. Only forcing the value off closes it.

    @brief A declared filter is overridden.
    @return None.
    @version 1
    """
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(
        "PROJECT_NAME = probe\nINPUT = .\n"
        "INPUT_FILTER = /bin/sh -c 'pwn'\n"
        "FILTER_PATTERNS = *.c=/bin/sh\n"
        "FILTER_SOURCE_FILES = YES\n",
        encoding="utf-8",
    )

    text = _build_doxyfile_content(doxyfile, None, None, False, tmp_path, "")

    for directive in ("INPUT_FILTER", "FILTER_PATTERNS"):
        values = _assignments(text, directive)
        assert values, f"{directive} is never assigned, so the repo's declaration stands"
        assert not values[-1], (
            f"the LAST {directive} assignment is {values[-1]!r}; doxygen takes the last one, "
            f"so the repo's filter command still runs"
        )
    sources = _assignments(text, "FILTER_SOURCE_FILES")
    assert sources and sources[-1].upper() == "NO", (
        f"FILTER_SOURCE_FILES ends as {sources[-1:]!r}, so a filter still runs over sources"
    )
