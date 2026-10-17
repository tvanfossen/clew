# SPDX-License-Identifier: MIT
"""Properties every subprocess in this package must have, asserted over the SOURCE.

A per-call-site test catches the site it was written for. These two catch the NEXT one, which is
the only kind of coverage that survives a contributor who has not read the audit:

  * every `git` invocation goes through `gitenv.git_argv`, because a repository's own
    `.git/config` can name a command git then RUNS (`core.fsmonitor` and friends) — so a bare
    `["git", ...]` argv is arbitrary code execution by the tree being inspected, reproduced
    against git 2.34.1 in `tests/test_gitenv.py`;
  * every `subprocess.run` passes a `timeout`, because a hostile repository can otherwise hang a
    build, a pre-commit gate or a long-lived MCP server indefinitely.

AST, NOT GREP, so a call spread over several lines or carrying a comment still counts, and so the
assertion is about the call's ARGUMENTS rather than about the text near it.

@brief Source-level invariants for subprocess use across clew.
@version 1
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "clew"

## MODULES WHOSE ARGV REACHES `subprocess` THROUGH A VARIABLE, with the choke point that
## disarms it. This exemption exists because the first version of this test claimed in its
## docstring to report a variable first element and did not — and `clew/guard/git.py` builds
## `["git", …]` at six call sites, hands them to an injectable runner, and so passed silently
## while the gate executed commands chosen by the repository under review. That was C1 again,
## in the worse context, and a test for an unrelated finding is what surfaced it.
##
## An entry here is not a pass: the module must call `git_argv` (asserted below), and a
## behavioural test must cover it against a real hostile repository
## (`tests/test_gitenv.py::test_the_gate_git_path_cannot_run_the_trees_commands`).
_INDIRECT_ARGV = {"guard/git.py": "run_git"}


## `clew/doxygen.py`'s doxygen call is a managed `Popen`, not `subprocess.run`: it owns a process
## group, a reaper and a 900 s watchdog of its own (`_reap_process_group`, `_DOXYGEN_TIMEOUT`), and
## `communicate(timeout=…)` is applied at the wait rather than at construction. Named here with
## its reason rather than left to pass silently, so the exemption cannot quietly widen.
_MANAGED_POPEN = {"doxygen.py"}


## @brief Every `subprocess.run` / `subprocess.Popen` call in the package, with its source file.
## @return List of (relative path, ast.Call) pairs.
## @version 1
def _subprocess_calls() -> list[tuple[str, ast.Call]]:
    """@brief Collect the package's subprocess call sites. @return (path, call) pairs. @version 1"""
    found: list[tuple[str, ast.Call]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"run", "Popen"}:
                continue
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id == "subprocess":
                found.append((str(path.relative_to(PACKAGE)), node))
    return found


def test_every_subprocess_call_in_the_package_is_bounded() -> None:
    """A MISSING TIMEOUT IS A HANG SOMEONE ELSE PAYS FOR. The gate runs inside a developer's
    commit; the MCP server runs for a session; both call git and cargo against trees they did not
    write. `cargo metadata` on a hostile `Cargo.toml` and `git ls-files` on a huge tree were both
    unbounded before the 1.1.0 audit.

    @brief No subprocess.run in clew/ omits a timeout.
    @version 1
    """
    unbounded = [
        f"{path}:{call.lineno}"
        for path, call in _subprocess_calls()
        if call.func.attr == "run" and not any(kw.arg == "timeout" for kw in call.keywords)
    ]

    assert not unbounded, (
        "these subprocess.run calls carry no timeout, so a hostile or merely huge repository "
        f"can hang the build, the gate or the server indefinitely: {unbounded}"
    )


def test_every_git_invocation_disarms_the_inspected_trees_config() -> None:
    """THE RULE LIVES IN ONE PLACE AND THIS IS WHAT KEEPS IT THERE. `gitenv.git_argv` prepends
    `-c core.fsmonitor=` and its siblings, which outrank the config file inside the tree being
    inspected. A call site that builds its own `["git", …]` list reopens the execution path, and
    it reopens it silently — the query still works, it just also runs the attacker's command.

    Asserted on the argv's first element: a literal `"git"` is the defect, `git_argv(...)` is the
    fix. A variable first element is reported too, since it cannot be shown safe from here.

    @brief No call site builds a bare git argv.
    @version 1
    """
    offenders: list[str] = []
    for path, call in _subprocess_calls():
        if not call.args:
            continue
        argv = call.args[0]
        if isinstance(argv, ast.Call):
            func = argv.func
            if isinstance(func, ast.Name) and func.id == "git_argv":
                continue
        if isinstance(argv, (ast.List, ast.Tuple)) and argv.elts:
            first = argv.elts[0]
            if isinstance(first, ast.Constant) and first.value == "git":
                offenders.append(f"{path}:{call.lineno}")
        elif isinstance(argv, ast.Constant) and argv.value == "git":
            offenders.append(f"{path}:{call.lineno}")

    assert not offenders, (
        "these git calls bypass gitenv.git_argv, so the inspected repository's own .git/config "
        f"can make git run a command of its choosing: {offenders}"
    )


@pytest.mark.parametrize(("module", "choke_point"), sorted(_INDIRECT_ARGV.items()))
def test_a_module_with_an_indirect_argv_disarms_at_its_choke_point(
    module: str, choke_point: str
) -> None:
    """THE OTHER HALF OF THE RULE ABOVE, which the argv test structurally cannot see. Where a
    module builds a git argv and passes it to a RUNNER, the literal list is not the thing that
    reaches `subprocess` — so the assertion has to move to the function every such call passes
    through, and that function has to be named rather than inferred.

    Asserted on the AST so the call is `git_argv(...)` and not a mention in a comment.

    @brief Each indirect-argv module's choke point calls git_argv.
    @version 1
    """
    tree = ast.parse((PACKAGE / module).read_text(encoding="utf-8"))
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == choke_point
    ]
    assert functions, f"{module} no longer defines {choke_point}; this exemption is stale"
    called = {
        node.func.id
        for node in ast.walk(functions[0])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "git_argv" in called, (
        f"{module}:{choke_point} builds the argv that reaches subprocess and does not call "
        f"git_argv, so the inspected repository's own .git/config chooses a command git runs"
    )


@pytest.mark.parametrize("key", ["core.fsmonitor", "core.hooksPath", "diff.external"])
def test_the_disarmed_key_list_reaches_the_argv(key: str) -> None:
    """The helper is only a defence if the keys actually land on the command line, and
    `core.hooksPath` must be `/dev/null` rather than empty — an empty value sends git back to the
    repository's own hooks directory.

    @brief git_argv emits each command-valued key, hooksPath pointed at /dev/null.
    @version 1
    """
    from clew.gitenv import git_argv

    argv = git_argv("ls-files")
    assert argv[0] == "git" and argv[-1] == "ls-files"
    expected = f"{key}=/dev/null" if key == "core.hooksPath" else f"{key}="
    assert expected in argv, f"{key} is not disarmed in {argv}"
