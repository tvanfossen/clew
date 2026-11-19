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
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


## @brief The toolchain config and compiled gate matcher for one working directory.
#  @version 1.0
#  @utility
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


## @brief The `validate.exclude` entry that excludes a path, or None.
#  @details GLOBS, LIKE EVERY OTHER PATH FILTER (R5-CFG F18, 2.0.0): an entry is matched with the
#  toolchain's gitignore-style matcher against the repo-relative path (a directory pattern such as
#  `tests/` or `tests/**` excludes everything under it); an entry prefixed `re:` is a regex
#  searched in the path, the only way to write one. Before, every entry was a regex while every
#  other path filter in `.clew.yaml` was a glob.
#  @version 1.0
#  @req REQ-DDB-GUARD-013
#  @return The matching entry, or None
def excluded_by(file_path: str | Path, patterns: list[str]) -> str | None:
    if not patterns:
        return None
    from ..toolchain import compile_globs, matches
    from .config import EXCLUDE_REGEX_PREFIX

    path = Path(file_path)
    try:
        rel = (path.relative_to(Path.cwd()) if path.is_absolute() else path).as_posix()
    except ValueError:
        ## Outside the repository: no repo-relative path exists, so only a `re:` entry can match.
        rel = path.as_posix()
    parts = rel.split("/")
    dirs = ["/".join(parts[:i]) for i in range(1, len(parts))]
    for pattern in patterns:
        if pattern.startswith(EXCLUDE_REGEX_PREFIX):
            if re.search(pattern[len(EXCLUDE_REGEX_PREFIX) :], rel):
                return pattern
            continue
        matcher = compile_globs((pattern,))
        if matcher is not None and (
            matches(matcher, rel) or any(matches(matcher, d, is_dir=True) for d in dirs)
        ):
            return pattern
    return None


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
