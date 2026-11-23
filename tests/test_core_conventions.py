# SPDX-License-Identifier: MIT
"""Core conventions agent C's audit found false for real repositories (W6-W10; round 5).

Vetted 2026-11-17 (`.claude/tmp/r5/review-core-bodies-vetted.md`) and approved by the owner. Each test
pairs the false case with the real one of the same shape.

@brief Tests for ISR predicates, extension routing, `super`, JS module keys, worktree first builds.
@version 1
"""

from __future__ import annotations

from clew.blocking import DEFAULT_BLOCKING_PATTERNS, walk_blocking_sites
from clew.tsnode import Parser


def _guards(source: str) -> list[str]:
    tree = Parser("c").parse(source.encode())
    sites = walk_blocking_sites(
        tree, source.encode(), {p.name: p for p in DEFAULT_BLOCKING_PATTERNS}
    )
    return [str(s[-1]) if s else "" for s in sites]


def test_an_isr_predicate_is_a_call_not_a_substring() -> None:
    """W7: `in_irq` is a substring of `within_irq_window`, so a real blocking-in-ISR conflict was
    downgraded to "guarded". A call of the predicate (`k_is_in_isr()`) still guards.

    @brief Predicates match as call tokens.
    """
    false_guard = _guards(
        "void h(void) { if (within_irq_window(dev)) { k_sem_take(&sem, K_FOREVER); } }"
    )
    real_guard = _guards("void h(void) { if (!k_is_in_isr()) { k_sem_take(&sem, K_FOREVER); } }")
    assert not any("within_irq_window" in g for g in false_guard), false_guard
    assert any("k_is_in_isr" in g for g in real_guard), real_guard


def test_an_upper_case_C_suffix_is_cpp() -> None:
    """W9: `.C` and `.H` are the traditional Unix C++ suffixes (GCC reads `.C` as C++); lowering the
    path sent them to the C grammar. `.c` and `.h` are unchanged.

    @brief `.C` / `.H` route to C++.
    """
    from clew.harvest import _ts_language_for

    ## Compared by grammar NAME: each lookup may return a fresh handle for the same grammar.
    def name(path: str) -> str:
        return _ts_language_for(path).__name__

    assert name("x/A.C") == name("x/A.H") == name("a.cpp")
    assert name("x/a.c") == name("a.h") != name("a.cpp")


def _pairs(tmp_path, files: dict[str, str]) -> set[tuple[str, str]]:
    import sqlite3

    from clew.cli import _build_argparser, _run_pipeline

    repo = tmp_path / "repo"
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    conn = sqlite3.connect(str(out))
    rows = conn.execute(
        "SELECT a.definition, b.definition FROM call_edges c JOIN memberdef a ON a.rowid = "
        "c.caller_rowid JOIN memberdef b ON b.rowid = c.callee_rowid"
    ).fetchall()
    conn.close()
    return {(str(x), str(y)) for x, y in rows}


def test_super_names_the_base_class_method(tmp_path) -> None:
    """W6: `super.run()` inside `B.run` was qualified as `B.run` — the override itself — so the
    self-edge was pruned and `B.run -> A.run` never existed. `this.helper()` still resolves in B.

    @brief super starts at the bases.
    """
    pairs = _pairs(
        tmp_path,
        {
            "src/shapes.ts": (
                "export class A {\n  run(): number { return 1; }\n}\n\n"
                "export class B extends A {\n"
                "  run(): number { return super.run() + this.helper(); }\n"
                "  helper(): number { return 2; }\n"
                "}\n"
            )
        },
    )
    assert ("src.shapes.B.run", "src.shapes.A.run") in pairs, pairs
    assert ("src.shapes.B.run", "src.shapes.B.helper") in pairs, pairs


def test_two_files_with_one_module_key_still_resolve_their_own_calls(tmp_path) -> None:
    """W8: `a.test.ts` and `a/test.ts` both become module `src.a.test`, so each file's own
    `helper()` saw two equal definitions in "one scope" and every same-file call was refused. A
    file's own definition is its lexical scope.

    @brief Same-file wins a module-key collision.
    """
    pairs = _pairs(
        tmp_path,
        {
            "src/a.test.ts": (
                "export function helper(): number { return 1; }\n"
                "export function f(): number { return helper(); }\n"
            ),
            "src/a/test.ts": (
                "export function helper(): number { return 2; }\n"
                "export function g(): number { return helper(); }\n"
            ),
        },
    )
    assert ("src.a.test.f", "src.a.test.helper") in pairs, pairs
    assert ("src.a.test.g", "src.a.test.helper") in pairs, pairs


def test_a_linked_worktree_is_a_work_tree_root_and_a_planted_git_file_is_not(tmp_path) -> None:
    """W10: a `git worktree add` tree's `.git` is a FILE (`gitdir: …`), and the first-build gate's
    `.git`-is-a-directory test refused it. The test existed for a reason — a planted one-byte
    `.git` file must not make an arbitrary directory indexable — so git itself is asked, and a
    planted file is still refused.

    @brief Ask git, not the filesystem.
    """
    import subprocess

    from clew.gitenv import git_argv, git_env, is_work_tree_root

    main = tmp_path / "main"
    main.mkdir()
    for args in (("init", "-q"), ("commit", "-q", "--allow-empty", "-m", "x")):
        subprocess.run(
            git_argv("-c", "user.name=t", "-c", "user.email=t@t", *args),
            cwd=main,
            env=git_env(),
            check=True,
        )
    linked = tmp_path / "linked"
    subprocess.run(
        git_argv("worktree", "add", "-q", str(linked)), cwd=main, env=git_env(), check=True
    )
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / ".git").write_text("x")
    assert (linked / ".git").is_file()
    assert is_work_tree_root(main) and is_work_tree_root(linked)
    assert not is_work_tree_root(planted)
    assert not is_work_tree_root(main / "nonexistent")
