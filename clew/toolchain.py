# SPDX-License-Identifier: MIT
"""The shared toolchain config: `toolchain.toml` ignores and `suppress.toml` entries.

knots, moldy and aurora-lint read one set of repo-level files that say which paths
every tool skips (lang-parsing-substrate's `docs/unified-config-spec.md`):

    # toolchain.toml
    [ignore]
    paths = ["vendor/**", "third_party/**"]

    # suppress.toml
    [[suppress]]
    name = "third-party"
    tool = "*"                  # every tool
    file_glob = "third_party/**"

clew honours them so a repo states "vendor is not ours" once, for every tool. This
module reads them; the build (`cli.py`) and the gate (`clew/guard/`) apply them.

WHAT APPLIES WHERE. The INDEX honours the all-tools statements: `[ignore].paths` and
suppress entries with `tool = "*"`. The GATE honours those plus `[clew.ignore].paths`
and entries with `tool = "clew"`, which are clew's own business. An entry that names a
`rule` suppresses a rule, not a file, so it never becomes an exclusion. That mirrors the
split this project keeps between index scope and gate scope: a statement about the doc
gate is never a reason to hide code from the graph, but "every tool skips vendor" is a
statement about the code itself.

WHERE THEY ARE FOUND. At the repo root, the spec's "walk up from the target until found"
with the target being the repo. `suppress.toml` is read from the same directory as
`toolchain.toml`, or from the root when there is none.

GLOBS ARE MATCHED BY THE SUBSTRATE (`PathIgnore`, globset semantics) against
repo-relative POSIX paths, and expanded here into concrete paths, because doxygen and
the tree scan understand path prefixes, not globs. A directory that matches is excluded
whole and not walked.

@brief Discovery and expansion of toolchain.toml / suppress.toml exclusions.
@version 1
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._common import logger

TOOLCHAIN_FILE = "toolchain.toml"
SUPPRESS_FILE = "suppress.toml"

## The tool name clew answers to in `[<tool>.ignore]` and `[[suppress]] tool = ...`.
TOOL_NAME = "clew"
_ALL_TOOLS = "*"

## Directories never walked while expanding globs: version control and caches, which can
## be huge and are never source.
_NEVER_WALK = frozenset({".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv"})


## @brief The shared toolchain statements found for one repository.
## @version 1
@dataclass(frozen=True)
class ToolchainConfig:
    """Paths are repo-relative globs as stated. `index_globs` is what every tool skips;
    `gate_globs` adds what is stated for clew alone.

    @brief Toolchain ignores and suppress-file exclusions for one repo.
    @version 1
    """

    toolchain_path: Path | None = None
    suppress_path: Path | None = None
    index_globs: tuple[str, ...] = ()
    gate_globs: tuple[str, ...] = ()
    problems: tuple[str, ...] = field(default=())

    ## @brief Whether any statement was found.
    ## @return True when either file supplied at least one glob.
    ## @version 1
    ## @dg_internal
    def declared(self) -> bool:
        """@brief True when there is anything to apply."""
        return bool(self.index_globs or self.gate_globs)

    ## @brief Where the statements came from, for logs and build_meta.
    ## @param repo_root Repo root, to make the paths relative.
    ## @return Comma-separated relative file names, or "".
    ## @version 1
    ## @dg_internal
    def sources(self, repo_root: Path) -> str:
        """@brief The files that were read, relative to the repo."""
        found = [p for p in (self.toolchain_path, self.suppress_path) if p is not None]
        return ", ".join(_relative(p, repo_root) for p in found)


## @brief Read a TOML file into a mapping, recording rather than raising on failure.
## @param path The file.
## @param problems Mutated: a message is appended when the file cannot be used.
## @return The parsed mapping, or {}.
## @version 1
## @dg_internal
def _read_toml(path: Path, problems: list[str]) -> dict[str, Any]:
    """A broken shared config must not fail a build: every tool reads this file, and
    clew refusing it would be the wrong severity. It is reported instead.

    @brief Parse one TOML file tolerantly.
    @return The mapping, or {}.
    """
    from .tomlcompat import require_toml_module

    try:
        with path.open("rb") as handle:
            data = require_toml_module().load(handle)
    except (OSError, ValueError) as exc:
        problems.append(f"{path.name}: could not be read ({exc}) — its exclusions are ignored")
        return {}
    return data if isinstance(data, dict) else {}


## @brief The string list at `table[key]`, or () when absent or malformed.
## @param table A TOML table.
## @param key Key holding a list of strings.
## @param where Name for the problem message.
## @param problems Mutated with a message for a malformed value.
## @return The strings.
## @version 1
## @dg_internal
def _string_list(table: Any, key: str, where: str, problems: list[str]) -> tuple[str, ...]:
    """@brief Read a list-of-strings value."""
    value = table.get(key) if isinstance(table, dict) else None
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        problems.append(f"{where}.{key} is not a list of strings — ignored")
        return ()
    return tuple(value)


## @brief The globs of one `[[suppress]]` entry that suppresses whole files.
## @param entry One suppress entry.
## @return Its `file` / `file_glob` patterns, or () when it scopes a rule.
## @version 1
## @dg_internal
def _entry_globs(entry: Any) -> tuple[str, ...]:
    """An entry with a `rule` suppresses that rule only (AND semantics in the spec), so it
    is not a file exclusion.

    @brief File patterns of a file-level suppress entry.
    @return The patterns.
    """
    if not isinstance(entry, dict) or entry.get("rule"):
        return ()
    patterns = [entry.get("file"), entry.get("file_glob")]
    return tuple(p for p in patterns if isinstance(p, str) and p)


## @brief Locate and read a repository's toolchain.toml and suppress.toml.
## @param repo_root The repository root.
## @return A ToolchainConfig; empty when neither file exists.
## @version 1
## @req REQ-DDB-CONFIG-009
def load_toolchain_config(repo_root: Path | str) -> ToolchainConfig:
    """@brief Read the shared toolchain exclusions for one repo."""
    root = Path(repo_root)
    toolchain = root / TOOLCHAIN_FILE
    suppress = root / SUPPRESS_FILE
    problems: list[str] = []
    index: list[str] = []
    gate: list[str] = []

    if toolchain.is_file():
        data = _read_toml(toolchain, problems)
        index += _string_list(data.get("ignore"), "paths", "ignore", problems)
        own = data.get(TOOL_NAME) if isinstance(data.get(TOOL_NAME), dict) else {}
        gate += _string_list(own.get("ignore"), "paths", f"{TOOL_NAME}.ignore", problems)

    if suppress.is_file():
        data = _read_toml(suppress, problems)
        entries = data.get("suppress", [])
        for entry in entries if isinstance(entries, list) else []:
            tool = entry.get("tool") if isinstance(entry, dict) else None
            if tool == _ALL_TOOLS:
                index += _entry_globs(entry)
            elif tool == TOOL_NAME:
                gate += _entry_globs(entry)

    for problem in problems:
        logger.warning("toolchain config: %s", problem)
    return ToolchainConfig(
        toolchain_path=toolchain if toolchain.is_file() else None,
        suppress_path=suppress if suppress.is_file() else None,
        index_globs=tuple(dict.fromkeys(index)),
        gate_globs=tuple(dict.fromkeys(index + gate)),
        problems=tuple(problems),
    )


## @brief Compile globs into the substrate's matcher, dropping any that do not compile.
## @param globs Glob patterns.
## @return A PathIgnore, or None when there is nothing usable.
## @version 1
## @dg_internal
def compile_globs(globs: tuple[str, ...]) -> Any | None:
    """One bad glob must not take the rest down with it, so each is checked on its own
    and a refused one is reported by name.

    @brief Build a PathIgnore from the valid globs.
    @return The matcher, or None.
    """
    from lang_parsing_substrate import PathIgnore

    valid = []
    for glob in globs:
        try:
            PathIgnore([glob])
        except ValueError as exc:
            logger.warning("toolchain config: invalid glob %r ignored (%s)", glob, exc)
            continue
        valid.append(glob)
    return PathIgnore(valid) if valid else None


## @brief Whether a repo-relative path matches, as a file or as a directory.
## @param matcher A compiled PathIgnore.
## @param rel Repo-relative POSIX path.
## @param is_dir Whether the path is a directory.
## @return True when the path is excluded.
## @version 1
## @dg_internal
def matches(matcher: Any, rel: str, *, is_dir: bool = False) -> bool:
    """globset reads `vendor/**` as matching `vendor/` and everything under it, but not
    `vendor`; a bare `build` matches `build` and nothing under it. A directory is tested
    both ways, so both spellings exclude the directory.

    @brief Match one path against the toolchain globs.
    @return True when excluded.
    """
    if matcher.is_ignored(rel):
        return True
    return is_dir and matcher.is_ignored(rel + "/")


## @brief Expand toolchain globs into the concrete paths they exclude under a root.
## @param repo_root The repository root the globs are relative to.
## @param globs Glob patterns.
## @param prune Absolute directories already excluded, which are not walked.
## @return Sorted absolute paths: whole directories where a directory matched, else files.
## @version 1
## @req REQ-DDB-CONFIG-009
def expand_globs(repo_root: Path, globs: tuple[str, ...], prune: list[str] = ()) -> list[Path]:
    """Doxygen's EXCLUDE and the tree scan take paths, not globs, so the globs are
    resolved against the tree once per build. A matched directory is returned whole and
    not descended into, which keeps `vendor/**` one exclusion rather than thousands.

    @brief Resolve globs to concrete excluded paths.
    @return The excluded paths.
    """
    matcher = compile_globs(globs)
    if matcher is None:
        return []
    root = Path(repo_root)
    pruned = {str(Path(p)) for p in prune}
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        rel_here = "" if here == root else here.relative_to(root).as_posix() + "/"
        keep = []
        for name in sorted(dirnames):
            full = here / name
            if name in _NEVER_WALK or str(full) in pruned:
                continue
            if matches(matcher, rel_here + name, is_dir=True):
                out.append(full)
            else:
                keep.append(name)
        dirnames[:] = keep
        out += [here / f for f in sorted(filenames) if matcher.is_ignored(rel_here + f)]
    return sorted(out)


## @brief A path relative to the repo when it is inside it, else as given.
## @return The display path.
## @version 1
## @dg_internal
def _relative(path: Path, repo_root: Path) -> str:
    """@brief Repo-relative display form of a path."""
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)
