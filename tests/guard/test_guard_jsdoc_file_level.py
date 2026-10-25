# SPDX-License-Identifier: MIT
"""The gate and the index must agree on what documents a JavaScript file.

Group A, 1.1.0 MERGE REVIEW. `clew/filedocs.py` accepts `@file`, `@fileoverview`, `@overview`
or `@module` as a JS/TS file-level doc — `_JSDOC_FILE_TAG` — because those are what JSDoc
actually uses; `@fileoverview` is the one the JSDoc documentation itself leads with. The gate
required the literal `@file`. So a correctly documented JavaScript file was a file doc to the
index and a violation to the gate, and the gate's remedy text told the owner to write a tag
JSDoc does not have.

Two smaller contradictions in the same path: a `#!/usr/bin/env node` shebang or a
`'use strict'` prologue sits above the doc block, and `_find_file_doxygen_start` gives up at
the first line that is not a doc comment — so a Node executable could not have a file block at
all. And `_suggest_file_skeleton` had no JS branch, so it suggested the C spelling.

@brief JSDoc file-level documentation is accepted as the index accepts it.
@version 1
"""

from __future__ import annotations

import pytest

from clew.guard.checks import check_file_presence
from clew.guard.config import CONFIG_DEFAULTS

## The gate only checks file-level presence when a repo asks for it.
_REQUIRE_FILE = {
    "validate": {
        **CONFIG_DEFAULTS["validate"],
        "presence": {
            **CONFIG_DEFAULTS["validate"].get("presence", {}),
            "require_file_doxygen": True,
        },
    },
    "impact": CONFIG_DEFAULTS["impact"],
}


@pytest.mark.parametrize("tag", ["@file", "@fileoverview", "@overview", "@module"])
def test_every_jsdoc_file_tag_the_index_accepts_is_accepted(tag: str) -> None:
    """@brief All four JSDoc file tags satisfy the gate. @version 1"""
    content = f"/**\n * {tag}\n * @brief Does a thing.\n * @version 1.0\n */\nexport const x = 1;\n"

    violations = check_file_presence("thing.js", content, _REQUIRE_FILE)

    assert violations == [], (
        f"`{tag}` documents the file for the index but not for the gate, so a correctly "
        f"documented JSDoc file fails the gate: {[v.message for v in violations]}"
    )


def test_a_shebang_does_not_hide_the_file_block() -> None:
    """A Node executable starts `#!/usr/bin/env node`, which is not a doc comment, so the
    search gave up on line one and reported a file with a perfectly good block as having none.

    @brief A shebang is skipped when locating the file block. @version 1
    """
    content = (
        "#!/usr/bin/env node\n"
        "/**\n * @fileoverview A tool.\n * @brief Does a thing.\n * @version 1.0\n */\n"
        "run();\n"
    )

    assert check_file_presence("tool.js", content, _REQUIRE_FILE) == []


def test_a_use_strict_prologue_does_not_hide_the_file_block() -> None:
    """@brief A `'use strict'` directive is skipped when locating the file block. @version 1"""
    content = (
        "'use strict';\n"
        "/**\n * @module thing\n * @brief Does a thing.\n * @version 1.0\n */\n"
        "run();\n"
    )

    assert check_file_presence("thing.js", content, _REQUIRE_FILE) == []


def test_an_undocumented_js_file_is_told_the_jsdoc_spelling() -> None:
    """THE REMEDY HAS TO BE RUNNABLE. Telling a JavaScript author to write the C file block is
    how an owner concludes the gate does not understand their language.

    @brief The skeleton suggestion names a JSDoc tag. @version 1
    """
    violations = check_file_presence("thing.js", "export const x = 1;\n", _REQUIRE_FILE)

    assert len(violations) == 1
    message = violations[0].message
    assert "@fileoverview" in message, f"the remedy does not name a JSDoc tag: {message}"


def test_a_js_file_with_no_file_tag_at_all_still_fails() -> None:
    """THE CONTROL. Widening which tags count must not make the check vacuous.

    @brief A block with no file tag is still a violation. @version 1
    """
    content = "/**\n * @brief Does a thing.\n * @version 1.0\n */\nexport const x = 1;\n"

    violations = check_file_presence("thing.js", content, _REQUIRE_FILE)

    assert violations, "a JS block naming no file tag must still be reported"
