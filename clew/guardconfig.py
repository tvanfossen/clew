# SPDX-License-Identifier: MIT
"""Read a repo's gate config — the `guard:` section of its `.clew.yaml` — for the INDEX.

The gate and the index read the same section with the same schema
(`clew.guard.config`), so a repo states its `@req` id pattern, its requirements
catalog and its `validate.exclude` once. They read it at DIFFERENT SEVERITIES, the
split this project already draws between gate scope and index scope:

- the GATE refuses an invalid section outright (`clew guard` exits 1), which is where
  the author learns about it;
- the INDEX warns and runs on its permissive built-in defaults, because failing a build
  over a gate typo would take a doxygen run with it.

Absent is not an error: a repo with no `.clew.yaml`, or one with no `guard:` section,
declares nothing and every declaration-driven lookup falls back to its default.

@brief Index-side loading of the `guard:` section of `.clew.yaml`.
@version 3
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._common import logger


## @brief A repo's guard config as the index read it.
## @version 2
@dataclass(frozen=True)
class GuardConfigRead:
    """`config` is empty when nothing was declared or the declaration was refused; the
    refusal's reasons are in `rejected`, so a caller can say why its defaults applied.

    @brief Result of an index-side guard-config read.
    """

    config: dict[str, Any]
    path: Path
    rejected: tuple[str, ...] = ()

    ## @brief Whether the read produced a config to declare from.
    ## @return True when a `guard:` section was read and accepted.
    ## @version 1
    ## @req REQ-DDB-CONFIG-001
    def usable(self) -> bool:
        """@brief Whether any config was recovered from the file."""
        return bool(self.config)


## @brief Read the `guard:` section of a repo's `.clew.yaml`, merged over the gate's defaults.
## @param repo_root Repo root whose `.clew.yaml` is read.
## @return A GuardConfigRead; `config` is empty when nothing usable was declared.
## @version 2
## @req REQ-DDB-CONFIG-001
def read_guard_config(repo_root: Path | str) -> GuardConfigRead:
    """THE single guard-config load for the index. Both consumers — the `@req` id
    pattern / catalog mapping in `requirements.py` and the declaration's view of the
    file — go through here, so an invalid section is reported once and cannot be
    tolerated by one reader and fatal to the other.

    @brief Load a repo's gate config for the index.
    @return The read result.
    """
    from .guard.config import CONFIG_FILE_NAME, load_config, read_guard_section
    from .guard.errors import ConfigError

    path = Path(repo_root).expanduser() / CONFIG_FILE_NAME
    try:
        declared = path.is_file() and read_guard_section(path) is not None
        config = load_config(path) if declared else {}
    except ConfigError as exc:
        problems = tuple(exc.problems) or (exc.message,)
        logger.warning(
            "guard config: %s is INVALID (%s) — the index continues with built-in defaults "
            "for the requirement-tag id pattern and the requirements catalog mapping; "
            "run 'clew guard validate' to see the gate refuse it",
            path,
            "; ".join(problems),
        )
        return GuardConfigRead(config={}, path=path, rejected=problems)
    return GuardConfigRead(config=config, path=path)
