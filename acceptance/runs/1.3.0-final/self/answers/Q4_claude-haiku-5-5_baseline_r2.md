Short answer: the `callers` field is a list of name-resolved, graded graph edges, not a list of verified call sites. Each entry says which extraction layer produced it and how sure clew is about it, so you can tell a direct call from an inferred one.

I answered from the source and docs in this checkout. I did not run a live query against a built index.

**What the answer contains**

`dossier` returns `callers` and `callees` alongside the body, locks, threads, requirements and liveness. Each neighbour is a `CallEdge` (`clew/query/models.py`) with:

- `name` and `rowid`
- `source`: the layer that found it
- `confidence`: `exact`, `resolved` or `fuzzy`
- `via_macro` and `via_macro_expansion`, when the call is written as a macro invocation
- `implementors`, for virtual endpoints (an annotation, not an edge)

The layers, from `clew/call_edges.py` and the language docs:

| `source` | What it means |
|---|---|
| `doxygen_sqlite` | Doxygen cross-reference, `exact` |
| `ast` | Tree-sitter, bare-identifier callee; `resolved` if unique, `fuzzy` if the name is shared |
| `ast_member` | Callee unwrapped from `obj.f()` or `Ns::f()` to its tail; mostly `fuzzy` on C++ |
| `macro_hop` | Call reached through a macro; no matching text in the caller's body |
| `fnptr` | Registered callback, `GLOBAL = PARAM` then `GLOBAL(...)` |
| `declared_dispatch`, `binding` | Inferred links through declared dispatch or bindings |

One row is stored per layer per pair, but the reply collapses them to the strongest evidence per endpoint (`CallEdge` docstring). Clew's own index has 520 rows for 260 distinct pairs, so a row count is not a relationship count.

**What makes it wrong to read as a list of call sites**

1. **Resolution is by name, not identity.** Several unrelated file-private helpers with the same name collapse into one node, and their edges merge at full confidence. `candidates` disambiguates which symbol you asked about, not its edges (`CPP_INTEGRATION.md`, "Overloads").
2. **Not every neighbour is a call.** `key` rows are shared-key dataflow with no call between the endpoints; they may be asynchronous and cross threads. `implementors` names possible override bodies and asserts nothing about which runs. `fnptr`, `binding` and `declared_dispatch` are inferred through pointers or registrations, not written at the call site.
3. **Confidence grades the link, not the code.** A `fuzzy` edge is a name match that might be wrong. A `resolved` edge can still be wrong if it was built on a shared name.
4. **An empty or short list is not proof of none.** Causes include:
   - `#if` blocks whose macro is not predefined (the preprocessor and Kconfig gating).
   - Functions defined by macros, which the `memberdef`-based detector cannot see.
   - Python: incremental refresh misses a new cross-file call until a full rebuild, and entry points only count via the `console_scripts` and `__main__` seeds.
   - Callers in code that was never indexed.
5. **Callees that do not resolve are not edges.** `external_callees` is recovered by name at query time and kept out of `callees` on purpose; calls to libc primitives are invisible in the graph.
6. **Self-edges are filtered.** A `caller == callee` row survives only if the body contains a self-directed call. Unparseable files keep their edges untouched rather than being pruned.
7. **Staleness.** `anchor_mismatch: true` means the file changed since the build, so the lines and neighbours may belong to something else.
8. **Caps.** Batch fan-out can be trimmed with `_limited` naming what was dropped. Detail prose is cut at 4,000 characters with a notice.

**How to read it**

Treat `callers` as candidate call sites ranked by evidence. For a `fuzzy` or `macro_hop` entry, read the caller's body before relying on it. For an empty list, first check whether the detector could see the code at all (preprocessor gating, macro definitions, language coverage) before concluding nothing calls it.