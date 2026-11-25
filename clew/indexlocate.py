# SPDX-License-Identifier: MIT
"""Find the index already built for a repository, without building one.

Moved out of `clew propose` (2.1, clew#74) so `clew guard impact` finds the same database by the
same rule: the explicit path, then the MCP server's target registry (the database an agent would
already have built), then `<repo>/clew.db`. NEVER INVENTED: a path that does not exist is "no
index", so a caller reports what it could not compute rather than measuring nothing.

@brief Locate a repository's existing index.
@version 1
"""

from __future__ import annotations

from pathlib import Path


## @brief The existing index for a repository.
## @param repo_root The repository.
## @param explicit A path the caller was given, or None.
## @return The database's path, or None when there is none.
## @version 1
## @req REQ-DDB-GUARD-010
def find_index(repo_root: Path, explicit: str | None = None) -> Path | None:
    """@brief Find the index. @return Path or None."""
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if candidate.is_file() else None
    local = repo_root / "clew.db"
    return registered_index(repo_root) or (local if local.is_file() else None)


## @brief The database the MCP target registry has allocated for a repository.
## @param repo_root The repository.
## @return Its path when the file exists, else None.
## @version 1
## @utility
def registered_index(repo_root: Path) -> Path | None:
    """IMPORTED LAZILY AND GUARDED: the registry lives under `mcp_server`, whose package import
    pulls the optional MCP SDK. A core-only install still runs; it just cannot find an
    agent-built database.

    @brief Registered database.
    @return Path or None.
    """
    try:
        from .mcp_server.state import TargetRegistry
    except ImportError:
        return None
    wanted = str(Path(repo_root).expanduser().resolve())
    for target in TargetRegistry().targets():
        path = Path(target.db_path)
        if str(Path(target.repo_path).expanduser().resolve()) == wanted and path.is_file():
            return path
    return None
