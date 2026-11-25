# SPDX-License-Identifier: MIT
"""propose-modes: a reviewed draft of which assertion fails into which declared mode (2.2, F4).

OWNER Q/A 2026-11-25. `clew wiki propose-modes` lists, per test that covers a requirement with
declared failure modes, those candidate modes (with meanings) and each assertion that carries no
`fails_when:` marker yet, every one `proposed: null`, `status: unreviewed`. An agent fills
`proposed` (the clew-wiki skill says how); a person sets `status: accepted` on what they agree
with; `--apply` writes ONLY accepted entries, as inline markers, and refuses a line whose text no
longer matches the assertion it was proposed for. clew itself makes no model call.

@brief Tests propose-modes.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import yaml

CATALOG = """requirements:
  REQ-A-001:
    title: adds
    failure_modes:
      FM-A-001-1: wrong sum
      FM-A-001-2: identity broken
"""

TESTS = '''"""@brief Tests."""
from src.add import add


## @brief Sums.
## @req REQ-A-001
def test_sums():
    """@brief Sums."""
    assert add(2, 3) == 5
    assert add(1, 0) == 1  # fails_when: FM-A-001-2
    assert add(0, 0) == 0
'''


def _build(tmp_path: Path) -> tuple[Path, Path]:
    from clew.cli import _build_argparser, _run_pipeline

    repo = tmp_path / "repo"
    for rel, text in {
        "src/__init__.py": "",
        "src/add.py": '"""@brief Add."""\n\n\n## @brief Add.\n## @req REQ-A-001\ndef add(a, b):\n'
        '    """@brief Add."""\n    return a + b\n',
        "tests/test_add.py": TESTS,
        "reqs.yaml": CATALOG,
        ".clew.yaml": "requirements:\n  file: reqs.yaml\n",
    }.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    db = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return repo, db


def test_the_draft_lists_candidate_modes_and_the_unmarked_assertions(tmp_path: Path) -> None:
    """@brief The covered requirement's modes; assertions 9 and 11, unproposed; 10 is marked."""
    from clew.wiki.proposemodes import proposals

    repo, db = _build(tmp_path)
    (entry,) = proposals(db, repo)
    assert (entry["test"], entry["file"]) == ("test_sums", "tests/test_add.py")
    assert entry["modes"] == [
        {"id": "FM-A-001-1", "meaning": "wrong sum"},
        {"id": "FM-A-001-2", "meaning": "identity broken"},
    ]
    assert [(a["line"], a["proposed"], a["status"]) for a in entry["assertions"]] == [
        (9, None, "unreviewed"),
        (11, None, "unreviewed"),
    ]
    assert entry["assertions"][0]["statement"] == "assert add(2, 3) == 5"


def test_apply_writes_only_accepted_entries_and_refuses_a_moved_line(tmp_path: Path) -> None:
    """@brief Accepted → marker; rejected → untouched; a line that changed → refused, named."""
    from clew.wiki.proposemodes import apply, proposals

    repo, db = _build(tmp_path)
    (entry,) = proposals(db, repo)
    first, last = entry["assertions"]
    first.update(proposed="FM-A-001-1", status="accepted")
    last.update(proposed="FM-A-001-2", status="rejected")
    written, refused = apply(repo, [entry])
    text = (repo / "tests" / "test_add.py").read_text().splitlines()
    assert (written, refused) == (1, [])
    assert text[8] == "    assert add(2, 3) == 5  # fails_when: FM-A-001-1"
    assert text[10] == "    assert add(0, 0) == 0", "a rejected entry writes nothing"
    last.update(status="accepted", statement="assert add(9, 9) == 18")
    written, refused = apply(repo, [{**entry, "assertions": [last]}])
    assert written == 0 and refused and "tests/test_add.py:11" in refused[0]


def test_the_command_prints_yaml_and_applies_a_reviewed_file(tmp_path: Path, capsys) -> None:
    """@brief `clew wiki propose-modes` to stdout; `--apply FILE` writes the accepted markers."""
    from clew.wiki.command import wiki_main

    repo, db = _build(tmp_path)
    capsys.readouterr()  # the build's own progress output is not the draft
    assert wiki_main(["propose-modes", "--index", str(db), "--repo-root", str(repo)]) == 0
    draft = yaml.safe_load(capsys.readouterr().out)
    draft[0]["assertions"][1].update(proposed="FM-A-001-1", status="accepted")
    reviewed = tmp_path / "reviewed.yaml"
    reviewed.write_text(yaml.safe_dump(draft))
    args = ["propose-modes", "--index", str(db), "--repo-root", str(repo), "--apply", str(reviewed)]
    assert wiki_main(args) == 0
    assert (
        "# fails_when: FM-A-001-1" in (repo / "tests" / "test_add.py").read_text().splitlines()[10]
    )
