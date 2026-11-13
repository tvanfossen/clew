# SPDX-License-Identifier: MIT
"""OS file-change events that wake the server's refresh loop the moment a file is saved.

1.3.6, Track 2 (owner 2026-11-13: the `watchdog` dependency). Before this, a save was noticed
only when a query arrived or the 15-second stat sweep ran — and the sweep stats every indexed
file. With the fast tier landing a one-file refresh in well under a second, the remaining delay
between a save and a current index was the WAIT, not the work. An inotify / FSEvents /
ReadDirectoryChangesW watch on each repository this session has answered from removes it.

THE WATCH ONLY WAKES; it decides nothing. The refresh loop it wakes measures staleness exactly as
before (`_data_stale`, `_derived_pending`), so an event for a file the index does not cover — a
build artifact, an editor swap file — costs one cheap check and no build. Events inside `.git`
and inside any `.clew*` / index directory are dropped before they wake anything, because a
refresh writes its own index and would otherwise wake itself forever.

A watch that cannot start (no inotify slots left, an unsupported filesystem) is LOGGED and the
loop keeps its interval sweep: slower, never broken.

@brief Repository file-change watching for the refresh loop.
@version 1
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger("clew")

## Path components whose events never wake the loop: version-control internals and the index's
## own writes (a refresh would otherwise re-trigger itself).
_IGNORED_PARTS = frozenset({".git", "__pycache__", ".pytest_cache", "node_modules"})


## @brief Whether a changed path should wake the refresh loop.
## @param path The changed path, as watchdog reports it.
## @return True when it could be an indexed source file.
## @version 1
## @dg_internal
def relevant(path: str) -> bool:
    """@brief Filter out VCS internals, caches and clew's own index files. @return True if relevant."""
    parts = Path(path).parts
    if any(p in _IGNORED_PARTS for p in parts):
        return False
    name = parts[-1] if parts else ""
    return not (
        name.startswith(".clew")
        or ".idxcache" in name
        or name.endswith((".db", ".db-journal", ".db-wal"))
    )


## @brief Watches a set of repository roots and calls back on any relevant change.
## @version 1
class RepoWatcher:
    """ONE OBSERVER, ONE SCHEDULED WATCH PER ROOT, reconciled against the session's working set
    by `sync` — a root the session stops using is unscheduled, so a long-lived server does not
    accumulate watches.

    @brief File-change watcher over the session's repositories.
    @version 1
    """

    ## @brief Prepare a watcher that calls `on_change` from watchdog's thread.
    ## @param on_change Thread-safe callback taking no arguments.
    ## @version 1
    ## @dg_internal
    def __init__(self, on_change: Callable[[], None]) -> None:
        self._on_change = on_change
        self._observer: Any = None
        self._watches: dict[str, Any] = {}

    ## @brief Watch exactly these roots: schedule new ones, unschedule dropped ones.
    ## @param roots Repository roots the session has answered from.
    ## @return None.
    ## @version 1
    ## @req REQ-DDB-INDEX-006
    def sync(self, roots: set[str]) -> None:
        """NEVER RAISES: a root that cannot be watched is logged and left to the interval sweep.

        @brief Reconcile the scheduled watches.
        @return None.
        @version 1
        """
        observer = self._ensure_observer()
        if observer is None:
            return
        for root in sorted(set(self._watches) - roots):
            observer.unschedule(self._watches.pop(root))
        for root in sorted(roots - set(self._watches)):
            try:
                self._watches[root] = observer.schedule(self._handler(), root, recursive=True)
            except Exception as exc:  # inotify limits, vanished directory, unsupported fs
                logger.warning(
                    "file watch on %s could not start (%s); its index is kept current by the "
                    "interval sweep instead",
                    root,
                    exc,
                )

    ## @brief Stop watching everything.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def stop(self) -> None:
        """@brief Stop the observer thread. @return None."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            self._watches.clear()

    ## @brief The running observer, started on first use; None when watchdog cannot start one.
    ## @return The observer or None.
    ## @version 1
    ## @dg_internal
    def _ensure_observer(self) -> Any:
        """@brief Lazily start the observer. @return Observer or None."""
        if self._observer is None:
            try:
                from watchdog.observers import Observer

                self._observer = Observer()
                self._observer.daemon = True
                self._observer.start()
            except Exception as exc:
                logger.warning("file watching unavailable (%s); using the interval sweep", exc)
                self._observer = None
        return self._observer

    ## @brief A watchdog event handler that forwards relevant changes.
    ## @return The handler.
    ## @version 1
    ## @dg_internal
    def _handler(self) -> Any:
        """@brief Build the forwarding handler. @return Handler."""
        from watchdog.events import FileSystemEventHandler

        on_change = self._on_change

        class _Forward(FileSystemEventHandler):
            """@brief Forward relevant file events. @version 1"""

            def on_any_event(self, event: Any) -> None:
                """@brief Wake the loop for a relevant non-directory change. @return None."""
                if not event.is_directory and relevant(str(event.src_path)):
                    on_change()

        return _Forward()
