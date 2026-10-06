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

## Docstrings (PEP 257) and `##` blocks

Both work, and a codebase may use either.

- **A `##` block** above a definition is doxygen's own convention, and doxygen parses it fully:
  `@brief`, `@version`, `@req`, aliases. Nothing about it changes.
- **A PEP 257 docstring** is, to doxygen, preformatted text: it lands in the detail as
  `<verbatim>`, the brief stays empty and a `@version` inside it is never parsed. So clew
  reads it itself (`clew/pydocs.py`): where doxygen left a function or class without a brief,
  the docstring's summary line becomes the brief and its `@version` the version. `@req` in a
  docstring already works, because the requirements pass reads the literal tag out of the
  detail.

Where both exist, the `##` block wins, in the index and in the gate. This repository writes
both and bumps `@version` in both when a body changes.

Neither is required for indexing. A module with no prose at all still yields symbols, call edges
and liveness; docs fill in `brief` and `detail`. To gate them, see
[`clew guard`](../GUARD.md#python), where the docstring is the primary form.

## File-level docs

A module docstring feeds `search`'s conceptual path — finding a module by what it is *about*
rather than by a name it contains. That is separate from per-symbol `brief`/`detail`, and it is
the highest-value prose in a Python repo for retrieval purposes.

## Reachability

Python gets structural reachability seeds that the C/C++ path does not need: `console_scripts`
entry points declared in `pyproject.toml`, and `if __name__ == "__main__"` guards. Without them a
library whose callers are all external would read as entirely orphaned.

## Both edge layers run, and tree-sitter is the larger one

Python's tree-sitter layer parses through
[lang-parsing-substrate](https://github.com/brandon-arrendondo/lang_parsing_substrate) (its
Python grammar, via `clew/tsnode.py`), so Python is **not** a doxygen-only language. On this
repository's own index:

| layer | edges |
|---|---|
| `ast` (tree-sitter) | 3,308 |
| `doxygen_sqlite` (`xrefs`) | 1,915 |
| `binding` | 40 |
| `fnptr` | 2 |

`lang-parsing-substrate` is a declared, required dependency. Losing it would take the whole
Python AST layer to zero rows, so the packaging tests check that every grammar the harvest
routes to has a declared provider.

## Limitations

The richness harvesters — threads, locks, shared-key dataflow, callbacks — were written against C
and C++ idiom and are matched against Python by the same detectors. They are not empty here (the
figures above include thread, lock and shared-key rows) but they are tuned for the C idiom, so
read a sparse causal layer on a Python target as "less well covered", not as a measured negative.

`kconfig` and preprocessor gating do not apply.

**Incremental refresh cannot see a NEWLY-ADDED cross-file call here, so it needs a full rebuild
to appear.** A refresh re-runs doxygen over the changed files plus a closure of their neighbours,
and one of the two closure passes walks doxygen's `includes` table to find files whose call sites
may now resolve differently. **That table is populated only from `#include` directives**, so on
Python it is empty and that pass contributes nothing.

Measured on clew's own index, which is a controlled comparison because the same repository holds
both languages: **42 include rows, all 42 from the C/C++ test fixtures and zero from its 208
Python files** (2,130 rows on the C++ target [entropic](https://github.com/tvanfossen/entropic) for
contrast).

Concretely: edit `a.py` to add a call to a function in `b.py`, and the refresh re-indexes `a.py`
and picks up the new call site — that part works, because the changed file is always re-run. What
it cannot do is notice that some *third*, unedited file's view changed as a consequence. The
practical exposure is small for this reason, but it is not nil, and a full build
(`index(action='refresh', force=True)`) closes it. Fixing it properly needs a tree-sitter import
graph rather than doxygen's `includes`.
