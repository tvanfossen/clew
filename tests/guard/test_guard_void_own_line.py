# SPDX-License-Identifier: MIT
"""A return type on its own line still decides whether `@return` is required (2.0.0, PG2 defect).

FOUND BY A CONSUMER (entropic, migrating to clew 728020d0):

    ENTROPIC_EXPORT void
    entropic_storage_destroy(entropic_storage_backend_t storage);

was asked for `@return`. `_is_void_function` reads the first three lines from the declaration's
start for one containing the name, and SKIPPED a line where the name sits in column 0 — which is
exactly GNU style and the export-macro style, where the return type is on the line before. So the
`void` was never seen and the function was treated as non-void. tree-sitter does not rescue it: an
unknown export macro parses as the type and `void` lands in an ERROR node.

@brief Tests that a return type on its own line is read for the void decision.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.guard.main import main

_HEADER = """/**
 * @brief Create.
 * @param p Path.
 * @return Handle.
 * @version 1
 */
API_EXPORT handle_t
make(const char* p);

/**
 * @brief Destroy.
 * @param s Handle.
 * @version 1
 */
API_EXPORT void
destroy(handle_t s);
"""


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> int:
    """@brief Validate one header in a clean repo. @return rc."""
    (tmp_path / ".clew.yaml").write_text("guard:\n  validate: {}\n")
    (tmp_path / "a.h").write_text(text)
    monkeypatch.chdir(tmp_path)
    return main(["validate", "--no-git", "a.h"])


def test_a_void_return_type_on_its_own_line_needs_no_return_tag(
    tmp_path, monkeypatch, capsys
) -> None:
    """@brief The consumer's shape: no @return finding for `destroy`."""
    assert _run(tmp_path, monkeypatch, _HEADER) == 0, capsys.readouterr().err


def test_a_non_void_return_type_on_its_own_line_still_needs_one(
    tmp_path, monkeypatch, capsys
) -> None:
    """@brief The control: drop `make`'s @return and it is still refused."""
    rc = _run(tmp_path, monkeypatch, _HEADER.replace(" * @return Handle.\n", ""))
    err = capsys.readouterr().err
    assert rc == 1 and "'make'" in err and "@return" in err, err
