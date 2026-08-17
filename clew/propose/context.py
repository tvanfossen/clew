# SPDX-License-Identifier: MIT
"""Everything a detector is allowed to look at, assembled once.

Kept in its own module so the detectors and the orchestrating registry can both
import it without a cycle. It is also the enforcement point for the expensive
invariants: the corpus is parsed ONCE and shared, and a detector never gets to
re-derive the scope or re-read the declaration for itself (two detectors
disagreeing about which files are in scope is exactly how the two design passes
ended up 14-36% apart on their own counts).

@brief Shared, pre-computed inputs for every detector.
@version 1
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..scope import DerivedScope
from .scanning import Corpus


## @brief The pre-computed inputs every detector reads.
## @version 1
@dataclass(frozen=True)
class Context:
    """`db_path` is None when the repo has no built index; detectors must then
    degrade to "not measured" rather than guessing, because the dry-run gate is
    the only thing standing between a plausible candidate and a wrong one.

    `dry_run` False is the `--no-dry-run` escape hatch and is FAIL-CLOSED: a
    detector that cannot measure emits nothing it would have gated on.

    @brief Shared detector inputs (scope, corpus, index, declaration).
    @version 1
    """

    repo_root: Path
    db_path: Path | None
    scope: DerivedScope
    declared: dict[str, Any]
    files: tuple[Path, ...]
    in_scope: Any
    corpus: Corpus
    ts_classes: tuple[Any, Any]
    dry_run: bool = True

    ## @brief Whether this run can measure a candidate against a real index.
    ## @return True when an index exists and dry runs are enabled.
    ## @version 1
    ## @req REQ-DDB-CONFIG-001
    def can_measure(self) -> bool:
        """@brief Whether the dry-run gate is available on this run."""
        return self.dry_run and self.db_path is not None and self.db_path.is_file()
