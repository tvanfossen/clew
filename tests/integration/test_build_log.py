# SPDX-License-Identifier: MIT
"""A build must leave a readable account of itself, written as it goes.

WHY THIS EXISTS. A running build told nobody anything. Whether a twenty-minute run was working or
wedged, which stage it was in, whether a doxygen process belonged to it or was an orphan of the
previous attempt — every one of those questions was answered with `ps` during the investigation
that produced this module, because the tool could not answer any of them. "Slow" and "hung" are
indistinguishable from outside a silent process, and an operator who cannot tell them apart kills
the build. That happened six times in a row on one target.

THE INCREMENTAL HALF IS THE WHOLE POINT, AND ONLY ONE TEST HERE PINS IT. A log flushed at the end
is written exactly when it has stopped being useful: the build worth reading about is the one that
never finished.

The obvious test does NOT establish that, which was found by mutation rather than by reading.
`test_a_failed_build_still_leaves_its_log` passes with the per-record flush removed, because the
handler's `close()` on the way out flushes whatever was buffered — so an aborted build's log
survives either way. Surviving an abort and being written as you go are different properties.
`test_the_log_is_readable_while_the_build_is_still_running` is the one that separates them, by
reading the file from inside a live build.

TWO MUTATION CONTROLS, AND ONLY ONE OF THEM BITES — recorded so the next reader does not go
hunting a gap that is not there:

  * REMOVING THE LOGGER-LEVEL RAISE is CAUGHT. It was also a real defect the probe found: a
    handler set to DEBUG still sees nothing the LOGGER filtered first, and `clew`'s logger is
    only lowered by `_configure_logging`, which the CLI calls and the library and MCP paths do
    not. The log held one config warning and no stage progress.
  * REMOVING THE PER-RECORD FLUSH is INERT against this suite, and that is a property of the
    FIXTURE, not a missing assertion. `FileHandler` block-buffers at ~8 KB and this build logs
    well past that before the probe, so the buffer spills on its own and the marker is on disk
    either way. The flush still buys the guarantee that matters — that the TAIL is readable,
    which on a wedged build is the stage it is stuck in — but a boundary that lands arbitrarily
    cannot be turned into a deterministic assertion here. If a future change makes this
    mutation start failing, the flush has become testable and this note should go.

@brief Integration tests for the per-build log.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew import cli
from clew._common import logger
from clew.buildlog import log_path
from clew.cli import _build_argparser, _run_pipeline

pytestmark = pytest.mark.integration

## A line the probe emits mid-build and then looks for on disk. Distinctive so it cannot be
## confused with anything the pipeline logs on its own.
_MARKER = "clew-buildlog-liveness-probe"


## @brief Run the pipeline against the pinned target.
## @param root Target repository.
## @param out Database path.
## @return The output path.
## @version 1
def _build(root: Path, out: Path) -> Path:
    """@brief Build the target.
    @return The output path.
    @version 1
    """
    args = _build_argparser().parse_args(["--repo-root", str(root), "--output", str(out)])
    _run_pipeline(args)
    return out


## @brief A completed build leaves a log naming the stages it ran.
## @version 1
def test_a_build_writes_a_log_beside_the_index(guard_repo: Path, tmp_path: Path) -> None:
    """Asserts CONTENT, not merely existence. An empty file would satisfy "a log is written" and
    answer none of the questions the log exists for, which is the shape of a diagnostic feature
    that ships and helps nobody.

    The needle is the doxygen stage, because it is the one that runs on every target regardless
    of language and richness tier — a needle from a C-only layer would make this test quietly
    target-specific.

    @brief The build log exists and describes the build.
    @version 1
    """
    out = tmp_path / "logged.db"
    _build(guard_repo, out)

    path = log_path(out)
    assert path.exists(), f"no build log at {path}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), "the build log is empty"
    assert "doxygen" in text.lower(), (
        "the build log does not mention the doxygen stage, so it is not recording the pipeline's "
        f"own progress. Head: {text[:400]!r}"
    )


## @brief An aborted build still leaves everything it logged before it died.
## @version 1
def test_a_failed_build_still_leaves_its_log(
    guard_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE TEST THAT DISTINGUISHES THIS FEATURE FROM A USELESS ONE. A log assembled in memory and
    written on success would pass the test above and fail this one, while being worthless for
    every case it was built for: the builds that need explaining are the builds that do not
    finish.

    The abort is placed in a LATE stage on purpose, so a passing result means "the earlier stages
    were already flushed to disk" rather than "the file happened to be created".

    @brief A killed build's log survives with its content.
    @version 1
    """

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("stage failed late in the build")

    monkeypatch.setattr(cli, "mark_reachability", _boom)
    out = tmp_path / "aborted.db"

    with pytest.raises(RuntimeError):
        _build(guard_repo, out)

    path = log_path(out)
    assert path.exists(), (
        f"no build log at {path} after a failed build — which is the only case the log is "
        "actually needed for"
    )
    text = path.read_text(encoding="utf-8")
    assert "doxygen" in text.lower(), (
        "the aborted build's log holds nothing from the stages that DID run, so it was buffered "
        f"rather than flushed as it went. Content: {text[:400]!r}"
    )


## @brief The log is readable mid-build, not assembled and written at the end.
## @version 1
def test_the_log_is_readable_while_the_build_is_still_running(
    guard_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE ONLY TEST HERE THAT PINS INCREMENTALITY, and it exists because the obvious one does
    not. `test_a_failed_build_still_leaves_its_log` passes with the per-record flush REMOVED —
    verified by mutation — because the handler's `close()` in the context manager's `finally`
    flushes whatever was buffered on the way out. Survival of an abort and incremental writing
    are different properties, and only one of them helps somebody watching a build that has not
    ended.

    So this reads the file from INSIDE the build, part-way through, where nothing has closed the
    handler yet. A buffered handler has written nothing to disk at that moment; a flushing one
    has written everything up to the current stage.

    @brief A live build's log is on disk before the build ends.
    @version 1
    """
    out = tmp_path / "live.db"
    seen: dict[str, str] = {}
    real = cli.mark_reachability

    def _peek(*args: object, **kwargs: object) -> object:
        ## EMIT, THEN IMMEDIATELY READ. Asserting on the log's accumulated content is not a test
        ## of flushing: `FileHandler` block-buffers at ~8 KB, and this fixture logs more than that
        ## before here, so a buffered handler has already spilled most of it to disk anyway —
        ## verified, the mutation survived that version. What buffering actually costs is the
        ## TAIL, which is precisely the part that says which stage a wedged build is sitting in.
        ## So the probe writes its own line and looks for THAT.
        logger.info("%s", _MARKER)
        seen["text"] = log_path(out).read_text(encoding="utf-8")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cli, "mark_reachability", _peek)
    _build(guard_repo, out)

    assert "text" in seen, "the probe never ran; this test would be vacuous"
    assert _MARKER in seen["text"], (
        "a line logged moments earlier was not yet on disk, so the log's TAIL is buffered. That "
        "tail is the whole value: it is what names the stage a wedged build is sitting in, and "
        "it is exactly what a reader of a still-running build has to go on."
    )
    ## And the earlier stages are there too — the log is cumulative, not just the last line.
    assert "doxygen" in seen["text"].lower(), "the log lost the stages that ran before the probe"
