# SPDX-License-Identifier: MIT
"""The ten per-file AST stages of one build, assembled before any of them runs.

gh#358. Every stage here walks the same file set and each used to drive its own
`run_harvest`, so a cold build parsed every file once per stage — ten times, and
`parser_cache` could not help because it memoizes tree-sitter *Parser* objects,
not parsed trees. This module names the stages ONCE so `run_shared_parse` can
parse each file once and warm all ten of their cache rows from that single tree.

**IT IS A PLAN OF HARVESTS, NOT OF EMITS.** Nothing here emits a row or decides
an order. The stages still run where the pipeline puts them, in the order their
data dependencies demand — `ast_symbols` before every layer that resolves an
endpoint to a memberdef rowid, the self-edge guard inside the call-edge stage,
callback_edges applying its `PreprocessorConfig` after its own harvest. Sharing
a parse is sound precisely because it shares nothing else:
`Harvester.harvest(tree, src_bytes)` reads only the file, and payloads are
rowid-free by contract.

**THE PARAMETRIZED HARVESTERS ARE PASSED ON, not rebuilt.** Five stages key on a
declaration's content hash, and those five take the same OBJECT this plan handed
the shared pass. Rebuilding an equal one inside the stage would be a second
chance to disagree about `(stage, stage_version, extra_key)` — and a
disagreement is invisible, because a stage that misses simply parses for itself
and produces the same rows, more slowly. It would also re-run each declaration
merge, including `resolve_shared_key_patterns`' shadowed-default warnings, twice
per build.

The other five take no arguments at all: their key is three class attributes and
an empty `extra_key`, so a separately-constructed instance is the same key by
construction and there is nothing to plumb. They are still built through public
factories, so that this module never reaches into another's privates and so each
class has exactly one construction site.

@brief The build's per-file AST stages, named once for the shared parse pass.
@version 1
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ast_symbols import function_definition_harvester
from .call_edges import call_site_harvester
from .callback_edges import callback_harvester
from .dispatch import DispatchManifest
from .dispatch_edges import dispatch_harvester
from .harvest import Harvester, HarvestTally, run_shared_parse
from .indexcache import IndexCache
from .kconfig_gates import gate_harvester
from .locks import lock_harvester
from .py_entrypoints import main_guard_harvester
from .shared_key_edges import shared_key_harvester, subscribe_harvester
from .threads import spawn_harvester


## @brief Every per-file AST stage of one build, each built exactly once.
## @version 1
@dataclass
class HarvestPlan:
    """The harvesters the pipeline is about to run, held so the shared parse pass
    and the stages themselves use the SAME object.

    `dispatch` and `subscribe` are None when their manifests declare nothing —
    those stages then do no AST work at all, and warming a payload no one will
    read would be pure cost. Every other stage always runs.

    @brief One build's per-file harvesters.
    @version 1
    """

    kconfig_gates: Harvester
    ast_symbols: Harvester
    call_edges: Harvester
    callback_edges: Harvester
    locks: Harvester
    threads: Harvester
    shared_key: Any
    py_entrypoints: Harvester
    dispatch: Harvester | None = None
    subscribe: Harvester | None = None

    ## @brief The stages the shared parse pass should warm.
    ## @return Every non-None harvester in this plan.
    ## @version 1
    ## @req REQ-DDB-PIPE-003
    def active(self) -> list[Harvester]:
        """Order is irrelevant to the shared pass — it warms cache rows and emits
        nothing — so this is simply "all of them that will run".

        @brief The plan's live harvesters.
        @version 1
        """
        return [
            h
            for h in (
                self.kconfig_gates,
                self.ast_symbols,
                self.call_edges,
                self.callback_edges,
                self.locks,
                self.threads,
                self.shared_key,
                self.py_entrypoints,
                self.dispatch,
                self.subscribe,
            )
            if h is not None
        ]


## @brief Build the per-file harvester for every stage this build will run.
## @param lock_patterns Declared `locks:` section, a YAML path, or None.
## @param thread_patterns Declared `threads:` section, a YAML path, or None.
## @param shared_key_patterns Declared shared-key accessor manifest, or None.
## @param shared_key_wrappers The dispatch manifest's `shared_key_wrappers` half, or None.
## @param dispatch The parsed dispatch manifest.
## @param dispatch_key Manifest-derived cache-key component for the dispatch harvest.
## @param mqtt_dispatch The --mqtt-dispatch manifest, or None.
## @return The assembled plan.
## @version 1
## @req REQ-DDB-PIPE-003
def build_harvest_plan(
    lock_patterns: Path | dict | None = None,
    thread_patterns: Path | dict | None = None,
    shared_key_patterns: Path | dict | None = None,
    shared_key_wrappers: Path | dict | None = None,
    dispatch: DispatchManifest | None = None,
    dispatch_key: str = "",
    mqtt_dispatch: Path | dict | None = None,
) -> HarvestPlan:
    """Every declaration is resolved HERE, once, and a `DeclarationError` in any of
    them now refuses the build before doxygen's output is augmented rather than
    part-way down the stage list. That is the right direction for a refusal, and it
    is a behaviour change worth naming: the same bad declaration used to fail later.

    @brief Resolve every declaration and construct all ten harvesters.
    @version 1
    """
    return HarvestPlan(
        kconfig_gates=gate_harvester(),
        ast_symbols=function_definition_harvester(),
        call_edges=call_site_harvester(),
        callback_edges=callback_harvester(),
        locks=lock_harvester(lock_patterns),
        threads=spawn_harvester(thread_patterns),
        shared_key=shared_key_harvester(shared_key_patterns, shared_key_wrappers),
        py_entrypoints=main_guard_harvester(),
        dispatch=(dispatch_harvester(dispatch, dispatch_key) if dispatch is not None else None),
        subscribe=subscribe_harvester(mqtt_dispatch),
    )


## @brief Parse every indexed file once, warming all of the plan's stages.
## @param db_path The database being built (its `path` table names the file set).
## @param repo_root Repository root the indexed paths are relative to.
## @param plan The build's harvester plan.
## @param cache Live index cache; None disables the pass.
## @return The shared pass's tally.
## @version 1
## @req REQ-DDB-PIPE-003
def warm_harvest_plan(
    db_path: Path,
    repo_root: Path,
    plan: HarvestPlan,
    cache: IndexCache | None = None,
) -> HarvestTally:
    """Opens its own connection because it runs between two stages that each own
    theirs, and READS ONLY — the `path` table, to enumerate the file set. Everything
    it writes goes to the sidecar cache, never to the index.

    @brief Drive the shared parse pass over one build's plan.
    @version 1
    """
    from .harvest import try_import_tree_sitter

    ts_classes = try_import_tree_sitter()
    if ts_classes is None:
        return HarvestTally()
    conn = sqlite3.connect(str(db_path))
    try:
        return run_shared_parse(conn, repo_root, plan.active(), ts_classes, cache)
    finally:
        conn.close()
