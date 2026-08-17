# SPDX-License-Identifier: MIT
"""Shared helpers for the clew package.

The Rich Progress factory, the module logger, and the one seam that decides
WHERE pipeline output goes. Kept tiny; if more shared state grows, move those
helpers here in their own modules.

@brief Shared helpers for clew submodules.
@version 2
"""

from __future__ import annotations

import io
import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

logger = logging.getLogger("clew")
console = Console()

## The console pipeline output is rendered to for the duration of ONE call.
##
## A ContextVar rather than a module-level rebind, because a caller silencing its
## own build must not silence anyone else's: a build dispatched to a worker thread
## runs beside a thread that may be writing to the real stdout, and each thread
## carries its own context, so a value set inside the worker is invisible there.
## None means "the process console", which is what a plain CLI build wants.
_render_target: ContextVar[Console | None] = ContextVar("clew_render_target", default=None)


## @brief os.environ + NO_COLOR/TERM=dumb so pipeline subprocesses emit no ANSI.
## @version 2
## @req REQ-DDB-PIPE-006
## @return Copy of os.environ with NO_COLOR=1, TERM=dumb, and CLICOLOR=0 set.
def clean_subprocess_env() -> dict[str, str]:
    """Return a copy of the environment with color/interactive TTY hints forced
    off (NO_COLOR=1, TERM=dumb, CLICOLOR=0). Passed to every pipeline subprocess
    (e.g. doxygen) so captured build output carries no SGR escape sequences.

    @brief Build a color-suppressing environment for pipeline subprocesses.
    @version 2
    """
    env = dict(os.environ)
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    env["CLICOLOR"] = "0"
    return env


## @brief The console every pipeline writer renders to right now.
## @return The console injected by `captured_output`, else the process console.
## @version 1
## @utility
def active_console() -> Console:
    """Read at write time rather than captured at import, so a caller can redirect
    the whole pipeline for one call without swapping `sys.stdout` — which is
    process-global and would take the frames of any other thread with it.

    @brief Resolve the current render target for pipeline output.
    @return The console to write to.
    @version 1
    """
    return _render_target.get() or console


## @brief A log handler that only accepts records raised on the thread that made it.
## @version 1
## @utility
class _OwnThreadHandler(logging.StreamHandler):
    """The render target is context-local, so two concurrent runs cannot see each
    other's bars. A logger is not: it is one object shared by every thread, and a
    handler added to it would collect the other run's records too. Matching on the
    creating thread restores the same isolation for the log half.

    @brief Stream handler scoped to one thread's records.
    @version 1
    """

    ## @brief Bind the handler to a stream and to the creating thread.
    ## @param stream Stream the records are written to.
    ## @version 1
    ## @dg_internal
    def __init__(self, stream: io.StringIO) -> None:
        """@brief Record which thread's output this handler accepts."""
        super().__init__(stream)
        self.owner = threading.get_ident()

    ## @brief Emit only when the record came from the owning thread.
    ## @param record The record being handled.
    ## @version 1
    ## @dg_internal
    def emit(self, record: logging.LogRecord) -> None:
        """@brief Drop records raised on any other thread."""
        if record.thread == self.owner:
            super().emit(record)


## @brief Send every pipeline writer into a buffer instead of the process stdout.
## @return Context manager yielding the buffer the output lands in.
## @version 2
## @utility
@contextmanager
def captured_output() -> Iterator[io.StringIO]:
    """The seam a caller uses when its `sys.stdout` is a protocol transport: the
    progress bars, the doxygen warning lines, the build summary and the pipeline's
    own log records all land in the yielded buffer, and stdout is untouched for
    anyone else.

    The LOG half is here because the log is where the pipeline explains itself —
    which Doxyfile it resolved, which scope tier it fell back to, what it refused.
    Capturing the rendered output alone would hand a caller a table of row counts
    and drop the sentence saying why the counts are what they are.

    The buffer stays readable after the block ends, so the partial output of a run
    that raised is still available to report.

    @brief Capture pipeline output and logging for the duration of a call.
    @return The buffer receiving everything the pipeline emits.
    @version 2
    """
    buffer = io.StringIO()
    handler = _OwnThreadHandler(buffer)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    level = logger.level
    token = _render_target.set(Console(file=buffer, no_color=True, width=100))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield buffer
    finally:
        logger.setLevel(level)
        logger.removeHandler(handler)
        _render_target.reset(token)


## @brief Single consistent Progress factory across all DB-build stages.
## @version 2
## @return A configured rich Progress instance with the standard column layout.
## @utility
def make_progress(known_total: bool = True) -> Progress:
    """Single consistent Progress factory across all DB-build stages, bound to
    whichever console is active when the bar is created.

    @brief Progress factory used by doxygen, AST, and XML stages.
    @version 2
    """
    cols = [
        SpinnerColumn(),
        TextColumn("  [bold]{task.description:<14}"),
        BarColumn(bar_width=28),
    ]
    if known_total:
        cols.append(TaskProgressColumn())
        cols.append(MofNCompleteColumn())
    else:
        cols.append(TextColumn("[cyan]{task.completed}[/] items"))
    cols.append(TimeElapsedColumn())
    return Progress(*cols, console=active_console(), transient=False)
