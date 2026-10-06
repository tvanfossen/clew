"""Source discovery and @req tag collection.

@brief Walk source trees, parse documented functions, and model their requirement tags.
@version 1.0
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .checks import EXEMPTION_TAGS
from .config import get_validate, parse_source_file_with_content

if TYPE_CHECKING:
    from .parser import Function

logger = logging.getLogger(__name__)

_GIT_LS_TIMEOUT_SECONDS = 30

__all__ = [
    "TaggedFunction",
    "collect_tagged_functions",
    "find_source_files",
]


## @brief A documented function and the requirement IDs it declares.
#  @version 1.0
#  @req REQ-DDB-GUARD-022
@dataclass
class TaggedFunction:
    name: str
    file_path: str
    reqs: list[str] = field(default_factory=list)
    is_exempt: bool = False


## @brief List tracked source files under a directory via git ls-files.
#  @version 1.0
#  @dg_internal
#  @return Matching paths, or None if the directory is not a usable git tree
def _git_ls_files(source_dir: str, extensions: set[str]) -> list[Path] | None:
    try:
        result = subprocess.run(
            ["git", "-C", source_dir, "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_GIT_LS_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, subprocess.TimeoutExpired):
        logger.info("git ls-files unavailable for %s, falling back to filesystem walk", source_dir)
        return None
    base = Path(source_dir)
    return [
        base / line
        for line in result.stdout.splitlines()
        if line and any(line.endswith(ext) for ext in extensions)
    ]


## @brief Fallback source discovery via filesystem glob.
#  @version 1.0
#  @dg_internal
#  @return Matching paths, or None if the directory does not exist
def _rglob_source_files(source_dir: str, extensions: set[str]) -> list[Path] | None:
    source_path = Path(source_dir)
    if not source_path.exists():
        logger.warning("Source directory not found: %s", source_dir)
        return None
    files: list[Path] = []
    for ext in extensions:
        for f in source_path.rglob(f"*{ext}"):
            rel = str(f.relative_to(Path.cwd())) if f.is_absolute() else str(f)
            files.append(Path(rel))
    return files


## @brief Find source files for configured languages, applying validate.exclude patterns.
#  @version 1.0
#  @req REQ-DDB-GUARD-013
#  @return Sorted source paths that survive the exclude patterns
def find_source_files(source_dir: str, config: dict[str, Any]) -> list[Path]:
    validate = get_validate(config)
    languages = validate.get("languages", {})
    exclude_patterns = validate.get("exclude", [])
    extensions: set[str] = set()
    for lang_config in languages.values():
        extensions.update(lang_config.get("extensions", []))

    git_files = _git_ls_files(source_dir, extensions)
    candidates = git_files if git_files is not None else _rglob_source_files(source_dir, extensions)
    if candidates is None:
        return []

    kept = sorted(f for f in candidates if not any(re.search(p, str(f)) for p in exclude_patterns))
    logger.info(
        "Source scan %s: %d candidate(s), %d kept after %d exclude pattern(s)",
        source_dir,
        len(candidates),
        len(kept),
        len(exclude_patterns),
    )
    return kept


## @brief Build a TaggedFunction for a documented function, or None if undocumented.
#  @version 1.1
#  @dg_internal
#  @return TaggedFunction for any function carrying a doxygen block, else None
def _extract_tagged_function(func: Function, file_path: str) -> TaggedFunction | None:
    if func.doxygen is None:
        return None
    tags = func.doxygen.tags
    return TaggedFunction(
        name=func.name,
        file_path=file_path,
        reqs=tags.get("req", []),
        is_exempt=bool(EXEMPTION_TAGS & set(tags)),
    )


## @brief Parse one source file into its documented functions.
#  @version 1.0
#  @dg_internal
def _process_source_file(source_file: Path, config: dict[str, Any]) -> list[TaggedFunction]:
    result = parse_source_file_with_content(str(source_file), config)
    if result is None:
        logger.info("No language config matched %s, skipping", source_file)
        return []
    functions = result[0]
    extracted = (_extract_tagged_function(func, str(source_file)) for func in functions)
    return [tf for tf in extracted if tf is not None]


## @brief Walk source directories and collect every documented function.
#  @version 1.0
#  @req REQ-DDB-GUARD-022
#  @return All documented functions found, each with its declared requirement IDs
def collect_tagged_functions(
    source_dirs: list[str],
    config: dict[str, Any],
) -> list[TaggedFunction]:
    tagged: list[TaggedFunction] = []
    file_count = 0
    for source_dir in source_dirs:
        source_files = [f for f in find_source_files(source_dir, config) if f.exists()]
        file_count += len(source_files)
        for source_file in source_files:
            tagged.extend(_process_source_file(source_file, config))

    with_reqs = sum(1 for tf in tagged if tf.reqs)
    logger.info(
        "Tag scan: %d file(s), %d documented function(s), %d with @req, %d without",
        file_count,
        len(tagged),
        with_reqs,
        len(tagged) - with_reqs,
    )
    return tagged
