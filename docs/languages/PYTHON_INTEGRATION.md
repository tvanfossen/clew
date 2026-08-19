<!-- SPDX-License-Identifier: MIT -->
# Python

| | |
|---|---|
| front end | **doxygen** — the same one C and C++ use |
| requires | `doxygen` built with sqlite3 support |
| Doxyfile | optional. A repo shipping none gets one synthesized from its declared scope |

**"C/C++ only" is imprecise — doxygen covers Python.** A Doxyfile-less Python codebase indexes to
thousands of functions plus call edges and prose, and the whole query surface works on it.

## Measured

This repository's own index (Python, whole-repo scope, no Doxyfile):

| | |
|---|---|
| `memberdef` | 5,059 |
| `call_edges` | 5,265 |
| `xrefs` | 2,823 |
| `req_edges` | 547 |
| `threads` · `locks` · `shared_key_edges` | 8 · 1 · 2 |
| barren ratio · undocumented ratio | 0.005 · 0.005 |

Reproduce it with `clew --repo-root .` from a checkout of this repository.

## Docstrings and `##` blocks

doxygen reads both a `##` comment block above a definition and the definition's own docstring.
This repository writes both and bumps `@version` in both when a body changes, because which one a
consumer reads is not reliably predictable and bumping both is monotonic.

Neither is required for indexing. A module with no prose at all still yields symbols, call edges
and liveness; docs fill in `brief` and `detail`.

## File-level docs

A module docstring feeds `search`'s conceptual path — finding a module by what it is *about*
rather than by a name it contains. That is separate from per-symbol `brief`/`detail`, and it is
the highest-value prose in a Python repo for retrieval purposes.

## Reachability

Python gets structural reachability seeds that the C/C++ path does not need: `console_scripts`
entry points declared in `pyproject.toml`, and `if __name__ == "__main__"` guards. Without them a
library whose callers are all external would read as entirely orphaned.

## Both edge layers run, and tree-sitter is the larger one

`tree-sitter-python` is a declared dependency and is registered alongside the C, C++ and Rust
grammars, so Python is **not** a doxygen-only language. On this repository's own index:

| layer | edges |
|---|---|
| `ast` (tree-sitter) | 3,308 |
| `doxygen_sqlite` (`xrefs`) | 1,915 |
| `binding` | 40 |
| `fnptr` | 2 |

`tree-sitter-python` is pinned explicitly rather than left transitive: the grammar importer
swallows `ImportError`, so losing it takes the whole Python AST layer to zero rows **with no
error**.

## Limitations

The richness harvesters — threads, locks, shared-key dataflow, callbacks — were written against C
and C++ idiom and are matched against Python by the same detectors. They are not empty here (the
figures above include thread, lock and shared-key rows) but they are tuned for the C idiom, so
read a sparse causal layer on a Python target as "less well covered", not as a measured negative.

`kconfig` and preprocessor gating do not apply.
