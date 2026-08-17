# SPDX-License-Identifier: MIT
"""Build a doxygen SQLite knowledge database from source code.

Public entry point: `python -m clew --doxyfile <path>
--output <path> [--enrich ...] [--repo-root ...]`.

The pipeline:

  1. doxygen runs with GENERATE_SQLITE3 forced on
     (see `doxygen.run_doxygen`).
  2. Generated DB copied into place; doxygen STRIP_FROM_PATH paths
     are restored to repo-root-relative form
     (`doxygen.fix_doxygen_paths`).
  3. README/CHANGELOG/docs/*.md ingested into FTS5
     (`prose.ingest_supplementary_docs`).
  4. Two layers of call-edge import populate `call_edges`:
     `call_edges.build_call_edges` (doxygen sqlite3 inline xrefs),
     `call_edges.import_ast_call_edges` (tree-sitter AST walk).
  5. Reachability BFS marks every function `live` or `orphan`
     (`reachability.mark_reachability`).
  6. Stats printed (`cli.report_stats`).

Each module is independently testable; previously this was one
~1200-line file. Split landed in Phase C PR-2.

@brief Doxygen → SQLite knowledge-database build pipeline.
@version 3
"""

from __future__ import annotations

# Re-export the public functions so the flat-module API keeps working
# for callers importing `clew.X`, in a checkout and from the
# wheel alike. Relative imports work in both contexts.
from .call_edges import (
    build_call_edges,
    import_ast_call_edges,
)
from .cli import main, report_stats
from .dispatch import load_dispatch_manifest, shared_key_document
from .dispatch_edges import import_declared_dispatch_edges
from .doxygen import (
    copy_database,
    fix_doxygen_paths,
    run_doxygen,
)
from .enrichment import enrich_database
from .filedocs import extract_file_doc, ingest_file_docs
from .kconfig import import_kconfig
from .kconfig_gates import import_kconfig_gates
from .prose import ingest_supplementary_docs
from .reachability import (
    DEFAULT_ENTRY_PATTERNS,
    ENTRY_PATTERN_FACTS,
    ENTRY_PATTERN_HEURISTICS,
    mark_reachability,
)
from .shared_key_edges import (
    import_mqtt_dispatch_edges,
    import_shared_key_edges_declared,
    import_shared_key_edges_inferred,
)
from .threads import (
    DEFAULT_SPAWN_PATTERNS,
    annotate_thread_boundaries,
    extract_threads,
)

__all__ = [
    "DEFAULT_ENTRY_PATTERNS",
    "DEFAULT_SPAWN_PATTERNS",
    "ENTRY_PATTERN_FACTS",
    "ENTRY_PATTERN_HEURISTICS",
    "annotate_thread_boundaries",
    "build_call_edges",
    "copy_database",
    "enrich_database",
    "extract_file_doc",
    "extract_threads",
    "fix_doxygen_paths",
    "import_ast_call_edges",
    "import_declared_dispatch_edges",
    "import_kconfig",
    "import_kconfig_gates",
    "import_mqtt_dispatch_edges",
    "import_shared_key_edges_declared",
    "import_shared_key_edges_inferred",
    "ingest_file_docs",
    "ingest_supplementary_docs",
    "load_dispatch_manifest",
    "main",
    "mark_reachability",
    "report_stats",
    "run_doxygen",
    "shared_key_document",
]
