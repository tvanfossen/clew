# SPDX-License-Identifier: MIT
"""The gh#48 reporter's own probe, over real JSON-RPC, as a test.

The issue was found with a stdlib script that starts `clew-mcp` four ways and issues one query
each. Against a split repository whose sub-indexes were built but not registered, ALL FOUR
REFUSED. Every test written for the fix so far calls the Python methods directly, which proves
the routing and proves nothing about the process a client actually speaks to: the launch
arguments, the environment, the handshake and the tool dispatch are all outside those calls.

So this drives the server as a subprocess, one line of JSON per message, in the reporter's four
modes:

    --repo, target supplied              was REFUSED
    --repo, target OMITTED               was REFUSED
    no --repo, CLAUDE_PROJECT_DIR set    was REFUSED
    no --repo, cwd only                  REFUSED, correctly — no source supplies a target

The fourth is the one that SHOULD refuse, and its message is asserted too, because "answers
three ways and says why on the fourth" is the whole claim.

@brief End-to-end stdio probe of the four launch modes on a split repository.
@version 1
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="the MCP SDK is a REQUIRED dependency")

from clew.mcp_server.state import PROJECT_DIR_ENV, STATE_HOME_ENV, target_for
from clew.scope import FIRST_PARTY_INDEX

pytestmark = pytest.mark.integration

## How long any one exchange may take before the probe gives up. Generous: the server imports the
## SDK and the query layer on start. A hang must still fail rather than wait for the suite's own
## timeout, which is the failure mode the reporter's script was written around.
_TIMEOUT = 60


## @brief A split repository whose first-party index is built but not registered.
## @param tmp_path Pytest temp dir.
## @param rich_db The fixture index to install as first-party.
## @return (repository root, state home).
## @version 1
def _probe_repo(tmp_path: Path, rich_db: Path) -> tuple[Path, Path]:
    """NOT REGISTERED, which is the reporter's state: the databases were on disk and the
    answering process had no record of them.

    @brief Build the probe fixture.
    @return (repo, state home).
    @version 1
    """
    repo = tmp_path / "split"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    for name in ("tinyfsm", "libIoT"):
        nested = repo / "deps" / name
        nested.mkdir(parents=True)
        (nested / ".git").write_text(f"gitdir: ../../.git/modules/{name}\n", encoding="utf-8")
    home = tmp_path / "state"
    target = target_for(repo, home, FIRST_PARTY_INDEX)
    Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target.db_path).write_bytes(rich_db.read_bytes())
    return repo.resolve(), home


## @brief Run one probe: start the server, handshake, call `dossier`, return the reply.
## @param repo The repository to ask about.
## @param home The state home holding the built index.
## @param args Extra command-line arguments (`--repo <path>`, or none).
## @param env_repo Value for $CLAUDE_PROJECT_DIR, or None to leave it unset.
## @param target The `target` argument to pass to the tool call, or None to omit it.
## @return The tool result payload as the client would see it.
## @version 1
def _probe(
    repo: Path, home: Path, args: list[str], env_repo: Path | None, target: Path | None
) -> dict:
    """ONE JSON OBJECT PER LINE, which is the stdio transport's framing — hand-rolled rather
    than driven through the SDK client on purpose: the reporter's probe was stdlib-only, and a
    test that used the SDK's own client to check the SDK's own server would share any
    assumption the two make about each other.

    @brief Drive one server process through initialize and one tool call.
    @return The parsed tool result.
    @version 1
    """
    env = {**os.environ, STATE_HOME_ENV: str(home)}
    env.pop(PROJECT_DIR_ENV, None)
    if env_repo is not None:
        env[PROJECT_DIR_ENV] = str(env_repo)
    proc = subprocess.Popen(
        [sys.executable, "-m", "clew.mcp_server", *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=repo,
        env=env,
    )
    arguments: dict[str, object] = {"subject": "sensor_poll"}
    if target is not None:
        arguments["target"] = str(target)
    lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=_pump, args=(proc, lines), daemon=True)
    reader.start()
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "gh48-probe", "version": "1"},
                },
            },
        )
        _await_reply(lines, 1)
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "dossier", "arguments": arguments},
            },
        )
        return _await_reply(lines, 2)
    finally:
        ## STDIN STAYS OPEN UNTIL THE ANSWER ARRIVES. Closing it is what a client does to END a
        ## session, and the first version of this probe wrote all three messages and closed —
        ## the server shut the transport down and never answered the call, which reads exactly
        ## like the refusal this test exists to detect.
        proc.kill()
        proc.wait(timeout=_TIMEOUT)


## @brief Read the server's stdout into a queue until it closes.
## @param proc The server process.
## @param lines Queue to push each line onto.
## @return None.
## @version 1
def _pump(proc: subprocess.Popen, lines: queue.Queue) -> None:
    """@brief Pump stdout lines onto a queue. @version 1"""
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line)


## @brief Write one JSON-RPC message.
## @param proc The server process.
## @param message The message to send.
## @return None.
## @version 1
def _send(proc: subprocess.Popen, message: dict) -> None:
    """@brief Send one newline-framed JSON-RPC message. @version 1"""
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


## @brief Wait for the reply carrying one request id.
## @param lines Queue of server output lines.
## @param wanted The request id awaited.
## @return The parsed reply.
## @version 1
def _await_reply(lines: queue.Queue, wanted: int) -> dict:
    """BOUNDED, because a hang here is indistinguishable from a slow start and would be paid at
    the suite's own timeout rather than as a readable failure.

    @brief Read until the reply with this id arrives.
    @return The reply.
    @version 1
    """
    deadline = time.monotonic() + _TIMEOUT
    seen: list[str] = []
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=deadline - time.monotonic())
        except queue.Empty:
            break
        seen.append(line)
        if not line.strip().startswith("{"):
            continue
        message = json.loads(line)
        if message.get("id") == wanted:
            return message
    raise AssertionError(f"no reply to request {wanted}; server said: {''.join(seen)!r}")


## @brief What one reply says: the payload dict, or the error text.
## @param reply The JSON-RPC reply.
## @return (payload or {}, error text or "").
## @version 1
def _read(reply: dict) -> tuple[dict, str]:
    """A refusal arrives as `isError` with the message in the content, not as a transport
    error — see `_answering_with_refresh`, which converts it to the SDK's own ToolError for
    exactly that reason.

    @brief Split a reply into its payload and its refusal text.
    @return (payload, error text).
    @version 1
    """
    result = reply.get("result") or {}
    text = "".join(part.get("text", "") for part in result.get("content") or [])
    if result.get("isError") or reply.get("error"):
        return {}, text or json.dumps(reply.get("error") or {})
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and structured:
        return structured, ""
    return (json.loads(text) if text.strip().startswith("{") else {}), ""


def test_the_three_target_bearing_modes_answer_from_first_party(
    tmp_path: Path, rich_db: Path
) -> None:
    """THE THREE MODES THAT HAVE A REPOSITORY. Each answers, and each says which part answered:
    a reply that read first-party while looking like a whole-repository answer is the failure
    `Answering` calls this project's most expensive.

    @brief --repo with and without target, and $CLAUDE_PROJECT_DIR, all answer from first-party.
    @version 1
    """
    repo, home = _probe_repo(tmp_path, rich_db)
    modes = {
        "--repo, target supplied": ([f"--repo={repo}"], None, repo),
        "--repo, target omitted": ([f"--repo={repo}"], None, None),
        f"no --repo, ${PROJECT_DIR_ENV} set": ([], repo, None),
    }
    for label, (args, env_repo, target) in modes.items():
        payload, error = _read(_probe(repo, home, args, env_repo, target))
        assert not error, f"{label}: refused — {error}"
        assert payload.get("found") is not False, f"{label}: {payload}"
        assert payload.get("sub_index") == FIRST_PARTY_INDEX, f"{label}: {payload}"
        assert payload.get("target") == str(repo), f"{label}: {payload}"


def test_the_cwd_only_mode_refuses_by_naming_every_source_of_a_target(
    tmp_path: Path, rich_db: Path
) -> None:
    """THE FOURTH MODE, WHICH IS CORRECT TO REFUSE. The working directory is deliberately not a
    source for the default target — a client that supplies neither `--repo` nor the environment
    nor roots has said nothing about which repository it means. What the refusal must do is name
    all three routes plus the per-call argument, so a reader can act without knowing the design.

    @brief With no target source, the refusal names --repo, the environment and target=.
    @version 1
    """
    repo, home = _probe_repo(tmp_path, rich_db)

    payload, error = _read(_probe(repo, home, [], None, None))

    assert not payload, f"a server with no target must not answer: {payload}"
    assert "No default target repository" in error, error
    assert "--repo" in error and PROJECT_DIR_ENV in error and "target=" in error, error
