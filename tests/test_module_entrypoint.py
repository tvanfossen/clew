# SPDX-License-Identifier: MIT
"""Running the server as a MODULE must work or say why (gh#14).

`python -m clew.mcp_server.server` started, registered zero tools, and exited 0
with no error. A user following that path gets a client that connects to a server
offering nothing, which reads as "clew has no tools" rather than "you invoked it
the wrong way".

THE CAUSE IS NOT THE DOUBLE IMPORT, though that warning is what the invocation
prints. `server.py` had no `if __name__ == "__main__"` block at all, so runpy
executed the file top to bottom — defining the tools, calling nothing — and the
process exited before any server existed. The `RuntimeWarning` about
`clew.mcp_server.server` already being in `sys.modules` is a real second problem
riding along: `clew/mcp_server/__init__.py` imports `.server`, so runpy's copy is
a SECOND module object whose decorators register onto a registry nobody serves.

Both are fixed by delegating: the `__main__` block imports the canonical module
and calls ITS `main()`, so the tools that get served are the ones the first import
registered.

@brief Tests for the module-form server entry point.
@version 1
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


##
# @brief The module form runs main() rather than defining and exiting.
# @return None.
# @version 1
def test_the_module_form_actually_runs_the_server_entry_point() -> None:
    """`--help` is the cheap proof that `main()` RAN: argparse only prints a usage line
    if something called it. Before the fix this produced no output at all and exited 0,
    which is indistinguishable from success to anything that does not count tools.

    Asserts the `clew-mcp` prog name specifically, because that is `main()`'s own parser
    and therefore proves the canonical entry point ran — not merely that some argparse
    somewhere did.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "clew.mcp_server.server", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "clew-mcp" in proc.stdout, (
        f"main()'s own parser did not run; got stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "--repo" in proc.stdout


##
# @brief The package form works too, since that is what a user tries next.
# @return None.
# @version 1
def test_the_package_form_runs_the_same_entry_point() -> None:
    """`python -m clew.mcp_server` is the idiomatic spelling and is what someone reaches
    for once the longer one fails. Without a `__main__.py` it raises
    "No module named clew.mcp_server.__main__", so the two module spellings failed in two
    different ways and neither pointed at the console script."""
    proc = subprocess.run(
        [sys.executable, "-m", "clew.mcp_server", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "clew-mcp" in proc.stdout


##
# @brief The served tool set is identical whichever spelling started it.
# @return None.
# @version 1
def test_every_entry_point_serves_the_same_tools() -> None:
    """THE ASSERTION THE ISSUE IS ACTUALLY ABOUT. `--help` proves `main()` ran; it does not
    prove the SERVED registry is the populated one. With the double import the delegating
    fix is what makes those the same object, and nothing but a real handshake can tell.

    Driven over real MCP stdio by `scripts/mcp_tools_probe.py`, which is also the tool that
    measured the defect for the issue.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from mcp_tools_probe import served_tools
    finally:
        sys.path.pop(0)

    ## The venv's script when there is one, else whatever `clew-mcp` PATH resolves to —
    ## CI builds a fresh venv per matrix leg and a hardcoded path would make this test
    ## assert about this machine's layout rather than about the entry points.
    venv_script = REPO / ".venv" / "bin" / "clew-mcp"
    console_cmd = [str(venv_script)] if venv_script.exists() else ["clew-mcp"]
    console = served_tools(console_cmd, cwd=REPO)
    assert console, "premise: the console script serves tools"
    module = served_tools([sys.executable, "-m", "clew.mcp_server.server"], cwd=REPO)
    package = served_tools([sys.executable, "-m", "clew.mcp_server"], cwd=REPO)
    assert module == console, f"module form served {module}, console served {console}"
    assert package == console, f"package form served {package}, console served {console}"
