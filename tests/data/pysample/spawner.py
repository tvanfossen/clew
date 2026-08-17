# SPDX-License-Identifier: MIT
"""Minimal Python fixture for the R1 richness layers (task #58).

Mirrors what `sample/` is for C: the smallest source that exercises each
detector, kept deterministic so the tests can assert exact rows. It is a
SEPARATE fixture because CLAUDE.md forbids enriching `sample/` — demobot's
committed shape is itself a fixture other tests depend on.

Every construct here is present because a test asserts on it:
  - `threading.Thread(target=...)` — module-qualified, keyword entry.
  - `Thread(target=...)` after `from threading import Thread` — the bare form
    that only resolves through this file's own import.
  - `Poller.start` / `Reader.start` both spawn `self._run`, so the two threads
    must resolve to DIFFERENT rowids or the class-qualification is broken.
  - `multiprocessing.Process` → kind 'process'; `asyncio.create_task` →
    'coroutine'; `ThreadPoolExecutor.submit` through a `with`-bound receiver →
    'task'. Each takes a DIFFERENT entry function, so the four threads carry
    four different names and the kind mapping is assertable per primitive.
  - a single-call lambda entry (resolves) and a MULTI-call lambda entry (must
    produce no thread at all).
  - `Decoy(target=noop)` where `Decoy` is imported from `.models` — a
    same-shaped constructor that must be REFUSED.
  - a `__main__` guard, for the reachability seed.

NOT executed by the test suite — it is parsed. It is nonetheless valid,
importable Python so a reader can reason about it.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor
from threading import Thread

from .models import Decoy


## @brief A no-op callable used as a spawn entry.
## @version 1
def noop() -> None:
    """@brief Do nothing.

    @version 1
    """
    return None


## @brief A second no-op, used as a lambda-body callee.
## @version 1
def helper() -> None:
    """@brief Do nothing, separately.

    @version 1
    """
    return None


## @brief A free function used as a positional/keyword thread entry.
## @version 1
def worker() -> None:
    """@brief Do nothing, as a thread body.

    @version 1
    """
    return None


## @brief The `multiprocessing.Process` entry.
## @version 1
def child_task() -> None:
    """A DISTINCT entry per primitive, on purpose. When every spawn in
    `spawn_all` shared one entry, all four threads fell back to the same
    qualified-entry name and the kind mapping became untestable — and, before
    `threads.UNIQUE` gained `kind`, three of the four rows were silently
    discarded with the survivor chosen by AST walk order.

    It also keeps the one bare-identifier call site the `ast`-vs-`ast_member`
    provenance test needs: `worker` is otherwise only ever REFERENCED
    (`target=worker`), never called.

    @brief Process entry; calls `worker` as a plain identifier.
    @version 1
    """
    worker()


## @brief The `asyncio.create_task` entry.
## @version 1
async def coro_body() -> None:
    """`async def` so `create_task(coro_body())` is real Python: the argument
    must be a coroutine object, which is what calling an async function yields.

    @brief Coroutine entry for the create_task spawn.
    @version 1
    """
    return None


## @brief The `ThreadPoolExecutor.submit` entry.
## @version 1
def pool_job() -> None:
    """@brief Work item submitted to the pool.

    @version 1
    """
    return None


## @brief Spawns threads whose entry is its OWN `_run`.
## @version 1
class Poller:
    """@brief One of two classes defining `_run`, to prove class-qualification.

    @version 1
    """

    ## @brief The poller's loop body.
    ## @version 1
    def _run(self) -> None:
        """@brief Poller loop.

        @version 1
        """
        return None

    ## @brief Spawn the poller thread with a named literal.
    ## @version 1
    def start(self) -> None:
        """@brief Start the poller thread.

        @version 1
        """
        threading.Thread(target=self._run, name="poller").start()


## @brief Spawns a thread whose entry is a DIFFERENT `_run`.
## @version 1
class Reader:
    """@brief The second `_run` definer; must not share Poller's rowid.

    @version 1
    """

    ## @brief The reader's loop body.
    ## @version 1
    def _run(self) -> None:
        """@brief Reader loop.

        @version 1
        """
        return None

    ## @brief Spawn the reader thread, unnamed (named by qualified entry).
    ## @version 1
    def start(self) -> None:
        """@brief Start the reader thread.

        @version 1
        """
        threading.Thread(target=self._run).start()


## @brief Spawns one of every other supported primitive.
## @version 1
def spawn_all() -> None:
    """Each call is a distinct primitive so one test can assert the whole kind
    mapping at once.

    @brief Spawn each remaining Python primitive.
    @version 1
    """
    Thread(target=worker).start()
    multiprocessing.Process(target=child_task).start()
    asyncio.create_task(coro_body())
    with ThreadPoolExecutor() as pool:
        pool.submit(pool_job)


## @brief A single-call lambda entry, which resolves to that callee.
## @version 1
def spawn_single_lambda() -> None:
    """@brief Spawn with a one-call lambda body.

    @version 1
    """
    threading.Thread(target=lambda: helper()).start()


## @brief A multi-call lambda entry, which must be refused.
## @version 1
def spawn_multi_lambda() -> None:
    """Two calls in the body make the entry ambiguous ("which is the loop?"), so
    the layer must produce NO thread rather than pick one.

    @brief Spawn with an ambiguous multi-call lambda body.
    @version 1
    """
    threading.Thread(target=lambda: (noop(), helper())).start()


## @brief Constructs a look-alike that must NOT become a thread.
## @version 1
def spawn_decoy() -> None:
    """`Decoy` is imported from `.models` and merely takes a `target=` keyword.
    Keyed on the bare tail it would look exactly like a spawn; resolved through
    this file's imports it is `.models.Decoy` and matches nothing. This is the
    committed regression for the real bug clew's own `Thread` dataclass posed.

    @brief Construct a same-shaped non-thread.
    @version 1
    """
    Decoy(target=noop)


## @brief The module's entry point, invoked only by the `__main__` guard.
## @version 1
def guarded_main() -> None:
    """Reached from no function, only from the guard below — the reachability
    seed case.

    @brief Module entry point.
    @version 1
    """
    spawn_all()


if __name__ == "__main__":
    guarded_main()
