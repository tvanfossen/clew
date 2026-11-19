# SPDX-License-Identifier: MIT
"""The wiki's entry points honour the platform facts, declared `entry_patterns` and Poetry scripts
(P4; 2.0.0: W3, W4 / D8 of the reviews).

W3 (CONFIRMED): `wiki.entrypoints._mains` looked for functions named `main` and nothing else, so
ESP-IDF's `app_main` (one of `reachability.ENTRY_PATTERN_FACTS`) and every pattern a repository
declared under `entry_patterns` had no flow. The liveness layer already consulted both.

W4 / D8 (CONFIRMED): `_scripts` read only PEP 621 `[project.scripts]`; `py_entrypoints` already
reads Poetry's `[tool.poetry.scripts]` too, and the wiki now reuses it.

NOT THE NAME HEURISTICS: `%_cb`, `%callback%` and the rest seed liveness, where a false positive
only keeps a function alive. As wiki flows they would draw every callback as an entry point.

@brief Tests the wiki's entry-point discovery.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.wiki.entrypoints import entry_point_flows

_C = """\
static int helper(int x) { return x + 1; }

int main(void) { return helper(0); }

void app_main(void) { helper(1); }

int start_server(int port) { return helper(port); }

void handle_cb(int x) { helper(x); }
"""
_PY = "def helper():\n    return 1\n\n\ndef run():\n    return helper()\n"
_PYPROJECT = '[tool.poetry]\nname = "pkg"\n\n[tool.poetry.scripts]\npkgtool = "pkg.cli:run"\n'


def test_facts_declared_patterns_and_poetry_scripts_are_entry_points(tmp_path: Path) -> None:
    """@brief main, app_main, start_server (declared) and run (Poetry) have flows; handle_cb does not."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "pkg").mkdir()
    (repo / "src/app.c").write_text(_C)
    (repo / "pkg/__init__.py").write_text("")
    (repo / "pkg/cli.py").write_text(_PY)
    (repo / "pyproject.toml").write_text(_PYPROJECT)
    (repo / ".clew.yaml").write_text('entry_patterns:\n  - "start_%"\n')
    db = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    entries = {(f.entry, f.file) for f in entry_point_flows(db, repo, 2)}
    assert {
        ("main", "src/app.c"),
        ("app_main", "src/app.c"),
        ("start_server", "src/app.c"),
        ("run", "pkg/cli.py"),
    } <= entries
    assert ("handle_cb", "src/app.c") not in entries
