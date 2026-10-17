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

import shutil
import sqlite3

import pytest

from clew.doxygen import _build_doxyfile_content, run_doxygen


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


## EVERY doxygen option whose value is a COMMAND doxygen executes. Enumerated from
## `doxygen -g`'s own template against the 1.9.8 binary, not from memory — the first version
## of this fix forced three of them and called it closed, which is how `QHG_LOCATION` survived.
_EXEC_VALUED = (
    "INPUT_FILTER",
    "FILTER_PATTERNS",
    "FILTER_SOURCE_PATTERNS",
    "FILE_VERSION_FILTER",
    "HHC_LOCATION",
    "QHG_LOCATION",
    "LATEX_CMD_NAME",
    "MAKEINDEX_CMD_NAME",
    "LATEX_MAKEINDEX_CMD",
    "DOT_PATH",
    "DIA_PATH",
    "MSCGEN_TOOL",
    "PLANTUML_JAR_PATH",
)

## Generators clew does not consume. It reads the sqlite3 database and NOTHING else — there is
## no XML, HTML or LaTeX reader anywhere in `clew/` (the `cli.py` module docstring's "SQLite +
## XML" is stale). Every one of these carries its own file-and-command surface, and
## `HTML_EXTRA_FILES` in particular COPIES a repo file into the output directory preserving its
## exec bit, which is what supplied the cwd-relative path a `QHG_LOCATION` attack needs.
_UNUSED_GENERATORS = (
    "GENERATE_HTML",
    "GENERATE_LATEX",
    "GENERATE_MAN",
    "GENERATE_RTF",
    "GENERATE_XML",
    "GENERATE_DOCBOOK",
    "GENERATE_AUTOGEN_DEF",
    "GENERATE_PERLMOD",
    "GENERATE_QHP",
    "GENERATE_HTMLHELP",
    "GENERATE_ECLIPSEHELP",
    "GENERATE_DOCSET",
)


##
# @brief A hostile Doxyfile cannot leave any command-valued option set.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_no_command_valued_option_survives_a_hostile_doxyfile(tmp_path: Path) -> None:
    """TABLE-DRIVEN ON PURPOSE. The previous fix forced INPUT_FILTER, FILTER_PATTERNS and
    FILTER_SOURCE_FILES and its docstring declared the path closed. `QHG_LOCATION` then
    executed anyway — doxygen runs qhelpgenerator, and `HTML_EXTRA_FILES` copies a repo file
    into the output tree with its exec bit intact to supply the path. Verified against 1.9.8.

    Driving the assertion off an enumerated list means the only way to satisfy it is to
    actually force the option, so a newly-discovered option cannot be quietly omitted.

    @brief Every exec-valued option ends empty.
    @return None.
    @version 1
    """
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(
        "PROJECT_NAME = probe\nINPUT = .\n"
        + "".join(f"{k} = /bin/sh\n" for k in _EXEC_VALUED)
        + "GENERATE_QHP = YES\nGENERATE_HTML = YES\nHTML_EXTRA_FILES = ./pwn.sh\n",
        encoding="utf-8",
    )
    text = _build_doxyfile_content(doxyfile, None, None, False, tmp_path, "")

    for key in _EXEC_VALUED:
        values = _assignments(text, key)
        assert values, f"{key} is never assigned, so the repo's value stands"
        assert not values[-1], (
            f"the LAST {key} assignment is {values[-1]!r}; doxygen takes the last one, so the "
            f"repo's command still runs"
        )
    for key in _UNUSED_GENERATORS:
        values = _assignments(text, key)
        assert values and values[-1].upper() == "NO", (
            f"{key} ends as {values[-1:]!r}; clew reads only the sqlite3 database, so every "
            f"other generator is surface it does not need"
        )
    assert _assignments(text, "HTML_EXTRA_FILES")[-1] == "", (
        "HTML_EXTRA_FILES still copies a repo-chosen file into the output tree with its exec "
        "bit preserved, which is what supplies an attacker a runnable path"
    )


##
# @brief A declared `predefined` value cannot inject a directive.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_declared_predefined_cannot_inject_a_directive(tmp_path: Path) -> None:
    """THE THIRD CHANNEL, and the one the previous fix missed entirely. `predefined` is
    concatenated AFTER the forced block, so anything it smuggles wins — and it comes from the
    TARGET REPO's own `.clew.yaml`, parsed by `_declared_macros` with only `str(v).strip()`,
    so an interior newline survives and a trailing `#` defeats the quoting.

    Both existing tests in this module pass `""` here, which is why this was invisible.

    @brief A predefined macro cannot become a directive.
    @return None.
    @version 1
    """
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text("PROJECT_NAME = probe\nINPUT = .\n", encoding="utf-8")
    hostile = "PREDEFINED += X=1\nINPUT_FILTER = /bin/sh -c 'pwn' #\n"

    text = _build_doxyfile_content(doxyfile, None, None, False, tmp_path, hostile)

    for value in _assignments(text, "INPUT_FILTER"):
        assert not value, (
            f"a declared predefined macro injected INPUT_FILTER = {value!r}, which doxygen "
            f"runs as a command over every input file"
        )
    assert "/bin/sh" not in text, "the injected command survived into the configuration"


## File-reading doxygen COMMANDS, which are a separate surface from the file-reading
## OPTIONS above them. An option is a Doxyfile key clew can restate; these are commands
## written in a SOURCE COMMENT, so no Doxyfile key disarms them — measured against doxygen
## 1.9.8: with `EXAMPLE_PATH =` forced empty, `@verbinclude secret.txt` still resolves
## against the process cwd (the repo root) and `@verbinclude /etc/hostname` resolves
## absolutely, both landing verbatim in `memberdef.detaileddescription`.
##
## `ALIASES` is the only lever that closes them, and it does: a BARE redefinition
## (`verbinclude=…`) overrides the built-in, the LAST assignment wins, and the arity form
## (`verbinclude{1}=…`) does NOT override — so a target repo cannot take the command back,
## because clew's block is appended after the repo's own text.
_FILE_READING_COMMANDS = (
    "verbinclude",
    "htmlinclude",
    "latexinclude",
    "rtfinclude",
    "maninclude",
    "docbookinclude",
    "xmlinclude",
    "include",
    "includelineno",
    "includedoc",
    "dontinclude",
    "snippet",
    "snippetlineno",
    "snippetdoc",
)


##
# @brief Every file-reading doxygen command is neutered by a forced alias.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_no_file_reading_command_survives_a_hostile_source_comment(tmp_path: Path) -> None:
    """H1, 1.1.0 SECURITY AUDIT. A doc comment reading `@verbinclude /etc/hostname` made
    doxygen inline that file into the served description — an arbitrary read whose result is
    presented to a model as this repository's documentation, which is the provenance an agent
    has no way to doubt. `EXAMPLE_PATH` is NOT the fix (measured: empty still resolves against
    cwd, and an absolute argument ignores it entirely) and neither is stripping `<verbatim>`
    from the served text — doxygen emits the identical element for an owner's legitimate
    `@verbatim` block, so a content filter cannot tell a leak from documentation.

    TABLE-DRIVEN for the reason the exec-valued test above is: the only way to satisfy it is
    to actually force each command, so the next one cannot be quietly omitted.

    @brief Each file-reading command's last ALIASES assignment is clew's.
    @return None.
    @version 1
    """
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(
        "PROJECT_NAME = probe\nINPUT = .\nEXAMPLE_PATH = /\nEXAMPLE_RECURSIVE = YES\n"
        ## The target taking the command BACK is the half a naive fix misses.
        + "".join(f'ALIASES += "{c}=ATTACKER-WINS "\n' for c in _FILE_READING_COMMANDS),
        encoding="utf-8",
    )

    text = _build_doxyfile_content(doxyfile, None, None, False, tmp_path, "")

    aliases = _assignments(text, "ALIASES")
    for command in _FILE_READING_COMMANDS:
        ours = [a for a in aliases if a.strip('"').startswith(f"{command}=")]
        assert ours, f"@{command} reads a repo-chosen file and is not neutered"
        assert "ATTACKER-WINS" not in ours[-1], (
            f"the LAST ALIASES assignment for @{command} is the repository's "
            f"({ours[-1]!r}); doxygen takes the last one, so the command still reads files"
        )

    ## AND THE OPTIONS that steer where those commands look, restated for the same reason
    ## every other read-external option in the forced block is.
    for key in ("EXAMPLE_PATH", "INCLUDE_PATH", "IMAGE_PATH"):
        values = _assignments(text, key)
        assert values and not values[-1], (
            f"{key} ends as {values[-1:]!r}, so the repository still chooses where "
            f"doxygen looks for files to inline"
        )
    assert _assignments(text, "EXAMPLE_RECURSIVE")[-1].upper() == "NO", (
        "EXAMPLE_RECURSIVE is a boolean, and an empty value would read as doxygen's own "
        "default rather than as a refusal"
    )


@pytest.mark.skipif(shutil.which("doxygen") is None, reason="asserted against a real doxygen run")
##
# @brief End to end: a hostile source comment inlines nothing into the index.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_a_file_inlining_comment_leaks_nothing_through_a_real_doxygen_run(tmp_path: Path) -> None:
    """THE TEXT TEST ABOVE ASSERTS THE DOXYFILE; THIS ONE ASSERTS DOXYGEN. The forced block is
    only a defence if doxygen honours it the way it was measured to, and a version bump could
    change that silently — the Doxyfile would still contain the lines and the leak would be
    back. Both arms of the original PoC run here: a relative argument (which resolves against
    cwd, the repo root) and an absolute one (which ignores EXAMPLE_PATH entirely).

    @brief No sentinel from an inlined file reaches any description column.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "secret.txt").write_text("SENTINEL-INLINE-LEAK\n", encoding="utf-8")
    (repo / "a.c").write_text(
        "/**\n"
        " * @brief Ordinary brief.\n"
        " * @details Relative:\n"
        " * @verbinclude secret.txt\n"
        " * @details Absolute:\n"
        " * @verbinclude /etc/hostname\n"
        " */\n"
        "int ordinary(void) { return 0; }\n",
        encoding="utf-8",
    )
    doxyfile = repo / "Doxyfile"
    doxyfile.write_text("PROJECT_NAME = probe\nINPUT = .\nQUIET = YES\n", encoding="utf-8")

    db = run_doxygen(doxyfile, repo, output_dir=tmp_path / "out")

    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT name, briefdescription, detaileddescription, inbodydescription FROM memberdef"
    ).fetchall()
    conn.close()

    served = " ".join(str(cell) for row in rows for cell in row)
    assert "SENTINEL-INLINE-LEAK" not in served, (
        f"a repo file was inlined into a served description: {rows}"
    )
    ## THE OTHER HALF OF THE ARGUMENT: the function is still indexed and still documented, so
    ## the refusal costs the ordinary case nothing.
    assert any(name == "ordinary" for name, *_ in rows)
    assert "Ordinary brief" in served
