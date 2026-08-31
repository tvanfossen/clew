# SPDX-License-Identifier: MIT
"""A per-build log written beside the index, incrementally.

WHAT IT IS FOR. A build that is running tells you nothing. Every diagnosis in the investigation
that produced this module came from `ps`: whether a twenty-minute build was working or wedged,
which stage it was in, whether the doxygen child was this build's or an orphan of the last one.
None of that was answerable from the tool, and "slow" and "hung" are indistinguishable from
outside a silent process — so an operator kills it, which is how six consecutive builds of one
target ended.

INCREMENTAL IS THE ENTIRE POINT, not a nicety. A log flushed at the end is written exactly when
it stops being needed: the interesting build is the one that never finishes. Every record is
flushed as it is emitted, so `tail -f` on a live build works and a killed build leaves everything
up to the moment it died.

BESIDE THE INDEX, NOT IN THE REPO. clew is a read-only consumer of target repositories; the log
goes next to the database in the state directory, where the sidecar and the lock already live.

IT IS DIAGNOSTIC, NEVER LOAD-BEARING. Nothing reads it back, no decision depends on it, and every
failure to write it is swallowed: an unwritable state directory, a full disk and a read-only
filesystem are all real, and none of them is a reason to fail a build that would otherwise
succeed. A component that can only ever ADD information must not be able to remove any.

ONE BUILD, ONE FILE, OVERWRITTEN. The previous build's log is replaced rather than rotated,
because the question this answers is always about the run happening now, and a rotation policy is
a second thing to get wrong on a path that is already best-effort.

@brief Per-build diagnostic log, flushed per record, beside the index.
@version 1
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ._common import logger

## Suffix for the log file, beside the database it describes — the same convention as
## `.idxcache` and `.buildlock`, so everything about one target lives under one stem.
LOG_SUFFIX = ".buildlog"

## Records carry their level and the stage timings already logged by the pipeline. The time is
## included because the FIRST question about a slow build is always "how long has it been in
## this stage", and a bare message cannot answer it.
_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"


##
# @brief Path of the build log for one target.
# @param output The database the build writes.
# @return Sibling log path.
# @version 1
# @utility
def log_path(output: Path) -> Path:
    """@brief Derive the build log path.
    @return The log file path.
    @version 1
    """
    return output.with_name(output.name + LOG_SUFFIX)


##
# @brief A logging handler that flushes every record immediately.
# @version 1
# @dg_internal
class _FlushingFileHandler(logging.FileHandler):
    """THE FLUSH IS THE FEATURE. `logging.FileHandler` buffers, so a killed build would leave a
    truncated or empty file — precisely the build whose log matters. Flushing per record costs a
    write syscall per line against a pipeline that spends minutes in tree-sitter, which is not a
    trade worth thinking about.

    @brief File handler with no buffering between records.
    @version 1
    """

    ## @brief Emit one record and flush it to disk.
    ## @param record The record to write.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def emit(self, record: logging.LogRecord) -> None:
        """@brief Write and flush.
        @version 1
        """
        super().emit(record)
        self.flush()


##
# @brief Tee this build's log records to a file beside the index.
# @param output The database the build writes; the log is its sibling.
# @return Yields the log path, or None when logging to a file was not possible.
# @version 1
# @req REQ-DDB-INDEX-002
@contextmanager
def build_log(output: Path) -> Iterator[Path | None]:
    """YIELDS None RATHER THAN RAISING when the log cannot be opened. The caller is a build, and
    a build must not fail because a diagnostic file could not be created — that would convert an
    observability feature into a new failure mode, which is the opposite of the point.

    TEE, NOT REDIRECT. The handler is ADDED to the existing logger, so console output and the
    MCP server's in-memory capture are both untouched and see exactly what they saw before.

    @brief Attach a file handler for the duration of one build.
    @return Yields the log path, or None.
    @version 1
    """
    path = log_path(output)
    handler: logging.Handler | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = _FlushingFileHandler(str(path), mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
    except OSError as exc:
        ## An unwritable state directory is a real deployment. Say so once, at DEBUG, and build.
        logger.debug("build log: cannot write %s (%s) — continuing without it", path, exc)
        yield None
        return
    ## THE LOGGER'S LEVEL, NOT JUST THE HANDLER'S — WITHOUT THIS THE FILE IS NEARLY EMPTY.
    ## A handler set to DEBUG never sees a record the LOGGER filtered out first, and the `clew`
    ## logger is lowered to INFO only by `_configure_logging`, which the CLI calls and the
    ## library and MCP entry points do not. So the build log captured warnings and nothing else
    ## on exactly the paths it exists for. MEASURED before this line: a log holding one config
    ## warning and none of the stage progress. `capture_pipeline_output` raises the level for
    ## the same reason.
    ##
    ## RAISED ONLY WHEN IT WOULD OTHERWISE HIDE INFO, so `--verbose` (DEBUG) is not quietly
    ## downgraded by attaching a log.
    previous = logger.level
    if previous == logging.NOTSET or previous > logging.INFO:
        logger.setLevel(logging.INFO)
    try:
        yield path
    finally:
        logger.setLevel(previous)
        logger.removeHandler(handler)
        try:
            handler.close()
        except OSError:  # pragma: no cover - already gone
            pass
