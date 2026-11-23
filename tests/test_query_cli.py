# SPDX-License-Identifier: MIT
"""`clew query` — the export API across a process boundary, for a host that is not Python.

1.3.2, Track 1. A C++ host (or any non-Python consumer) cannot import `clew.query`; it can run a
process and read JSON. `clew query dossier|search` prints exactly what `export_dossier` /
`export_search` return, so the process boundary adds no second wording of any answer.

@brief Tests for the `clew query` CLI verb.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clew import query as q
from clew.query_command import query_main


## @brief Run the verb and parse its stdout.
## @param argv Arguments after `clew query`.
## @param capsys Pytest capture.
## @return (exit code, parsed stdout or None, stderr).
## @version 1
def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, object, str]:
    """@brief Invoke query_main. @return Code, JSON, stderr."""
    code = query_main(argv)
    out, err = capsys.readouterr()
    return code, (json.loads(out) if out.strip() else None), err


def test_a_dossier_prints_the_export_payload(
    rich_db: Path, repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief `clew query dossier NAME` == export_dossier, as JSON.
    @return None.
    @version 1
    """
    code, got, _ = _run(
        ["dossier", "dm_mutex", "--index", str(rich_db), "--repo-root", str(repo_root)], capsys
    )
    assert code == 0
    assert got == q.export_dossier(rich_db, "dm_mutex", repo_root=repo_root)


def test_several_subjects_are_one_batch(
    rich_db: Path, repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief Several positional subjects print the batch envelope.
    @return None.
    @version 1
    """
    names = ["dm_mutex", "main", "definitely_not_indexed_xyz"]
    code, got, _ = _run(
        ["dossier", *names, "--index", str(rich_db), "--repo-root", str(repo_root)], capsys
    )
    assert code == 0
    assert got == q.export_dossier(rich_db, names, repo_root=repo_root)


@pytest.mark.parametrize("corpus", q.EXPORT_CORPORA)
def test_a_search_prints_the_export_payload(
    rich_db: Path, repo_root: Path, capsys: pytest.CaptureFixture[str], corpus: str
) -> None:
    """@brief `clew query search TEXT --corpus C` == export_search, as JSON.
    @return None.
    @version 1
    """
    code, got, _ = _run(
        [
            "search",
            "dm",
            "--corpus",
            corpus,
            "--index",
            str(rich_db),
            "--repo-root",
            str(repo_root),
        ],
        capsys,
    )
    assert code == 0
    assert got == q.export_search(rich_db, "dm", corpus=corpus, repo_root=repo_root)


def test_a_missing_index_is_refused_not_answered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ABSENCE IS NOT EMPTINESS: no index must not print an empty-looking payload.

    @brief A missing --index exits 1 with nothing on stdout.
    @return None.
    @version 1
    """
    code, got, err = _run(["dossier", "x", "--index", str(tmp_path / "none.db")], capsys)
    assert code == 1 and got is None and "no index" in err


def test_a_refused_request_exits_2_with_the_reason(
    rich_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief An unknown corpus (the library's ValueError) exits 2, reason on stderr.
    @return None.
    @version 1
    """
    code, got, err = _run(["search", "x", "--corpus", "nope", "--index", str(rich_db)], capsys)
    assert code == 2 and got is None and "Known corpora" in err


def test_the_verb_is_dispatched_by_the_cli() -> None:
    """@brief `clew query` is a first-word subcommand like its siblings.
    @return None.
    @version 1
    """
    from clew import cli, query_command

    assert cli.QUERY_COMMAND == query_command.QUERY_COMMAND == "query"
