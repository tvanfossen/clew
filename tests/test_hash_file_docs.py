# SPDX-License-Identifier: MIT
"""76 INDEXED FILES WITH A HEADER COMMENT AND NO FILE DOCUMENTATION.

`filedocs` ships three extractors — Python, C-family, JS/TS — and **none reads a `#` comment
block.** Measured on the rebuilt mbedtls index:

    .sh              38 indexed,  0 with file documentation
    cmakelists.txt   23 indexed,  0
    makefile          8 indexed,  0
    .pl               6 indexed,  0
    .cmake            1 indexed,  0
    .py              16 indexed, 15          <- the shape that works

62 of those 76 are `.sh` and CMake, which clew ALREADY claims and harvests symbols from. Their
headers were never a C5 omission; they have never been read.

**WHAT IT COSTS, on a graded mark.** mbedtls Q4 asks how a negative return becomes a string and
what a contributor must do to add one. One failed mark (weight 3) cites
`scripts/generate_errors.pl:1-30`, which is:

    #!/usr/bin/env perl
    #
    # Generate error.c
    #
    # Usage: ./generate_errors.pl or scripts/generate_errors.pl without arguments,
    # or generate_errors.pl include_dir data_dir error_file

That is a file-level comment in the ordinary sense and it answers the mark. C5 registered the
path; nothing read the header. I called this evidence structurally out of reach for an
index-only arm, and it is not — the index can hold a file's leading comment without parsing the
language, which is exactly what it already does for YAML and JSON.

**A LICENCE HEADER IS NOT DOCUMENTATION.** Many of those 76 files lead with nothing but
copyright and an SPDX line. Publishing those as a file's documentation would add 76 rows of
boilerplate to the corpus `search(corpus="prose")` reads, and make a real header harder to find
rather than easier — so a block with no prose beyond licence lines is rejected.

@brief A leading `#` comment block is file-level documentation.
@version 1
"""

from __future__ import annotations

import pytest

from clew.filedocs import extract_file_doc

PERL = """#!/usr/bin/env perl

# Generate error.c
#
# Usage: ./generate_errors.pl or scripts/generate_errors.pl without arguments,
# or generate_errors.pl include_dir data_dir error_file
#
# Copyright The Mbed TLS Contributors
# SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later

use strict;
"""


## @brief The mbedtls Q4 header is extracted verbatim enough to answer its mark.
## @version 1
def test_the_graded_perl_header_is_extracted() -> None:
    """RED BEFORE THE FIX: `.pl` matches no extractor, so this returns "".

    Asserted on the CONTENT the mark needs — that the file generates `error.c` and how it is
    invoked — rather than on an exact string, because `_clean` normalises whitespace and the
    assertion should survive that.
    """
    doc = extract_file_doc("scripts/generate_errors.pl", PERL)

    assert doc, "a leading # block is file-level documentation"
    assert "Generate error.c" in doc
    assert "include_dir data_dir error_file" in doc, doc


## @brief The shebang is not part of the documentation.
## @version 1
def test_the_shebang_is_skipped() -> None:
    """`#!/usr/bin/env perl` is a kernel directive that happens to start with `#`. Including it
    makes every script's documentation begin with an interpreter path, which is noise in a
    corpus a reader searches by concept.
    """
    doc = extract_file_doc("scripts/generate_errors.pl", PERL)

    assert "/usr/bin/env" not in doc, doc
    assert doc.lstrip().startswith("Generate error.c"), doc


## @brief Shell and CMake headers are read too.
## @version 1
@pytest.mark.parametrize(
    "path",
    [
        pytest.param("tests/scripts/all.sh", id="sh"),
        pytest.param("library/CMakeLists.txt", id="cmakelists"),
        pytest.param("cmake/Toolchain.cmake", id="cmake"),
        pytest.param("library/Makefile", id="makefile"),
        pytest.param("build/rules.mk", id="mk"),
        pytest.param("scripts/helper.pm", id="perl-module"),
    ],
)
def test_every_hash_comment_type_is_read(path: str) -> None:
    """ALL SIX, because 62 of the 76 unread files are types clew already harvests — the gap was
    never specific to the ones C5 added. Claiming only `.pl` would fix one mark and leave the
    other 70 files silent.
    """
    doc = extract_file_doc(path, "# Builds the thing.\n#\n# Run it with no arguments.\n\ncode\n")

    assert "Builds the thing" in doc, f"{path}: {doc!r}"


## @brief A licence-only header is not documentation.
## @version 1
@pytest.mark.parametrize(
    "header",
    [
        pytest.param(
            "# Copyright The Mbed TLS Contributors\n# SPDX-License-Identifier: MIT\n",
            id="copyright-spdx",
        ),
        pytest.param("# SPDX-License-Identifier: Apache-2.0\n", id="spdx-only"),
        pytest.param("#!/bin/sh\n", id="shebang-only"),
        pytest.param("# \n#\n", id="blank-comments"),
    ],
)
def test_a_licence_only_header_is_rejected(header: str) -> None:
    """Publishing boilerplate as documentation would add rows of it to the corpus
    `search(corpus="prose")` reads and make a real header harder to find. Asserted per shape
    because each of these appears alone at the top of real files in the measured set.
    """
    assert extract_file_doc("x.sh", header + "\ncode\n") == ""


## @brief Licence lines are dropped from a header that also carries prose.
## @version 1
def test_licence_lines_are_dropped_from_a_real_header() -> None:
    """The Perl header above carries BOTH — two prose lines and then copyright. The block is
    accepted for the prose and the licence lines are not published, because a reader searching
    the prose corpus for a concept should not match every file that shares a licence.
    """
    doc = extract_file_doc("scripts/generate_errors.pl", PERL)

    assert "Generate error.c" in doc
    assert "SPDX" not in doc, doc
    assert "Copyright" not in doc, doc


## @brief A file whose comments start below the first code line has no file doc.
## @version 1
def test_a_comment_after_code_is_not_a_file_doc() -> None:
    """The block must LEAD the file. A `#` comment after the first statement documents that
    statement, and attributing it to the file would publish one function's note as the module's
    — the same error `JsFileDoc` guards against by requiring an `@file` tag.
    """
    assert extract_file_doc("x.sh", "set -e\n\n# This documents the next bit.\nrun\n") == ""
