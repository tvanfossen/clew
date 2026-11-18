# SPDX-License-Identifier: MIT
"""A qualified name that is both a thread and a function resolves to the FUNCTION, and names the
thread under `also` (T6; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW (entropic F3), confirmed:
`dossier("HealthMonitor::monitor_loop")` returned a 371-byte `thread` stub with no body and no
`also`. The `threads` row is named by that qualified string, so the string resolved as given, and
the C7 re-read (bare tail plus selector) ran only when NOTHING resolved. The function was never
tried. `search(corpus='threads')` serves exactly that name, and the tool's prose says a row's name
goes back to `dossier`, so the stub is what a model following the served text received.

THE FUNCTION WINS because it is the description: a thread row names an entry point, and the entry
point's body, callers and locks are what a reader came for. The thread stays one call away, under
`also`, and `kind='thread'` still selects it by the same spelling.

@brief Tests that a thread never shadows its same-named function.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.query.subject import dossier

_SRC = """\
#include <thread>

class HealthMonitor {
public:
    void start();
private:
    void monitor_loop();
    std::thread worker_;
};

void HealthMonitor::start() {
    worker_ = std::thread(&HealthMonitor::monitor_loop, this);
}

void HealthMonitor::monitor_loop() {
    int beats = 0;
    while (beats < 10) { ++beats; }
}
"""


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """@brief Index the one-file C++ repo. @return (db, repo)."""
    base = tmp_path_factory.mktemp("t6")
    repo = base / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/health.cpp").write_text(_SRC, encoding="utf-8")
    db = base / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return db, repo


def test_the_qualified_name_resolves_to_the_function_with_the_thread_under_also(built) -> None:
    """@brief Function first, with its body; `thread` named, not served."""
    db, repo = built
    d = dossier(db, "HealthMonitor::monitor_loop", repo_root=repo)
    assert d is not None
    assert d.kind == "function"
    assert "thread" in d.also
    assert any("beats" in line for line in d.function.body.lines)


def test_kind_thread_still_selects_the_thread_by_the_same_spelling(built) -> None:
    """@brief The thread stays reachable: the preference is a default, not a removal."""
    db, repo = built
    d = dossier(db, "HealthMonitor::monitor_loop", kind="thread", repo_root=repo)
    assert d is not None and d.kind == "thread"
