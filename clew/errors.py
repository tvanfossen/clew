# SPDX-License-Identifier: MIT
"""The environment-is-wrong exception types.

Every type here says a PREREQUISITE IS MISSING, not that clew failed:
something the user's machine or install must supply is absent, and `cli.main`
turns each into a one-line exit 2 rather than a traceback.

TRUE LEAF — zero intra-package imports, by design. `clew/_common.py`
pulls in `rich`, while `clew/query/_common.py` is deliberately
stdlib-only; importing either here would make one of those two layers
un-importable without the other's dependencies. A logger, if one is ever needed,
comes from `logging.getLogger` directly for exactly that reason.

@brief Missing-prerequisite exception types.
@version 1
"""

from __future__ import annotations


## @brief The external `doxygen` binary is not installed or not on PATH.
## @version 1
class DoxygenUnavailableError(RuntimeError):
    """Raised before the pipeline spawns doxygen, when the binary is absent.

    Exists because the alternative shipped: on a machine without doxygen a cold
    build produced a twelve-frame Python traceback ending
    `FileNotFoundError: [Errno 2] No such file or directory: 'doxygen'`. That is
    the worst possible first contact with the tool — it reads as a bug in
    clew rather than a missing prerequisite, and it names a file the reader
    never asked for.

    doxygen CANNOT be a pip dependency: it is a C++ program distributed as a
    system package, and `pip install doxygen` finds no distribution. So it is the
    one prerequisite an installed user must supply themselves, which makes a clear
    message about it more important rather than less. `init` already checks and
    reports — but `init` is an OPTIONAL doctor, and nothing on the build path
    checked, so the check existed exactly where a user who skipped it would not see
    it.

    @brief Missing doxygen binary — refuse before spawning.
    @version 1
    """


## @brief `cargo`, or a nightly toolchain capable of `rustdoc --output-format json`,
## is not available.
## @version 1
class RustdocUnavailableError(RuntimeError):
    """Raised before the pipeline spawns `cargo rustdoc`, when cargo is missing or
    no nightly toolchain is installed.

    Doxygen has no Rust parser, so a Rust repo's structural layer (`clew/rustdoc.py`)
    comes from `cargo +nightly rustdoc -- -Z unstable-options --output-format json`
    instead — rustdoc's JSON output has been nightly-gated since it was introduced and
    remains so. This is the SAME kind of refusal `DoxygenUnavailableError` makes for the
    `doxygen` binary: fail before spawning, with a message naming the missing
    prerequisite, rather than let a bare `FileNotFoundError` or a nightly-feature
    compiler error read as a bug in clew.

    Unlike doxygen, `cargo`/`rustup` ARE how most Rust developers already manage their
    toolchain, so the fix named here is `rustup toolchain install nightly` rather than a
    system package manager invocation.

    @brief Missing cargo or nightly rustdoc — refuse before spawning.
    @version 1
    """


## @brief Neither `tomllib` (3.11+) nor the `tomli` backport is importable.
## @version 1
class TomlParserUnavailableError(RuntimeError):
    """Raised when a TOML document must be read and no parser exists.

    A distinct type, rather than the `ImportError` it is raised from, because
    `ImportError` is precisely what the old handler CAUGHT. `py_entrypoints`
    imported `tomllib` inside `except (OSError, ValueError, ImportError)`, so on
    Python 3.10 the missing stdlib module was swallowed, logged as a warning and
    turned into `{}` — the pipeline then went on to build a graph missing every
    `pyproject.toml` entry point, with nothing in the output saying so. That is
    this project's recurring defect: an absent CAPABILITY that is indistinguishable
    from an absent FINDING.

    The type distinction is what lets a caller keep the tolerance it actually
    wanted (a repo with no `pyproject.toml`, or one with a syntax error in it, must
    not fail a build) while refusing the one case that is a broken installation.

    Reaching this on a supported interpreter should be impossible: `tomllib` is
    stdlib from 3.11, and below that `pyproject.toml` declares
    `tomli>=2; python_version < "3.11"`. So the message names that dependency —
    the only way here is an install where the conditional dependency did not
    arrive, and the fix is `pip install tomli`.

    @brief No TOML parser available — refuse rather than return an empty document.
    @version 1
    """
