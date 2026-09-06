# SPDX-License-Identifier: MIT
"""WHAT THE SERVER ACTUALLY SERVES, asked over real MCP stdio rather than by import.

Every other check of the tool surface in this repo reaches it by importing
`build_server()`. That answers "were the decorators evaluated", which is not the
same question as "does a client see them", and gh#14 is exactly the gap between
the two: `python -m clew.mcp_server.server` started, spoke no MCP, exited 0, and
offered a client nothing — while the imported module looked perfectly healthy.

So this speaks the protocol: `initialize`, `notifications/initialized`,
`tools/list`, and counts what comes back. It is the only measurement here that
can fail the way a user fails.

    .venv/bin/python scripts/mcp_tools_probe.py

@brief Count the tools a server command serves over MCP stdio.
@version 1
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

## Long enough for an interpreter start plus the pipeline imports the server does at
## startup, short enough that a hung server fails the suite rather than holding it.
_SETTLE_SECONDS = 2.5
_STEP_SECONDS = 0.4


## @brief Ask one server command for its tool list over stdio.
## @param cmd The argv to launch, e.g. ['clew-mcp'] or [sys.executable, '-m', 'pkg'].
## @param cwd Working directory for the child.
## @return Sorted tool names; empty when the server offered none or never answered.
## @version 1
def served_tools(cmd: list[str], cwd: Path | str | None = None) -> list[str]:
    """Returns [] for BOTH "answered with no tools" and "never answered", deliberately:
    from a client's seat those are the same outcome, and gh#14's whole point is that the
    second was indistinguishable from the first. A caller wanting to tell them apart
    should compare against a known-good command, which is what the tests do.

    @brief The tool names a server command serves.
    @return Sorted names, or [].
    @version 1
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    handshake = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp_tools_probe", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    try:
        for message in handshake:
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
            time.sleep(_STEP_SECONDS)
        time.sleep(_SETTLE_SECONDS)
    except (BrokenPipeError, OSError):
        ## The server exited before the handshake finished — gh#14's shape exactly.
        pass
    proc.terminate()
    try:
        out, _err = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _err = proc.communicate()
    for line in out.splitlines():
        try:
            payload = json.loads(line)
        except (ValueError, TypeError):
            continue
        if payload.get("id") == 2 and "result" in payload:
            return sorted(t["name"] for t in payload["result"].get("tools", []))
    return []


## @brief Report the tool list for every way this package can be started.
## @return Process exit code: 0 when every spelling serves the same tools.
## @version 1
def main() -> int:
    """@brief Compare the served tool set across entry points.
    @return 0 when they agree, 1 otherwise.
    @version 1
    """
    venv_script = REPO / ".venv" / "bin" / "clew-mcp"
    console = str(venv_script) if venv_script.exists() else "clew-mcp"
    spellings = {
        "console script": [console],
        "-m clew.mcp_server.server": [sys.executable, "-m", "clew.mcp_server.server"],
        "-m clew.mcp_server": [sys.executable, "-m", "clew.mcp_server"],
    }
    results = {label: served_tools(cmd, cwd=REPO) for label, cmd in spellings.items()}
    for label, tools in results.items():
        print(f"{label:<28} tools={len(tools):<3} {tools}")
    distinct = {tuple(t) for t in results.values()}
    if len(distinct) != 1:
        print("\nDISAGREEMENT: these spellings do not serve the same tools (gh#14).")
        return 1
    print("\nevery entry point serves the same tools")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
