"""File filters the gate shares with clew's index: shared toolchain ignores and file typing.

@brief Toolchain-config and binary-file exclusion for the gate's file walks.
@version 1.0

Applied after `validate.exclude`, in `validate_file` (pre-commit and `validate`) and in
`find_source_files` (`coverage`, `files`). Paths are matched relative to the working
directory, which is the repository root when pre-commit runs the hook, the same root
`.clew.yaml` is read from.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


## @brief The toolchain config and compiled gate matcher for one working directory.
#  @version 1.0
#  @dg_internal
#  @return (ToolchainConfig, PathIgnore or None)
@lru_cache(maxsize=4)
def _gate_matcher(root: str) -> tuple[Any, Any]:
    from ..toolchain import compile_globs, load_toolchain_config

    config = load_toolchain_config(Path(root))
    return config, compile_globs(config.gate_globs) if config.gate_globs else None


## @brief The toolchain ignores the gate honours here, for the files contract.
#  @version 1.0
#  @req REQ-DDB-CONFIG-009
#  @return {"toolchain_config": sources, "toolchain_ignores": globs}
def toolchain_contract() -> dict[str, Any]:
    root = Path.cwd()
    config, _ = _gate_matcher(str(root))
    return {"toolchain_config": config.sources(root), "toolchain_ignores": list(config.gate_globs)}


## @brief Why the gate should not read a file, or None when it should.
#  @details Toolchain ignores first (toolchain.toml `[ignore]` and `[clew.ignore]`,
#  suppress.toml entries for `*` and `clew`), then file typing: a binary file named like
#  source is never parsed.
#  @version 1.0
#  @req REQ-DDB-CONFIG-009
#  @return A reason string, or None
def gate_exclusion(file_path: str | Path) -> str | None:
    root = Path.cwd()
    config, matcher = _gate_matcher(str(root))
    path = Path(file_path)
    try:
        rel = (path if not path.is_absolute() else path.relative_to(root)).as_posix()
    except ValueError:
        rel = None
    if matcher is not None and rel is not None:
        from ..toolchain import matches

        parts = rel.split("/")
        dirs = ["/".join(parts[:i]) for i in range(1, len(parts))]
        if matches(matcher, rel) or any(matches(matcher, d, is_dir=True) for d in dirs):
            return f"ignored by {config.sources(root)}"
    from ..filetypes import binary_file

    skipped = binary_file(path)
    if skipped is not None:
        return f"{skipped.binary_kind} binary, not source"
    return None
