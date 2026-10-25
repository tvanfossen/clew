# SPDX-License-Identifier: MIT
"""The environment one kconfiglib parse runs inside, and the functions it may call.

kconfiglib takes its configuration from the PROCESS ENVIRONMENT — `srctree` for `source`
resolution, `KCONFIG_FUNCTIONS` for the Python module whose functions a Kconfig may call —
and it has no constructor argument for either. Driving a parse therefore means mutating
`os.environ`, and once that is true the only question left is what the parse gets to see.

Three things were measured against kconfiglib 14.1 during the 1.1.0 security audit, each with
the same root cause — the parse inherited the whole process environment:

  * `$(SENTINEL)` in a `prompt` or `default` EXPANDS from the environment, and the result is
    persisted and served as the repository's own configuration text. For the MCP plugin that
    environment is the editor's: `ANTHROPIC_API_KEY`, `GH_TOKEN`, `AWS_*`, `SSH_AUTH_SOCK`.
  * `$(shell,<command>)` RUNS the command. That is execution, not disclosure, and it needs
    nothing but a `Kconfig` file in the tree.
  * `KCONFIG_FUNCTIONS` names a module kconfiglib imports and whose body therefore runs; its
    DEFAULT is `kconfigfunctions`, a name a repository can ship as a file.

So the parse is given a MINIMAL ENVIRONMENT rather than three separate patches: `srctree` (the
only variable the parse legitimately needs), `PATH` and `HOME` (kept because removing them
breaks nothing a Kconfig does and breaks plenty that Python does), and `KCONFIG_FUNCTIONS`
pointing HERE. Nothing else is inherited, which closes the expansion vector for every variable
rather than for a list of ones we thought of.

Pointing `KCONFIG_FUNCTIONS` at this module does double duty, and that is why it is this
module and not a deletion of the variable: kconfiglib `update()`s its built-in function table
from the named module, so a `shell` entry here REPLACES the built-in one. Using the library's
own documented extension point, rather than reaching into `Kconfig._functions`, means a
kconfiglib upgrade that renames an internal cannot silently reopen the hole — it would fail
loudly, and a test asserts the refusal end to end.

A REFUSAL IS RECORDED, never swallowed. A Zephyr tree legitimately uses `$(shell,…)`, and its
owner must be able to read WHY a default came out empty; an expansion that quietly became ""
is exactly the accepted-but-unread failure this project keeps finding.

@brief The minimal environment and refusing function table for a Kconfig parse.
@version 1
"""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Iterator
from pathlib import Path

from ._common import logger

## PER-THREAD, because the MCP server builds different targets on different threads and a
## shared list would attribute one target's refusals to another's `build_meta`.
_state = threading.local()

## Variables the parse keeps. `srctree` is set per parse; these are the two whose ABSENCE
## breaks ordinary Python rather than anything a Kconfig expresses.
_INHERITED = ("PATH", "HOME")

## The module name kconfiglib must import, which is this one. Written out rather than derived
## from `__name__` so a reader of the forced value can see what it points at.
_FUNCTIONS_MODULE = "clew.kconfig_env"


## @brief Record one refused shell expansion for the current parse.
## @param command The command text the Kconfig asked to run.
## @return None.
## @version 1
## @dg_internal
def _record(command: str) -> None:
    """@brief Append a refusal to this thread's parse record. @version 1"""
    refusals = getattr(_state, "refusals", None)
    if refusals is None:
        ## A parse outside `parse_environment` should not be possible, but a dropped refusal
        ## would be invisible, so it is logged rather than lost.
        logger.warning("kconfig: refused `$(shell,%s)` outside a recorded parse", command)
        return
    refusals.append(command)


## @brief kconfiglib's `$(shell,…)`, refusing instead of running.
## @param _kconf The parsing Kconfig instance (unused).
## @param _name The function name as written (unused).
## @param command The command the Kconfig asked to run.
## @return The empty string, which is what an unset expansion yields.
## @version 1
## @req REQ-DDB-PIPE-014
def refuse_shell(_kconf: object, _name: str, command: str) -> str:
    """RETURNS "" RATHER THAN RAISING. A raise here would fail the whole Kconfig parse, and
    `load_kconfig` already degrades a parse failure to a recorded error with no symbols — so
    refusing by exception would cost every symbol in a tree that uses `$(shell,…)` once. An
    empty expansion costs that one value, and the refusal record says which.

    @brief Refuse a shell expansion, recording it.
    @return "".
    @version 1
    """
    _record(command)
    return ""


## The table kconfiglib `update()`s into its built-ins. The `shell` key is the whole point:
## same name, same arity, refusing implementation.
functions = {"shell": (refuse_shell, 1, 1)}


## @brief Run a kconfiglib parse in a minimal environment, collecting its refusals.
## @param root Absolute repo root kconfiglib resolves `source` paths against.
## @return A context manager yielding the list refused shell commands accumulate into.
## @version 1
## @req REQ-DDB-PIPE-014
@contextlib.contextmanager
def parse_environment(root: Path) -> Iterator[list[str]]:
    """REPLACES the environment for the duration of the parse and restores it in a `finally`,
    because this runs inside a longer pipeline and the MCP server is a long-lived process that
    builds several targets: a leaked `srctree` would silently redirect a later parse.

    The whole mapping is saved and restored rather than the three keys we set. Restoring keys
    is correct only if the set of keys we touch never grows, and the point of this function is
    that it touches ALL of them.

    THREAD SAFETY, STATED PLAINLY: `os.environ` is process-wide, so two concurrent parses on
    two threads would see each other's environment. kconfiglib offers no other route, and the
    build lock the MCP server holds is per-target, so this is a real (if narrow) constraint
    rather than a solved problem — recorded here because a reader will otherwise assume the
    `threading.local` above covers it. It does not; it covers only the refusal record.

    @brief Install the minimal parse environment, yielding the refusal record.
    @return The list of refused shell commands.
    @version 1
    """
    saved = dict(os.environ)
    refusals: list[str] = []
    _state.refusals = refusals
    minimal = {name: saved[name] for name in _INHERITED if name in saved}
    minimal["srctree"] = str(root)
    minimal["KCONFIG_FUNCTIONS"] = _FUNCTIONS_MODULE
    try:
        os.environ.clear()
        os.environ.update(minimal)
        yield refusals
    finally:
        os.environ.clear()
        os.environ.update(saved)
        _state.refusals = None
        if refusals:
            logger.warning(
                "kconfig: refused %d `$(shell,…)` expansion(s) while parsing under %s — a "
                "Kconfig may not run commands during indexing, so each expanded to the empty "
                "string. Refused: %s",
                len(refusals),
                root,
                "; ".join(refusals),
            )
