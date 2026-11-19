# SPDX-License-Identifier: MIT
"""A file `guard.validate.exclude` leaves out is counted in the gate's skip report (PG6; 2.0.0).

FOUND 2026-11-19 by checking a claim I had made to a consumer: a `validate.exclude` match was
logged at DEBUG and returned before the skip was recorded, so an excluded file vanished from the
report while `gate_exclusion` skips were counted. AGENTS.md: "A gate that reports success while
checking nothing is worse than a red one ... If you add a skip, print the count." A repository
excluding a header to defer a fix should see that file named as not checked, every run.

@brief Tests that declared exclusions are counted.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.guard.main import main

_BLOCK = "/**\n * @file {name}\n * @brief B.\n * @version 1.0\n */\n"


def test_an_excluded_file_is_counted_as_not_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """@brief One file excluded by a declared glob: the stderr report counts it, naming the reason."""
    (tmp_path / "gen").mkdir()
    (tmp_path / "gen/a.c").write_text(_BLOCK.format(name="a.c"))
    (tmp_path / "b.c").write_text(_BLOCK.format(name="b.c"))
    (tmp_path / ".clew.yaml").write_text('guard:\n  validate:\n    exclude: ["gen/**"]\n')
    monkeypatch.chdir(tmp_path)
    assert main(["validate", "--no-git", "gen/a.c", "b.c"]) == 0
    err = capsys.readouterr().err
    assert "1 file(s) not checked" in err and "validate.exclude" in err, err
