# SPDX-License-Identifier: MIT
"""`clew init` — the first command a new user runs, and it REWRITES A FILE.

Almost every assertion here is on BYTES, not on a return code. The command's whole
job is a surgical edit of a document it did not write: a `.mcp.json` normally
already names other servers, and the user-scope target is `~/.claude.json`, which
on a real machine is a hundred-plus kilobytes of accumulated Claude Code state
that no tool can regenerate. "Exit 0" says nothing about whether that survived.

**There is exactly ONE write target and that is now part of the contract.** The command
briefly also wrote a delimited guidance block into the scope's CLAUDE.md; that capability
and its tests are gone. Installing a tool does not get to edit prose the user maintains, so
the only file `init` touches is the MCP client config.

## The safety argument, stated once

`mcp_config.apply_plan` writes to `global_config_path()`, which defaults to
`~/.claude.json`. `tests/conftest.py` carries an AUTOUSE, session-scoped fixture
that points `CLAUDE_CONFIG_DIR` at a throwaway directory, and `global_config_path`
honours that variable, so no test here can reach the real file. That is not taken
on faith: `test_the_global_config_path_is_inside_the_pytest_tmp_tree` asserts the
resolved path is under pytest's own base temp directory and is not the user's,
`global_home` re-asserts it for every test that writes there, and the ONE test
that unsets the variable (`test_global_scope_refuses_without_evidence`) patches
`Path.home` at the same time and asserts the resolved path is under tmp BEFORE it
calls anything.

## Why the environment is stubbed

`stub_env` fakes the console script, `doxygen` and the MCP SDK probe. Without it
these tests would measure the MACHINE — on a checkout whose console script is not
installed, `init` refuses to write anything at all, and every merge assertion
below would be vacuously testing a refusal. The stub is also what keeps the suite
free of environment-gated skips, which the release checklist forbids.

@brief Tests for the init command: merge safety, scopes, resolution, the doctor.
@version 1
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from clew import cli, init_command
from clew.mcp_config import (
    CLAUDE_CONFIG_DIR_ENV,
    CONSOLE_SCRIPT,
    DEFAULT_INDENT,
    MCP_ENTRY_NAME,
    REPO_CONFIG_NAME,
    SERVERS_KEY,
    ConfigError,
    apply_plan,
    claude_state_dir,
    config_path,
    global_config_available,
    global_config_path,
    plan_merge,
    resolve_server_command,
    server_entry,
)
from clew.vocabulary import (
    CHECK_FAIL,
    CHECK_OK,
    CHECK_WARN,
    INIT_ACTION_ADD,
    INIT_ACTION_CREATE,
    INIT_ACTION_UNCHANGED,
    INIT_ACTION_UPDATE,
    INIT_SCOPE_GLOBAL,
    INIT_SCOPE_REPO,
)

REPO = Path(__file__).resolve().parents[1]

## The suffix `apply_plan` preserves the previous file under. Spelled here rather
## than imported because the POINT of these tests is that the shipped name does
## not change silently — a backup nobody can find is not a backup.
BACKUP_SUFFIX = ".clew.bak"

## A stand-in for the user's real `~/.claude.json`: several top-level keys, in a
## deliberate order, with `mcpServers` in the MIDDLE and an unrelated server
## already in it. Shaped after the real file (numStartups / userID / projects /
## oauthAccount all exist there) because the failure this guards is a merge that
## reformats or reorders a document it only needed to add one key to.
LIVE_LIKE_DOCUMENT: dict[str, Any] = {
    "numStartups": 412,
    "installMethod": "native",
    "autoUpdates": True,
    "mcpServers": {
        "entropic": {"type": "stdio", "command": "entropic-mcp", "args": ["--flag"]},
        "other-tool": {"type": "sse", "url": "http://127.0.0.1:9999/sse"},
    },
    "userID": "0f1e2d3c4b5a",
    "tipsHistory": {"new-user-warmup": 3, "shift-enter": 11},
    "projects": {"/home/somebody/work": {"allowedTools": [], "history": [{"display": "hello"}]}},
    "oauthAccount": {"emailAddress": "somebody@example.com"},
}


## @brief A throwaway target repo, so no test can rewrite this checkout's own config.
## @param tmp_path Per-test temporary directory.
## @return Path to an empty repo directory.
## @version 1
@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Deliberately EMPTY. A bare directory is the day-one state `init` is written
    for, and it also means `--repo-root .` can never be mistaken for this repo.

    @brief An empty temporary repo to register.
    @return The repo path.
    @version 1
    """
    target = tmp_path / "target-repo"
    target.mkdir()
    return target


## @brief Make command resolution, doxygen and the SDK probe deterministic.
## @param tmp_path Per-test temporary directory.
## @param monkeypatch pytest's attribute/env patcher.
## @return Path to the fake bin directory holding the stubbed executables.
## @version 1
@pytest.fixture
def stub_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Three substitutions, each for a measurement that would otherwise be about
    this machine rather than about the command:

    * `shutil.which` answers only for files in the fake bin directory — so a test
      can DELETE `doxygen` there and get the missing-binary path deterministically,
      and an unrelated tool on the real PATH cannot change an outcome.
    * `sys.executable`'s parent is that same directory, which is where
      `resolve_server_command` looks when PATH misses.
    * `importlib.util.find_spec` reports the server's own import line as present,
      delegating every other name to the real one (the import system does not
      route through this function, but libraries do, and breaking it wholesale
      would break lazily-imported pipeline modules).

    @brief Stub the console script, doxygen and the MCP SDK probe.
    @return The fake bin directory.
    @version 1
    """
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    for name in (CONSOLE_SCRIPT, "doxygen"):
        script = bindir / name
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)

    def fake_which(cmd: str, *args: object, **kwargs: object) -> str | None:
        candidate = bindir / cmd
        return str(candidate) if candidate.is_file() else None

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, package: str | None = None) -> object:
        return object() if name == "mcp.server.fastmcp" else real_find_spec(name, package)

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(sys, "executable", str(bindir / "python"))
    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    return bindir


## @brief A per-test user-scope config directory, re-proving it is under tmp.
## @param tmp_path Per-test temporary directory.
## @param tmp_path_factory pytest's session temp-directory factory.
## @param monkeypatch pytest's env patcher.
## @return Path to the isolated config directory.
## @version 1
@pytest.fixture
def global_home(
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Narrows the session-wide isolation to ONE directory per test, so two
    global-scope tests cannot see each other's writes, and asserts the resolved
    target is inside pytest's temp tree before any test is allowed to write.

    The assertion is not decoration. This is the fixture that hands out a path
    `apply_plan` will overwrite; if the isolation ever regressed, the value
    handed over would be the user's real state file.

    @brief Give this test its own Claude config directory, verified under tmp.
    @return The isolated config directory.
    @version 1
    """
    isolated = tmp_path / "claude-home"
    isolated.mkdir()
    monkeypatch.setenv(CLAUDE_CONFIG_DIR_ENV, str(isolated))
    resolved = global_config_path()
    assert resolved.is_relative_to(tmp_path_factory.getbasetemp()), (
        f"the user-scope config resolved OUTSIDE pytest's temp tree: {resolved}"
    )
    return isolated


## @brief Run `init` for a repo, returning its exit code and stdout.
## @param argv Extra arguments after the built-in `--repo-root`.
## @param repo_root Repo to register.
## @param capsys pytest's output capture.
## @return (exit code, captured stdout).
## @version 1
def _run(argv: list[str], repo_root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """@brief Invoke `init_main` and collect what it printed.

    @param argv Extra arguments.
    @param repo_root Repo to register.
    @param capsys Output capture.
    @return (exit code, stdout).
    @version 1
    """
    code = init_command.init_main(["--repo-root", str(repo_root), *argv])
    return code, capsys.readouterr().out


## @brief The entry `init` writes in the stubbed environment.
## @return The expected `mcpServers` entry.
## @version 2
def _expected_entry() -> dict[str, Any]:
    """Derived from `server_entry`, never spelled out: a test that hardcodes the
    entry passes just as happily when the entry is wrong everywhere at once.
    Under `stub_env` the resolved command is always the bare console script.

    Takes no scope any more: neither scope passes `--repo`, so there is nothing left
    for the scope to change (gh#22).

    @brief Build the entry the stubbed environment should produce.
    @return The expected entry mapping.
    @version 2
    """
    return server_entry(CONSOLE_SCRIPT)


## @brief The first JSON object embedded in captured stdout.
## @param out Captured stdout.
## @return The substring from the first `{` to the last `}`.
## @version 1
def _printed_json(out: str) -> str:
    """Spans first-brace to last-brace, which is only valid because the surrounding
    output carries no other braces — the doctor lines, the dry-run headings and the
    guidance block are all brace-free. `_disclosure_document` below relies on the same
    property, so a sentinel leaking into the output would land INSIDE this span and
    break the parse loudly rather than passing unnoticed.

    @brief Slice the printed JSON object out of stdout.
    @return The JSON text.
    @version 1
    """
    return out[out.index("{") : out.rindex("}") + 1]


## A `~/.claude.json` stand-in carrying strings that must NEVER reach stdout. The
## sentinels sit where the real file keeps its most sensitive state: a project path
## and a prompt-history entry. They are deliberately distinctive so an absence
## assertion cannot pass by accident on a generic word like "hello", and the user
## name stays `somebody` because that is one of the sanctioned fictional users. The
## gate that enforced that is DELETED; the choice is UNCHECKED and kept by hand.
DISCLOSURE_SENTINELS = (
    "/home/somebody/clients/acme-teardown",
    "rewrite the auth token rotation for acme",
    "sentinel-user-id-9f3a11",
)


## @brief A live-like config document seeded with recognisable sentinel strings.
## @return The document to write to the dry-run target.
## @version 1
def _disclosure_document() -> dict[str, Any]:
    """Built from `LIVE_LIKE_DOCUMENT` rather than beside it, so the shape this repo
    already treats as realistic is the shape the disclosure tests measure.

    @brief Build the sentinel-bearing config document.
    @return The document mapping.
    @version 1
    """
    path, prompt, user = DISCLOSURE_SENTINELS
    return {
        **LIVE_LIKE_DOCUMENT,
        "userID": user,
        "projects": {path: {"allowedTools": [], "history": [{"display": prompt}]}},
    }


## @brief Assert no sentinel reached stdout while the entry still did.
## @param out Captured stdout.
## @version 1
def _assert_entry_only(out: str) -> None:
    """The load-bearing assertion of gh#27, and it checks BOTH directions. Absence
    alone would pass for a dry run that printed nothing useful; presence alone was
    already true of the defective version, which printed the entry inside the whole
    document.

    @brief Check the entry is shown and the unrelated document is not.
    @version 1
    """
    for sentinel in DISCLOSURE_SENTINELS:
        assert sentinel not in out, f"--dry-run disclosed unrelated config state: {sentinel!r}"
    for key in ("numStartups", "tipsHistory", "oauthAccount", "other-tool"):
        assert key not in out, f"--dry-run printed the surrounding document: {key}"
    assert MCP_ENTRY_NAME in out, "the entry under review must still be named"


# ─── the merge contract: what lands on disk ──────────────────────────────────


## @brief A fresh repo gets a `.mcp.json` holding exactly this server.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_fresh_repo_creates_the_config(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The baseline. NEITHER scope passes `--repo` any more (gh#22).

    Repo scope used to write `--repo .`, which pinned the server: it refused to
    retarget, so a session could not index a second repository (gh#19). And the pin
    was not even reliable at the job it was for — a stale one invalidated a 36-cell
    benchmark run. The server now DERIVES its target from `$CLAUDE_PROJECT_DIR`, which
    resolves to the project the config is committed in, whereas `--repo .` resolved
    against the LAUNCHING process's cwd."""
    del stub_env
    code, out = _run([], repo, capsys)
    target = repo / REPO_CONFIG_NAME
    assert code == 0, out
    assert json.loads(target.read_text(encoding="utf-8")) == {
        SERVERS_KEY: {MCP_ENTRY_NAME: _expected_entry()}
    }
    assert _expected_entry()["args"] == [], "no scope may pin the server any more"


## @brief Every unrelated server in an existing config survives byte-identical.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_other_servers_survive_byte_identical(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE failure mode this command's design exists to prevent. A doctor that
    registers itself by writing a fresh one-server document has destroyed the
    user's other servers, and the result still looks like a valid config — the
    damage is invisible until something they rely on stops connecting.

    Compared as re-serialised subtrees rather than by `==` so a changed nesting or
    a dropped key inside an entry cannot pass."""
    del stub_env
    target = repo / REPO_CONFIG_NAME
    before = {
        SERVERS_KEY: {
            "entropic": {"type": "stdio", "command": "entropic-mcp", "args": ["--flag"]},
            "chrome": {"type": "sse", "url": "http://127.0.0.1:1234/sse", "env": {"A": "b"}},
        }
    }
    target.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    code, out = _run([], repo, capsys)
    assert code == 0, out
    after = json.loads(target.read_text(encoding="utf-8"))
    for name, entry in before[SERVERS_KEY].items():
        assert json.dumps(after[SERVERS_KEY][name], sort_keys=True) == json.dumps(
            entry, sort_keys=True
        ), f"unrelated server {name} was altered"
    assert list(after[SERVERS_KEY]) == ["entropic", "chrome", MCP_ENTRY_NAME], (
        "existing servers must keep their order, ours appended"
    )


## @brief Re-running against an identical entry rewrites nothing.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_identical_entry_is_a_no_op_on_bytes(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Asserted on bytes AND on the absence of a backup, because those catch
    different mistakes: identical CONTENT could still have been produced by a
    rewrite (which would leave a `.bak` and churn the file's mtime), and this
    repo's own committed `.mcp.json` is supposed to make `init` here a genuine
    no-op rather than a re-write that happens to match."""
    del stub_env
    target = repo / REPO_CONFIG_NAME
    first_code, _ = _run([], repo, capsys)
    assert first_code == 0
    original = target.read_bytes()
    second_code, out = _run([], repo, capsys)
    assert second_code == 0, out
    assert target.read_bytes() == original, "an identical entry must not rewrite the file"
    assert not target.with_name(target.name + BACKUP_SUFFIX).exists(), (
        "no write happened, so there is nothing to back up"
    )
    assert "already registered and identical" in out, "the no-op must be reported as one"
    assert list(json.loads(original)[SERVERS_KEY]) == [MCP_ENTRY_NAME], "no duplicate entry"
    assert plan_merge(target, _expected_entry()).action == INIT_ACTION_UNCHANGED


## @brief A differing existing entry is refused, and the file is untouched.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_differing_entry_is_refused_without_force(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A user who hand-tuned their entry — extra args, a wrapper command, a
    different pinned repo — must not lose it to a doctor being helpful. The
    refusal has to carry the DIFF, or "it differs" is not actionable."""
    del stub_env
    target = repo / REPO_CONFIG_NAME
    hand_tuned = {
        SERVERS_KEY: {
            MCP_ENTRY_NAME: {
                "type": "stdio",
                "command": "/opt/wrapper/clew-mcp",
                "args": ["--repo", "/elsewhere", "--verbose"],
            }
        }
    }
    target.write_text(json.dumps(hand_tuned, indent=2) + "\n", encoding="utf-8")
    original = target.read_bytes()
    code, out = _run([], repo, capsys)
    assert code == 1
    assert target.read_bytes() == original, "a refusal must not modify the file"
    assert not target.with_name(target.name + BACKUP_SUFFIX).exists()
    assert "--force" in out
    assert "/opt/wrapper/clew-mcp" in out, "the diff must show what would be lost"


## @brief `--force` replaces the differing entry and keeps the neighbours.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_force_replaces_the_differing_entry(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--force` is scoped to OUR key. Overriding the conflict rule must not turn
    into permission to rewrite the document."""
    del stub_env
    target = repo / REPO_CONFIG_NAME
    target.write_text(
        json.dumps(
            {
                SERVERS_KEY: {
                    "entropic": {"type": "stdio", "command": "entropic-mcp", "args": []},
                    MCP_ENTRY_NAME: {"type": "stdio", "command": "stale", "args": []},
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    code, out = _run(["--force"], repo, capsys)
    assert code == 0, out
    after = json.loads(target.read_text(encoding="utf-8"))
    assert after[SERVERS_KEY][MCP_ENTRY_NAME] == _expected_entry()
    assert after[SERVERS_KEY]["entropic"] == {
        "type": "stdio",
        "command": "entropic-mcp",
        "args": [],
    }
    assert INIT_ACTION_UPDATE in out


## @brief The backup holds the ORIGINAL bytes, not the new ones.
## @param tmp_path Per-test temporary directory.
## @version 1
def test_apply_plan_backs_up_the_original_bytes(tmp_path: Path) -> None:
    """The single most consequential write in the tool, so it is tested directly
    rather than through the command. `os.replace` guarantees the target is never
    half-written; it guarantees NOTHING about the content being right, and the
    content has been through a full parse → mutate → re-serialise round-trip. A
    defect anywhere in that round-trip destroys the file perfectly atomically.

    The assertion that matters is which bytes the `.bak` holds: a backup taken
    AFTER the swap would exist, be the same size, and be worthless."""
    target = tmp_path / REPO_CONFIG_NAME
    original = (
        '{\n  "mcpServers": {\n    "entropic": {"command": "entropic-mcp"}\n  },\n'
        '  "note": "hand written, irreplaceable"\n}\n'
    )
    target.write_text(original, encoding="utf-8")
    apply_plan(plan_merge(target, _expected_entry()))
    backup = target.with_name(target.name + BACKUP_SUFFIX)
    assert backup.is_file(), "an existing target must be backed up before it is replaced"
    assert backup.read_text(encoding="utf-8") == original, "the backup must hold the ORIGINAL bytes"
    assert json.loads(target.read_text(encoding="utf-8"))[SERVERS_KEY][MCP_ENTRY_NAME] == (
        _expected_entry()
    )
    assert not target.with_name(target.name + ".clew.tmp").exists(), (
        "the atomic-swap temp file must not survive"
    )


## @brief Creating a file leaves no backup — there was nothing to lose.
## @param tmp_path Per-test temporary directory.
## @version 1
def test_no_backup_is_left_when_the_file_is_created(tmp_path: Path) -> None:
    """A stray `.bak` next to a file that never existed is misleading rather than
    protective — it invites the reader to believe something was overwritten."""
    target = tmp_path / REPO_CONFIG_NAME
    apply_plan(plan_merge(target, _expected_entry()))
    assert target.is_file()
    assert not target.with_name(target.name + BACKUP_SUFFIX).exists()


## @brief Malformed JSON is refused, and the file is not rewritten or truncated.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_malformed_json_is_refused_and_left_alone(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The only way to "handle" an unparseable config is to overwrite it, which
    destroys entries the user wrote by hand. A half-finished edit is the normal
    reason a config does not parse, so this is a state a real user is in — and the
    file has to still be there afterwards for them to finish fixing it."""
    del stub_env
    target = repo / REPO_CONFIG_NAME
    broken = '{\n  "mcpServers": {\n    "entropic": {"command": "entropic-mcp",\n'
    target.write_text(broken, encoding="utf-8")
    code, out = _run([], repo, capsys)
    assert code == 1
    assert target.read_text(encoding="utf-8") == broken, "a malformed file must not be rewritten"
    assert str(target) in out, "the refusal must name the file to fix"
    assert not target.with_name(target.name + BACKUP_SUFFIX).exists()


## @brief A non-object `mcpServers` is refused rather than replaced.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_non_object_servers_key_is_refused(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Parses as JSON, so `load_document` accepts it, and the merge would happily
    replace a list with a dict — silently discarding whatever the user meant."""
    del stub_env
    target = repo / REPO_CONFIG_NAME
    original = '{"mcpServers": ["entropic"]}\n'
    target.write_text(original, encoding="utf-8")
    code, out = _run([], repo, capsys)
    assert code == 1
    assert target.read_text(encoding="utf-8") == original
    assert SERVERS_KEY in out


## @brief A JSON document that is not an object is refused.
## @param tmp_path Per-test temporary directory.
## @version 1
def test_non_object_document_is_refused(tmp_path: Path) -> None:
    """`json.loads("[]")` succeeds; `document.get(...)` on a list does not."""
    target = tmp_path / REPO_CONFIG_NAME
    target.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        plan_merge(target, _expected_entry())


## @brief `--dry-run` prints the ENTRY it would write, and writes nothing at all.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 2
def test_dry_run_writes_nothing(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SPEC CHANGED BY gh#27, deliberately. This used to assert the printed JSON was
    the whole re-serialised document (`plan.text`), which is the defect: on
    `--scope global` that document is the user's entire `~/.claude.json`. The dry run
    now prints the entry under review, so the assertion parses that instead.

    Nothing reviewable was lost here even though this is the `create` case — the
    document the old version printed was this entry wrapped in `mcpServers` and
    nothing else."""
    del stub_env
    code, out = _run(["--dry-run"], repo, capsys)
    assert code == 0, out
    assert not (repo / REPO_CONFIG_NAME).exists(), "--dry-run must not create the file"
    assert json.loads(_printed_json(out)) == _expected_entry()


## @brief `--dry-run` over an existing config leaves its bytes alone.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_dry_run_over_an_existing_file_changes_nothing(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The riskier half of the dry run: here there IS something to destroy."""
    del stub_env
    target = repo / REPO_CONFIG_NAME
    original = json.dumps({SERVERS_KEY: {"entropic": {"command": "entropic-mcp"}}}, indent=2) + "\n"
    target.write_text(original, encoding="utf-8")
    code, out = _run(["--dry-run"], repo, capsys)
    assert code == 0, out
    assert target.read_text(encoding="utf-8") == original
    assert not target.with_name(target.name + BACKUP_SUFFIX).exists()


# ─── gh#27: --dry-run must not publish the document it merges into ────────────


## @brief `add`: dry-run over a live-like document prints the entry, not the document.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param global_home Isolated Claude config directory.
## @param capsys Output capture.
## @version 1
def test_dry_run_add_shows_the_entry_and_not_the_user_document(
    repo: Path,
    stub_env: Path,
    global_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run against USER scope on purpose, because that is the file with something to
    disclose. The document already holds two other servers, so the merge is an `add`
    and the old code path printed all of it."""
    del stub_env
    target = global_home / ".claude.json"
    target.write_text(json.dumps(_disclosure_document(), indent=2) + "\n", encoding="utf-8")
    code, out = _run(["--dry-run", "--scope", INIT_SCOPE_GLOBAL], repo, capsys)
    assert code == 0, out
    _assert_entry_only(out)
    assert json.loads(_printed_json(out)) == _expected_entry()


## @brief `unchanged`: dry-run says so in one line and prints no payload.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param global_home Isolated Claude config directory.
## @param capsys Output capture.
## @version 1
def test_dry_run_unchanged_prints_no_document(
    repo: Path,
    stub_env: Path,
    global_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """THE CASE THAT PRODUCED gh#27. The entry is already registered and identical, so
    the run is a verified no-op — and it still dumped ~150KB of user state. A no-op
    must print no payload at all, not a smaller one."""
    del stub_env
    document = _disclosure_document()
    document[SERVERS_KEY] = {**document[SERVERS_KEY], MCP_ENTRY_NAME: _expected_entry()}
    target = global_home / ".claude.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    code, out = _run(["--dry-run", "--scope", INIT_SCOPE_GLOBAL], repo, capsys)
    assert code == 0, out
    _assert_entry_only(out)
    assert INIT_ACTION_UNCHANGED in out, "the no-op action must be reported"
    assert "{" not in out, "a no-op dry run must print no JSON payload whatsoever"


## @brief `update --force`: dry-run shows the entry-scoped diff and nothing wider.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param global_home Isolated Claude config directory.
## @param capsys Output capture.
## @version 1
def test_dry_run_update_with_force_shows_only_the_entry_diff(
    repo: Path,
    stub_env: Path,
    global_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The useful half of the dry run, which the fix must NOT cost: someone about to
    `--force` over a hand-tuned entry needs to see what changes. They get `plan.diff`,
    which is rendered over the entry alone."""
    del stub_env
    document = _disclosure_document()
    stale = {"type": "stdio", "command": "/old/path/clew-mcp", "args": ["--repo", "/old"]}
    document[SERVERS_KEY] = {**document[SERVERS_KEY], MCP_ENTRY_NAME: stale}
    target = global_home / ".claude.json"
    original = json.dumps(document, indent=2) + "\n"
    target.write_text(original, encoding="utf-8")
    code, out = _run(["--dry-run", "--force", "--scope", INIT_SCOPE_GLOBAL], repo, capsys)
    assert code == 0, out
    _assert_entry_only(out)
    assert "/old/path/clew-mcp" in out, "the diff must show what would be replaced"
    assert "+++ proposed" in out, "the entry-level unified diff must be shown"
    assert target.read_text(encoding="utf-8") == original, "--dry-run must not write"


## @brief `update` without `--force`: the refusal is entry-scoped too.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param global_home Isolated Claude config directory.
## @param capsys Output capture.
## @version 1
def test_dry_run_update_without_force_refuses_without_dumping(
    repo: Path,
    stub_env: Path,
    global_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A different code path from the three above: `_execute` refuses before `_emit` is
    reached, so this pins the OTHER exit that prints a diff. It was already
    entry-scoped; this stops it regressing to match what `_emit` used to do."""
    del stub_env
    document = _disclosure_document()
    stale = {"type": "stdio", "command": "/old/path/clew-mcp", "args": []}
    document[SERVERS_KEY] = {**document[SERVERS_KEY], MCP_ENTRY_NAME: stale}
    target = global_home / ".claude.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    code, out = _run(["--dry-run", "--scope", INIT_SCOPE_GLOBAL], repo, capsys)
    assert code == 1, out
    _assert_entry_only(out)
    assert "--force" in out, "the refusal must name the override"


## @brief Repo scope shares the code path, so it shares the fix.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_dry_run_repo_scope_is_entry_scoped_as_well(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_emit` takes a plan, not a scope, so `<repo>/.mcp.json` went through the exact
    same dump. The symptom is invisible there only because the file is small — which is
    a property of the FILE, not of the code, and the next `.mcp.json` this runs against
    may not be small."""
    del stub_env
    target = repo / REPO_CONFIG_NAME
    target.write_text(json.dumps(_disclosure_document(), indent=2) + "\n", encoding="utf-8")
    code, out = _run(["--dry-run"], repo, capsys)
    assert code == 0, out
    _assert_entry_only(out)
    assert json.loads(_printed_json(out)) == _expected_entry()


## @brief A file's own indentation survives the merge.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_existing_indentation_is_preserved(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A config the user maintains by hand must not be reformatted to register a
    server: a diff that is 90% whitespace hides the one line that matters."""
    del stub_env
    target = repo / REPO_CONFIG_NAME
    target.write_text(
        json.dumps({SERVERS_KEY: {"entropic": {"command": "entropic-mcp"}}}, indent=4) + "\n",
        encoding="utf-8",
    )
    code, out = _run([], repo, capsys)
    assert code == 0, out
    text = target.read_text(encoding="utf-8")
    assert '\n    "mcpServers"' in text, "4-space indentation must be preserved"
    assert '\n  "mcpServers"' not in text, f"reformatted to {DEFAULT_INDENT} spaces"


## @brief `plan_merge` classifies all four merge actions.
## @param tmp_path Per-test temporary directory.
## @version 1
def test_plan_merge_classifies_every_action(tmp_path: Path) -> None:
    """The action drives the exit path — `unchanged` skips the write entirely and
    `update` is the only one the conflict rule gates — so a misclassification is
    either a silent overwrite or a refusal to do anything."""
    target = tmp_path / REPO_CONFIG_NAME
    entry = _expected_entry()
    assert plan_merge(target, entry).action == INIT_ACTION_CREATE
    target.write_text(json.dumps({SERVERS_KEY: {"entropic": {}}}) + "\n", encoding="utf-8")
    assert plan_merge(target, entry).action == INIT_ACTION_ADD
    target.write_text(json.dumps({SERVERS_KEY: {MCP_ENTRY_NAME: entry}}) + "\n", encoding="utf-8")
    assert plan_merge(target, entry).action == INIT_ACTION_UNCHANGED
    other = {**entry, "command": "something-else"}
    target.write_text(json.dumps({SERVERS_KEY: {MCP_ENTRY_NAME: other}}) + "\n", encoding="utf-8")
    plan = plan_merge(target, entry)
    assert plan.action == INIT_ACTION_UPDATE
    assert "something-else" in plan.diff


## @brief A realistic multi-key document round-trips with one key changed.
## @param tmp_path Per-test temporary directory.
## @version 1
def test_live_like_document_round_trips_with_only_servers_changed(tmp_path: Path) -> None:
    """Shaped like the real user-scope file, which is the one this tool can do
    irreversible damage to. Every other top-level key must come back deep-equal
    AND in its original position — `mcpServers` sits in the middle here on purpose,
    because a merge that rebuilt the document would move it to the end."""
    target = tmp_path / "claude-like.json"
    target.write_text(json.dumps(LIVE_LIKE_DOCUMENT, indent=2) + "\n", encoding="utf-8")
    entry = _expected_entry()
    apply_plan(plan_merge(target, entry))
    after = json.loads(target.read_text(encoding="utf-8"))
    assert list(after) == list(LIVE_LIKE_DOCUMENT), "top-level key ORDER must be preserved"
    for key, value in LIVE_LIKE_DOCUMENT.items():
        if key != SERVERS_KEY:
            assert after[key] == value, f"unrelated key {key} was altered"
    assert list(after[SERVERS_KEY]) == ["entropic", "other-tool", MCP_ENTRY_NAME]
    assert after[SERVERS_KEY][MCP_ENTRY_NAME] == entry
    assert after[SERVERS_KEY]["entropic"] == LIVE_LIKE_DOCUMENT[SERVERS_KEY]["entropic"]


# ─── global scope, and the isolation that makes testing it safe ──────────────


## @brief The user-scope target resolves inside pytest's temp tree, never at home.
## @param tmp_path_factory pytest's session temp-directory factory.
## @version 1
def test_the_global_config_path_is_inside_the_pytest_tmp_tree(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The safety gate for this whole module, asserted rather than assumed.

    `conftest.py`'s autouse fixture points `CLAUDE_CONFIG_DIR` at a throwaway
    directory; this proves the fixture actually reaches the function that
    `apply_plan` writes to. A test that CAN touch `~/.claude.json` is unacceptable
    even while it happens to pass, because the failure is unrecoverable."""
    resolved = global_config_path()
    assert resolved.is_relative_to(tmp_path_factory.getbasetemp())
    assert resolved != Path.home() / ".claude.json"
    assert claude_state_dir().is_relative_to(tmp_path_factory.getbasetemp())


## @brief Global scope writes top-level `mcpServers` and preserves the rest.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param global_home Isolated Claude config directory.
## @param capsys Output capture.
## @version 1
def test_global_scope_preserves_the_user_state_document(
    repo: Path,
    stub_env: Path,
    global_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The stakes case, run against a stand-in for the real file.

    `args == []` is no longer a SCOPE asymmetry — both scopes are unpinned now — but it
    is still worth pinning here, because a user-scope config follows the user between
    projects and a `--repo` of any kind in it would freeze every session onto one
    repository."""
    del stub_env
    target = global_home / ".claude.json"
    target.write_text(json.dumps(LIVE_LIKE_DOCUMENT, indent=2) + "\n", encoding="utf-8")
    code, out = _run(["--scope", INIT_SCOPE_GLOBAL], repo, capsys)
    assert code == 0, out
    after = json.loads(target.read_text(encoding="utf-8"))
    assert list(after) == list(LIVE_LIKE_DOCUMENT)
    assert after["userID"] == LIVE_LIKE_DOCUMENT["userID"]
    assert after["projects"] == LIVE_LIKE_DOCUMENT["projects"]
    assert after[SERVERS_KEY][MCP_ENTRY_NAME] == _expected_entry()
    assert after[SERVERS_KEY][MCP_ENTRY_NAME]["args"] == [], "user scope must stay dynamic"
    assert not (repo / REPO_CONFIG_NAME).exists(), "global scope must not touch the repo"


## @brief `config_path` selects the file by scope.
## @param repo Target repo.
## @param global_home Isolated Claude config directory.
## @version 1
def test_config_path_selects_by_scope(repo: Path, global_home: Path) -> None:
    """@brief Each scope resolves to its own documented file.

    @param repo Target repo.
    @param global_home Isolated Claude config directory.
    @version 1
    """
    assert config_path(INIT_SCOPE_REPO, repo) == repo / REPO_CONFIG_NAME
    assert config_path(INIT_SCOPE_GLOBAL, repo) == global_home / ".claude.json"


## @brief With no declaration and no evidence, global scope refuses and creates nothing.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param tmp_path Per-test temporary directory.
## @param monkeypatch pytest's attribute/env patcher.
## @param capsys Output capture.
## @version 1
def test_global_scope_refuses_without_evidence(
    repo: Path,
    stub_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The ONE test that unsets `CLAUDE_CONFIG_DIR`, so it patches `Path.home` in
    the same breath and asserts the resolved path is under tmp BEFORE running
    anything — with the variable gone, an unpatched `Path.home` would point the
    write at the developer's real config.

    The behaviour under test: writing a config to a location that was GUESSED is
    worse than writing none, so with no evidence of a Claude Code install the
    command refuses and names every place it looked."""
    del stub_env
    fake_home = tmp_path / "empty-home"
    fake_home.mkdir()
    monkeypatch.delenv(CLAUDE_CONFIG_DIR_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    assert global_config_path().is_relative_to(tmp_path), "precondition: the write target is in tmp"
    assert not global_config_available()
    code, out = _run(["--scope", INIT_SCOPE_GLOBAL], repo, capsys)
    assert code == 1
    assert not (fake_home / ".claude.json").exists(), "nothing may be created on a refusal"
    assert str(fake_home / ".claude.json") in out
    assert CLAUDE_CONFIG_DIR_ENV in out, "the refusal must name the override that fixes it"
    assert INIT_SCOPE_REPO in out, "and the scope that needs no evidence"


## @brief The state directory alone evidences an install.
## @param tmp_path Per-test temporary directory.
## @param monkeypatch pytest's attribute/env patcher.
## @version 1
def test_state_directory_alone_is_sufficient_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user who installed Claude Code but has not accumulated a config yet is a
    real state, and refusing them would be refusing the very case `init` is for."""
    fake_home = tmp_path / "fresh-home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.delenv(CLAUDE_CONFIG_DIR_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    assert global_config_path() == fake_home / ".claude.json"
    assert global_config_available()


## @brief A declared `CLAUDE_CONFIG_DIR` relocates both the file and the state dir.
## @param tmp_path Per-test temporary directory.
## @param monkeypatch pytest's env patcher.
## @version 1
def test_claude_config_dir_relocates_both_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both, and the state directory is that directory ITSELF rather than a
    `.claude` child of it — the asymmetry against the default layout (where the
    file and the state directory are siblings) is exactly what an assumption gets
    wrong, and it is why this project's rule is to read declarations."""
    declared = tmp_path / "elsewhere"
    monkeypatch.setenv(CLAUDE_CONFIG_DIR_ENV, str(declared))
    assert global_config_path() == declared / ".claude.json"
    assert claude_state_dir() == declared
    assert global_config_available(), "a declaration IS the evidence"


# ─── command resolution ──────────────────────────────────────────────────────


## @brief The bare console-script name is used when PATH resolves it.
## @param tmp_path Per-test temporary directory.
## @param repo Target repo.
## @version 1
def test_bare_console_script_when_on_path(tmp_path: Path, repo: Path) -> None:
    """The `pip install clew` case, and the right answer for it: the bare
    name is the interface the package publishes, it survives the checkout moving,
    and it is what every other installed MCP server looks like in a config."""
    found = tmp_path / "bin" / CONSOLE_SCRIPT
    found.parent.mkdir()
    found.touch()
    resolution = resolve_server_command(
        repo, INIT_SCOPE_REPO, which=lambda _cmd: str(found), bindir=tmp_path / "bin"
    )
    assert resolution.command == CONSOLE_SCRIPT
    assert resolution.portable


## @brief A script inside the repo is recorded repo-relative.
## @param repo Target repo.
## @version 1
def test_repo_relative_when_the_script_lives_inside_the_repo(repo: Path) -> None:
    """The developer-checkout case: `.venv/bin/clew-mcp` is real and
    usable but invisible to `which` unless the venv is activated. Relative keeps
    the committed config portable across clones of the same repo."""
    script = repo / ".venv" / "bin" / CONSOLE_SCRIPT
    script.parent.mkdir(parents=True)
    script.touch()
    resolution = resolve_server_command(
        repo, INIT_SCOPE_REPO, which=lambda _cmd: None, bindir=script.parent
    )
    assert resolution.command == f".venv/bin/{CONSOLE_SCRIPT}"
    assert resolution.portable


## @brief Off PATH and outside the repo yields an absolute path, flagged.
## @param tmp_path Per-test temporary directory.
## @param repo Target repo.
## @version 1
def test_absolute_path_is_used_and_flagged_non_portable(tmp_path: Path, repo: Path) -> None:
    """A bare name the launching shell cannot resolve produces a server that
    silently never starts, which is strictly worse than a machine-specific path.
    So the path is written — and reported as non-portable rather than chosen
    quietly on the user's behalf."""
    script = tmp_path / "outside" / CONSOLE_SCRIPT
    script.parent.mkdir()
    script.touch()
    resolution = resolve_server_command(
        repo, INIT_SCOPE_REPO, which=lambda _cmd: None, bindir=script.parent
    )
    assert resolution.command == str(script)
    assert not resolution.portable
    assert "not on PATH" in resolution.origin


## @brief Global scope never records a relative command.
## @param repo Target repo.
## @version 1
def test_global_scope_never_uses_a_relative_command(repo: Path) -> None:
    """A user-scope config loads from every directory the user works in, so a
    relative command there resolves against whatever the cwd happens to be."""
    script = repo / ".venv" / "bin" / CONSOLE_SCRIPT
    script.parent.mkdir(parents=True)
    script.touch()
    resolution = resolve_server_command(
        repo, INIT_SCOPE_GLOBAL, which=lambda _cmd: None, bindir=script.parent
    )
    assert resolution.command == str(script)
    assert Path(resolution.command).is_absolute(), "user scope must record an absolute command"


## @brief No script anywhere blocks the write entirely.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_missing_console_script_blocks_the_write(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Writing a `command` that does not exist is the worst outcome available: the
    client reports "failed to connect" with no cause, and the config LOOKS right.
    So this is one of only two blocking checks."""
    (stub_env / CONSOLE_SCRIPT).unlink()
    code, out = _run([], repo, capsys)
    assert code == 1
    assert not (repo / REPO_CONFIG_NAME).exists(), "no config may name a missing command"
    assert CONSOLE_SCRIPT in out


## @brief The entry `init` writes is shaped the way a registration must be.
## @version 2
def test_the_written_entry_is_shaped_like_a_registration() -> None:
    """REPLACES "the dogfood pin", which compared this repo's own committed
    `.mcp.json` against what `init` produces. That file is gone: it registered the
    same server, under the same name, pointed at the same place, as the user-scope
    entry already did — a second registration and no capability.

    What the old test bought was drift detection: if the entry shape changed, it
    failed here on a committed file rather than a year later on a user's machine.
    That guarantee is worth keeping and does not need a checked-in artifact to hold
    it, so it is asserted directly against `server_entry` instead.

    What is genuinely lost with the file: a clone of this repo no longer
    auto-registers the server, and this repo no longer proves by example that
    running `init` on it is a no-op rather than a rewrite that happens to match.
    Both are real and both were judged smaller than carrying a duplicate.

    @brief The generated entry has the shape a client can launch.
    @version 2
    """
    entry = server_entry(CONSOLE_SCRIPT)
    assert entry["command"].endswith(CONSOLE_SCRIPT)
    assert entry["type"] == "stdio", "a local server is launched over stdio"
    ## No `--repo`. The target is DERIVED (from $CLAUDE_PROJECT_DIR, else the
    ## client's roots), so an entry that pinned one would defeat the resolution the
    ## server exists to perform.
    assert entry["args"] == [], "a written entry must not pin a target"


# ─── the doctor ──────────────────────────────────────────────────────────────


## @brief A Doxyfile makes the repo indexable.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @version 1
def test_doxyfile_makes_the_repo_indexable(repo: Path, stub_env: Path) -> None:
    """@brief A repo shipping a Doxyfile reports `indexable: ok` naming it.

    @param repo Target repo.
    @param stub_env Stubbed executables.
    @version 1
    """
    del stub_env
    (repo / "Doxyfile").write_text("INPUT = .\n", encoding="utf-8")
    check = _named(init_command.diagnose(repo, INIT_SCOPE_REPO), init_command.CHECK_INDEXABLE)
    assert check.status == CHECK_OK
    assert "Doxyfile" in check.detail


## @brief A repo with no Doxyfile and no guard scope is INDEXABLE, and says so.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 2
def test_a_repo_with_no_doxyfile_and_no_guard_scope_is_still_indexable(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """THIS TEST USED TO ASSERT THE OPPOSITE AND THE PRODUCT PROVED IT WRONG. It was
    `test_unindexable_repo_warns_but_still_registers`, and it pinned a WARN saying
    "index(action='refresh') will fail until this repo has one".

    MEASURED: a git repo containing one `.c` file, no Doxyfile, no doxygen-guard config and no
    declaration BUILDS — doxygen is synthesized from the whole-repo scope and the function is
    indexed. The premise died with gh#333, which made whole-repo the DEFAULT tier rather than a
    last resort; `is_derived()` stayed true only for SOURCE_DECLARED, so the check fell to a warn
    branch that is wrong every time it fires.

    WHY THIS MATTERS MORE THAN A LABEL: it is the FIRST SCREEN a new consumer sees, on the exact
    configuration they arrive with — no Doxyfile, nothing declared. It told them the tool would
    not work on their repository.

    The suite pinned it, which is why running the product rather than the tests is what found it.

    Warnings must still not spend the exit code, so that half is kept."""
    del stub_env
    code, out = _run([], repo, capsys)
    assert code == 0, out
    assert (repo / REPO_CONFIG_NAME).is_file()
    check = _named(init_command.diagnose(repo, INIT_SCOPE_REPO), init_command.CHECK_INDEXABLE)
    assert check.status == CHECK_OK, (
        "a repo with neither is the ordinary starting state and it indexes fine; warning here "
        "tells a new user their repository is unsupported when it is not"
    )
    assert "whole repository" in check.detail.lower(), "and it must name the route that will run"


## @brief The declaration check reports both states, and points at `propose`.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @version 1
def test_declaration_check_reports_both_states(repo: Path, stub_env: Path) -> None:
    """Absent is the norm rather than a defect, so it is a warning — but a SAID
    one: an empty causal layer on a repo whose accessors the built-in defaults
    cannot see is the commonest "this database is useless" report, and `propose`
    is the answer."""
    del stub_env
    absent = _named(init_command.diagnose(repo, INIT_SCOPE_REPO), init_command.CHECK_DECLARATION)
    assert absent.status == CHECK_WARN
    assert "propose" in absent.detail
    (repo / ".clew.yaml").write_text("shared_key_patterns: []\n", encoding="utf-8")
    present = _named(init_command.diagnose(repo, INIT_SCOPE_REPO), init_command.CHECK_DECLARATION)
    assert present.status == CHECK_OK
    assert ".clew.yaml" in present.detail


## @brief Missing doxygen fails the run but still registers the server.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_missing_doxygen_fails_but_still_registers(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """doxygen is a SUBPROCESS dependency, invisible to pip, so nothing else in
    the install path notices it is gone — the first build does. The fix is a
    package install, not a config edit, so withholding the registration would only
    make the user run `init` twice."""
    (stub_env / "doxygen").unlink()
    code, out = _run([], repo, capsys)
    assert code == 1, "a missing doxygen is a real failure and must be reported as one"
    assert (repo / REPO_CONFIG_NAME).is_file(), "but the registration still lands"
    assert json.loads((repo / REPO_CONFIG_NAME).read_text(encoding="utf-8"))[SERVERS_KEY]
    assert "doxygen is not on PATH" in out


## @brief The SDK check passes on an environment whose server can actually start.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_mcp_sdk_check_passes_when_the_server_can_be_built(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE TEST THAT WAS MISSING, and its absence shipped a broken install path.

    `_check_mcp_sdk` had a test for its FAIL path and none for its OK path, so the
    whole suite stayed green while `init` hard-failed every environment holding the
    only SDK version a fresh `pip install` resolves. The probe named
    `mcp.server.fastmcp` — deleted in 2.x — and described it as "the server's own
    import line", which stopped being true when `_sdk` took over that import.

    So this asserts against the real environment rather than a stub: if
    `build_server()` works here, the doctor must say so. A check that disagrees with
    the thing it checks is the defect, whichever way it disagrees.
    """
    del stub_env
    from clew.mcp_server.server import build_server

    build_server()  # the ground truth: the server constructs under this SDK
    code, out = _run([], repo, capsys)
    assert "[fail] mcp-sdk" not in out, (
        f"the server builds under this SDK, so the doctor must not fail it:\n{out}"
    )
    assert code == 0, f"a working environment must exit clean:\n{out}"


## @brief A broken MCP SDK fails the run but still registers the server.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param monkeypatch pytest's attribute patcher.
## @param capsys Output capture.
## @version 2
def test_broken_mcp_sdk_fails_but_still_registers(
    repo: Path,
    stub_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Breaks the IMPORT, not a name lookup, because the check now performs the
    server's own import rather than probing a string that stands in for it.

    `sys.modules[name] = None` is the documented way to make a subsequent
    `from name import ...` raise: CPython treats a None entry as a poisoned module
    and raises ImportError rather than re-importing. That reaches the real failure
    path without needing a broken interpreter.
    """
    del stub_env
    monkeypatch.setitem(sys.modules, "clew.mcp_server._sdk", None)
    code, out = _run([], repo, capsys)
    assert code == 1
    assert (repo / REPO_CONFIG_NAME).is_file(), "the registration still lands"
    assert "SDK import failed" in out


## @brief Every check is printed even on a run that refuses to write.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @param capsys Output capture.
## @version 1
def test_every_check_prints_before_a_refusal(
    repo: Path, stub_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """On a refusing run the REPORT is the product. A user whose doxygen is also
    missing needs to learn that on the same run that told them the entry
    conflicts, not one re-run later."""
    (stub_env / CONSOLE_SCRIPT).unlink()
    _code, out = _run([], repo, capsys)
    for name in (
        init_command.CHECK_CLIENT_CONFIG,
        init_command.CHECK_SERVER_COMMAND,
        init_command.CHECK_MCP_SDK,
        init_command.CHECK_DOXYGEN,
        init_command.CHECK_INDEXABLE,
        init_command.CHECK_DECLARATION,
    ):
        assert name in out, f"the {name} check must be reported even on a refusal"


## @brief Only the two write-invalidating checks are blocking.
## @version 1
def test_blocking_checks_are_only_the_write_invalidating_ones() -> None:
    """Pinned because the set is the whole three-tier design in one constant.
    Adding `doxygen` here would make a missing binary withhold the registration —
    the "run it twice" outcome the tiers exist to avoid — and removing
    `server-command` would let a config name a command that does not exist."""
    assert init_command.BLOCKING_CHECKS == frozenset(
        {init_command.CHECK_CLIENT_CONFIG, init_command.CHECK_SERVER_COMMAND}
    )
    assert init_command.CHECK_DOXYGEN not in init_command.BLOCKING_CHECKS
    assert init_command.CHECK_MCP_SDK not in init_command.BLOCKING_CHECKS
    assert init_command.CHECK_DECLARATION not in init_command.BLOCKING_CHECKS, (
        "an undeclared repo is the ordinary starting state and must never withhold the registration"
    )


## @brief A failed check that is not blocking still exits non-zero.
## @param repo Target repo.
## @param stub_env Stubbed executables.
## @version 1
def test_check_statuses_come_from_the_vocabulary(repo: Path, stub_env: Path) -> None:
    """Every status the doctor emits has to be a registered `check_status` value,
    or the report's own legend (printed from `CHECK_STATUS.means`) describes
    something else."""
    del stub_env
    for check in init_command.diagnose(repo, INIT_SCOPE_REPO):
        assert check.status in (CHECK_OK, CHECK_WARN, CHECK_FAIL)
        assert check.detail, f"{check.name} reported no evidence"


# ─── CLI wiring ──────────────────────────────────────────────────────────────


## @brief The dispatch word and the command's own name are the same string.
## @version 1
def test_cli_command_word_matches_the_command() -> None:
    """`cli.py` spells the word rather than importing the module, so that a build
    invocation never drags `init`'s import graph in. That duplication is only safe
    while something pins the two together."""
    assert cli.INIT_COMMAND == init_command.COMMAND == "init"


## @brief The init import stays inside `main()`, not at module scope.
## @version 1
def test_init_is_imported_lazily_inside_main() -> None:
    """`init` must stay runnable on an install missing the pipeline's heavier
    optional dependencies — it is the command that DIAGNOSES a broken install, so
    it cannot be the command that needs a whole one to start."""
    import inspect

    source = inspect.getsource(cli.main)
    assert "from .init_command import" in source
    assert "from .init_command import" not in inspect.getsource(cli).split("def main(")[0]


## @brief Parser defaults are repo scope, the cwd, no force, no yes, no dry run.
## @version 2
def test_parser_defaults() -> None:
    """`--force`, `--yes` and `--dry-run` default off in the safe direction: nothing
    is replaced, nothing is written to a curated file unasked, and nothing is
    hidden."""
    args = init_command.build_parser().parse_args([])
    assert args.scope == INIT_SCOPE_REPO
    assert args.repo_root == "."
    assert args.force is False
    assert args.dry_run is False


## @brief Find one named check in a diagnostic report.
## @param checks The report.
## @param name Check name to select.
## @return The matching check.
## @version 1
def _named(checks: list[init_command.Check], name: str) -> init_command.Check:
    """@brief Select one check from a report by name.

    @param checks The report.
    @param name Check name to select.
    @return The matching check.
    @version 1
    """
    match = [c for c in checks if c.name == name]
    assert len(match) == 1, f"expected exactly one {name} check, got {len(match)}"
    return match[0]
