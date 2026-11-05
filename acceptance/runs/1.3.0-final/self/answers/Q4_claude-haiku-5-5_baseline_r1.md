The answer is a list of **caller functions with provenance**, not a list of call sites. Each row is one endpoint, and the row carries enough metadata to show how much weight it deserves. I worked from the source (`clew/query/symbols.py`, `clew/call_edges.py`, `clew/dispatch_edges.py`, and the docs), not by running the tool.

**What a row contains**

Each row is a `CallEdge` with the caller's name and definition, an `edge_class` (`call` or `key`), a `source` naming the layer that found it, and a `confidence` of `exact`, `resolved` or `fuzzy`. Callers may also carry `implementors` (concrete overrides, when doxygen records them). Key-class rows carry the shared key and thread information.

The sources are not equivalent:

| source | what it means |
|---|---|
| `doxygen_sqlite` | doxygen's own cross-reference, `exact` |
| `ast`, `ast_member` | tree-sitter recovery; `ast_member` unwraps member/qualified callees and is mostly fuzzy on large C++ |
| `macro_hop` | the call is written inside a macro |
| `fnptr` | inferred from a registered callback |
| `declared_dispatch` | synthesized from an owner's `dispatch:` manifest; it records the owner's claim, not an observed call |

**Why it is not a list of call sites**

1. **One row per endpoint identity, not per site.** `_direct_call_edges` collapses duplicates across layers and across a function's declaration and definition rows. A caller that invokes `fn` five times appears once.
2. **It mixes in non-callers.** `callers()` also returns `edge_class='key'` rows: functions whose shared-key write `fn` reads. They do not call `fn` and may run on another thread. The docstring says to check `edge_class` on every row.
3. **Fuzzy edges are not filtered.** Traversal (`chain_trace`) drops them. The flat list keeps them, because filtering would remove 21.3% of this repo's edges and 79.8% of a real C++ target. Weighing `confidence` is the reader's job.
4. **Same-named functions merge.** `callers`/`callees` resolve by name. Unrelated file-private helpers that share a name collapse into one node with merged edges, at full confidence. `qualified` narrows only the call half; the key half still unions every same-named function (the gh#26 gap noted in `_call_edges`).
5. **Synthesized edges look like observations.** `macro_hop`, `fnptr` and `declared_dispatch` are inferences, and the answer does not render that distinction beyond the `source` field.
6. **An empty list is not "no callers".** `unresolved_inbound` counts call sites that named the function but produced no surviving edge. `0` is a measured negative; `None` means this index never measured it. Read the count before concluding nothing calls the function.
7. **It is a snapshot.** The index is built at a commit. `CORE_HYPOTHESIS.md` notes that a new call site in a changed file produces a silently short list, which invalidity flags do not catch well.

**Reading it correctly:** treat `callers` as a deduplicated, ordered set of causal predecessors. Check `edge_class` for each row, check `confidence` and `source`, check `unresolved_inbound` before trusting an empty result, and do not read a short list on a common helper name as complete.