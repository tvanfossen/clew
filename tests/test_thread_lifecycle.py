# SPDX-License-Identifier: MIT
"""Thread lifecycle: whether a spawned thread is joined, detached or a daemon, and where (2.1).

FOUND in the 2.0.0 grid (entropic Q4, −25.4 points): the rubric's mark is that ONE thread is
detached (`std::thread(...).detach()`, external_bridge.cpp:1222) while every other is joined, and
the threads layer recorded where each thread was spawned but nothing about how it ends.

Read from the spawning file's own syntax, never guessed:
- `std::thread(...).detach()` / `.join()` chained on the spawn call;
- `x = std::thread(...)` then `x.join()` / `x.detach()` in the same file, matched by the handle's
  last name (`ct->thread` and `(*it)->thread` are one handle);
- `std::jthread` joins itself;
- `pthread_create(&tid, ...)` then `pthread_join(tid, ...)` / `pthread_detach(tid)`;
- Python `threading.Thread(..., daemon=True)`, or `t = Thread(...)` then `t.join()`.
Nothing found is `unknown` with no line; an interrupt handler has no lifecycle at all (NULL).

@brief Tests thread lifecycle detection.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

## EACH SPAWN HAS ITS OWN ENTRY: `threads` is UNIQUE(name, entry, kind), so lambdas that all call
## `loop()` collapse into one row (the documented first-wins collapse) and hide the rest.
CPP = """#include <thread>
#include <pthread.h>
void one() {}
void two() {}
void three() {}
struct S {
  std::thread worker_;
  void loop();
  void start();
  void stop();
};
void S::loop() {}
void S::start() {
  worker_ = std::thread(&S::loop, this);
  std::thread([]() { one(); }).detach();
  std::thread never = std::thread([]() { two(); });
  std::jthread([]() { three(); });
}
void S::stop() {
  if (worker_.joinable()) { worker_.join(); }
}
static void *entry(void *a) { return a; }
void spawn_c(void) {
  pthread_t tid;
  pthread_create(&tid, 0, entry, 0);
  pthread_detach(tid);
}
#include <signal.h>
static void on_sig(int s) { (void)s; }
void install(void) { signal(SIGINT, on_sig); }
"""

PY = """import threading


def background():
    pass


def quiet():
    pass


def run():
    threading.Thread(target=quiet, daemon=True).start()
    t = threading.Thread(target=background)
    t.start()
    t.join()


def other():
    u = 1
    t = threading.Thread(target=late)
    t.start()
"""


def _threads(tmp_path: Path) -> dict[tuple[str, int], tuple[str | None, int | None]]:
    from clew.cli import _build_argparser, _run_pipeline

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "s.cpp").write_text(CPP)
    (repo / "w.py").write_text(PY)
    db = tmp_path / "x.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    rows = (
        sqlite3.connect(db)
        .execute(
            "SELECT p.name, t.spawn_line, t.lifecycle, t.lifecycle_line FROM threads t "
            "JOIN path p ON p.rowid = t.spawn_path_rowid"
        )
        .fetchall()
    )
    return {(Path(f).name, int(line)): (life, at) for f, line, life, at in rows}


def test_each_spawn_records_how_it_ends(tmp_path: Path) -> None:
    """@brief Joined, detached, daemon and unknown, each with the line that says so."""
    threads = _threads(tmp_path)
    assert threads[("s.cpp", 14)] == ("joined", 20), "worker_ joined in S::stop"
    assert threads[("s.cpp", 15)] == ("detached", 15), "chained .detach()"
    assert threads[("s.cpp", 16)] == ("unknown", None), "a handle nobody joins or detaches"
    assert threads[("s.cpp", 17)] == ("joined", 17), "std::jthread joins itself"
    assert threads[("s.cpp", 25)] == ("detached", 26), "pthread_detach(tid)"
    assert threads[("w.py", 13)] == ("daemon", 13), "Python daemon=True"
    assert threads[("w.py", 14)] == ("joined", 16), "Python t.join()"


def test_a_local_handle_is_ended_only_in_its_own_function(tmp_path: Path) -> None:
    """FOUND MEASURING clew's own tree: a `child` killed in one test was credited with another
    test's `child.join()`. A local (a Python name, a C++ declaration at the spawn) is matched only
    inside the spawning function; a member (`worker_ =`, `self._t`) anywhere in the file.

    @brief Local handles stay local.
    """
    assert _threads(tmp_path)[("w.py", 21)] == ("unknown", None)


def test_a_handler_registration_has_no_lifecycle(tmp_path: Path) -> None:
    """FOUND MEASURING mbedtls: `signal(SIGINT, h)` read `unknown`. No thread is created, so the
    question does not apply and the column is NULL, never "we looked and found nothing".

    @brief A signal handler's lifecycle is absent.
    """
    assert _threads(tmp_path)[("s.cpp", 30)] == (None, None)


def test_a_dossier_serves_the_lifecycle(tmp_path: Path) -> None:
    """@brief The thread record carries `lifecycle` and `lifecycle_line`."""
    from clew.query.models import Thread

    fields = Thread.__dataclass_fields__
    assert "lifecycle" in fields and "lifecycle_line" in fields


def test_a_chained_end_reports_the_line_of_the_end_not_the_spawn() -> None:
    """FOUND MEASURING entropic: a lambda spawn spanning lines 1158-1222 reported 1158, where the
    call starts, when the `.detach()` the rubric names is at 1222.

    @brief The chained `.detach()` line.
    """
    from clew.threadlife import Lifecycles
    from clew.tsnode import Parser

    src = b"void f() {\n  std::thread([]() {\n    work();\n  }).detach();\n}\n"
    tree = Parser("cpp").parse(src)
    stack, spawn = [tree.root_node], None
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        fn = node.child_by_field_name("function") if node.type == "call_expression" else None
        if fn is not None and src[fn.start_byte : fn.end_byte] == b"std::thread":
            spawn = node
    assert spawn is not None
    assert Lifecycles(tree.root_node, src).of(spawn, "std::thread", "", "pthread") == (
        "detached",
        4,
    )
