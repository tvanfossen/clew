# SPDX-License-Identifier: MIT
"""`error.c` IS GENERATED, AND A READER HAD NO WAY TO LEARN THAT FROM THE INDEX.

mbedtls Q4's rubric says it plainly: *"library/error.c IS GENERATED — the file carries no banner
saying so, so an answer that reads it top to bottom will describe a hand-written lookup table and
be wrong."* Its weight-3 conclusion mark and three of its `set` members all cite one
`add_custom_command` in `library/CMakeLists.txt`.

`clew/cmakeast.harvest_generation` now reads those rules. This wires them to a reply, because a
harvest nothing serves changes nothing an agent can see — the distinction I spent too much of this
review blurring.

**ONE PARTITION, NOT A NEW STAGE, and the vocabulary argues it for me.** `STAGE_SCRIPT_SYMBOLS`'
own comment says it covers two languages in one partition because "every stage in this vocabulary
is harvested over every indexed file, so a second partition would add an empty payload row per
file per index — on a 40,000-file target that is 40,000 rows recording that a C file defines no
shell function." Generation rules live only in CMake files, so a `generation` stage would store
exactly that. The records ride in the script-symbols payload and its `stage_version` bumps.

**THE SUBJECT IS THE GENERATED FILE, NOT THE BUILD FILE.** A reader asking about `error.c` does
not know a `CMakeLists.txt` is involved — that is the whole problem. So `dossier("library/error.c")`
carries it, which is where C1 already put file-level facts.

**BOTH DIRECTIONS, because both are asked.** "Is this file generated, and by what" is the mark;
"what does this script produce" is how a contributor checks they edited the right input.

@brief A generated file says so, and names what produced it.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.query.corpus import file_subject


##
# @brief An index holding one generation rule, as the harvest records it.
# @param tmp_path Per-test temporary directory.
# @return Open connection.
# @version 1
@pytest.fixture()
def generated(tmp_path: Path) -> sqlite3.Connection:
    """The mbedtls shape at minimum size. `output_name` is the BASENAME the rule names, because
    `${CMAKE_CURRENT_BINARY_DIR}/error.c` is a variable reference this pipeline never resolves —
    and the literal is stored beside it so a reader can see what the build file actually said.

    @brief Seed a generated-file row.
    @return Open connection.
    @version 1
    """
    conn = sqlite3.connect(str(tmp_path / "clew.db"))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE generated_files (
            output_name TEXT, output_literal TEXT, kind TEXT,
            source_file TEXT, source_line INTEGER,
            role TEXT, arg_name TEXT, arg_literal TEXT, unresolved INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO path (name, type) VALUES (?, 1)",
        [("library/error.c",), ("library/CMakeLists.txt",), ("scripts/generate_errors.pl",)],
    )
    rows = [
        ("command", "generate_errors.pl", ".../generate_errors.pl", 0),
        ("depends", "generate_errors.pl", ".../generate_errors.pl", 0),
        ("depends", "", "${error_headers}", 1),
        ("depends", "error.fmt", ".../data_files/error.fmt", 0),
    ]
    conn.executemany(
        "INSERT INTO generated_files VALUES ('error.c', "
        "'${CMAKE_CURRENT_BINARY_DIR}/error.c', 'custom_command', "
        "'library/CMakeLists.txt', 134, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return conn


## @brief The generated file's subject says it is generated, and by what.
## @version 1
def test_a_generated_file_says_so(generated: sqlite3.Connection) -> None:
    """RED BEFORE THE FIX: `FileSubject` has no `generated_by`, so the one fact the rubric says an
    answer will get wrong is absent from the reply about that very file.

    Matched on BASENAME, because the build file names `${CMAKE_CURRENT_BINARY_DIR}/error.c` and
    the index holds `library/error.c`. Neither string contains the other, and resolving the
    variable is not available — so the basename is the only honest join, and it is stated as such
    rather than presented as a resolved path.
    """
    built = file_subject(generated, "library/error.c")

    assert built is not None
    assert built.generated_by is not None, "the file the rubric calls generated must say so"
    gen = built.generated_by
    assert gen.kind == "custom_command"
    assert gen.source_file == "library/CMakeLists.txt" and gen.source_line == 134, gen
    assert "generate_errors.pl" in [c.name for c in gen.command], gen.command


## @brief The inputs are listed, and an unresolved one says it is unresolved.
## @version 1
def test_the_inputs_are_listed_and_a_variable_stays_unresolved(
    generated: sqlite3.Connection,
) -> None:
    """THE THREE `set` MEMBERS mbedtls Q4 wants are inputs: the generator, the headers directory
    and `error.fmt`. `${error_headers}` is a glob CMake expands at configure time — it must be
    reported as unresolved rather than dropped, because a reader counting the inputs needs to
    know one of them is a pattern, and must not be given `error_headers` as a filename.
    """
    gen = file_subject(generated, "library/error.c").generated_by

    named = [d.name for d in gen.depends if d.name]
    assert "generate_errors.pl" in named and "error.fmt" in named, gen.depends

    glob = next(d for d in gen.depends if not d.name)
    assert glob.unresolved is True and "error_headers" in glob.literal, glob


## @brief A hand-written file carries no generation claim at all.
## @version 1
def test_a_hand_written_file_has_no_generated_by(generated: sqlite3.Connection) -> None:
    """ABSENCE, NOT A FALSE NEGATIVE FIELD. `CMakeLists.txt` is not generated, and the field is
    None rather than an empty record — the rule `SubjectDossier` follows for every section it
    does not populate. A `generated_by` present-but-empty would read as "we checked and it is
    generated by nothing".
    """
    assert file_subject(generated, "library/CMakeLists.txt").generated_by is None


## @brief The producing script says what it produces.
## @version 1
def test_the_generator_lists_what_it_produces(generated: sqlite3.Connection) -> None:
    """THE OTHER DIRECTION, and it is a different question with a different asker: a contributor
    editing `generate_errors.pl` wants to know what regenerates, which is how they check they
    changed the right input. mbedtls Q4 asks exactly that — "what a contributor has to do to add
    a new one".
    """
    built = file_subject(generated, "scripts/generate_errors.pl")

    assert built is not None
    assert "error.c" in built.generates, (
        f"the script's own subject must name what it produces: {built.generates}"
    )
    ## And a file that produces nothing says so by an empty tuple, which is a measurement: this
    ## index was read and that file generates nothing.
    assert file_subject(generated, "library/error.c").generates == ()
