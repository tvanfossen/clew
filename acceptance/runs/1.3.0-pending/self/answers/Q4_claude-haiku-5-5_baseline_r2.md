**Short answer:** a `callers` result is a list of neighbouring functions, one row per caller-callee pair, each with a provenance label and a confidence grade. It is not a list of call sites. It also mixes in edges that are not calls, and an empty list does not mean nothing calls the function.

I answered from the source (`clew/query/models.py`, `clew/query/symbols.py`, `clew/query/dossier.py`, `clew/call_edges.py`). I did not run clew against this tree.

## What is in the answer

For each neighbour, a `CallEdge` carries:

| Field | Meaning |
|---|---|
| `name`, `rowid` | The other function, by name and identity. |
| `edge_class` | `'call'` for a direct call, `'key'` for a shared-key dataflow edge with no call between the two. |
| `source` | Which layer found it: `doxygen_sqlite`, `ast`, `ast_member`, `fnptr`, `macro_hop`, `declared_dispatch`, `binding`. |
| `confidence` | `exact`, `resolved` or `fuzzy` (for call edges). |
| `via_macro`, `via_macro_expansion` | Set when a macro invocation produced the hop. The expansion is doxygen's text, quoted verbatim. |
| `implementors` | For a virtual endpoint, the known overriding bodies. An annotation, not an edge. |

The `dossier` also carries `callers_unresolved` (a count of call sites that named this function but did not resolve), `external_callees`, `macro_collision`, and `context_conflicts`. `name_ambiguity` is computed separately at the MCP layer.

## What makes it wrong to read as call sites

1. **One row per pair, not per site.** `UNIQUE(caller, callee, source)` collapses a caller that calls the function five times into one row. `CallEdge` has no line number, so you cannot see where in the caller the call happens.

2. **Namesakes are linked.** An `ast_member` edge keeps only the unqualified tail of `obj.method()` and never checks the receiver's type. Every same-named function gets an edge from every such site. The model's own example: `Get` matches 33 functions and accumulates 162 callers, of which at most one per site is real. `confidence='fuzzy'` flags this but does not give the count. `name_ambiguity` does.

3. **Empty does not mean none.** `callers: []` means "nothing calls this" only when `callers_unresolved` is 0. `None` means the index predates the measurement, so the absence of a count proves nothing.

4. **Not every row is a caller.** `callers()` also returns `'key'` rows: functions that write a value this one reads. They do not call it, and may run on another thread. `dossier` keeps them out of `callers` and reports them under writes/reads, but the library function merges them. Check `edge_class` on every row.

5. **Indirect dispatch is attributed by resolution, not by path.** `fnptr` edges resolve a call through a function pointer to the function registered in the callback layer. The list does not say which registration site or which thread.

6. **Macro hops have no text in the caller.** A `macro_hop` row exists because a macro invocation expands to a call. Without `via_macro` a reader sees a `resolved` edge with no visible call.

7. **Liveness is a separate question.** A caller in the list may be dead code. Reachability lives in its own field.

8. **It is a snapshot.** Queries refresh a stale index first. The README says a newly added cross-file call in Python or Rust is not seen until a full rebuild, because the include-graph pass reads `#include`, which those languages lack there.

## Practical reading

Treat `callers` as "these functions probably reach this one, here is how sure the index is, and here is how many sites it could not place." Before quoting a count or saying something is unused, check `edge_class`, `confidence`, `callers_unresolved`, and whether the name is ambiguous. For a line-level answer, go to the source.