**Short answer:** `callers` returns a list of causal neighbours, not a list of call sites. Each row says where the edge came from, how precisely its endpoint was resolved, and whether it is a call at all. Several things in that list make a plain "A calls B" reading wrong.

**What a row contains** (`CallEdge`, `clew/query/models.py:145`; built in `_direct_call_edges`, `clew/query/symbols.py:389`)

| Field | Meaning |
|---|---|
| `name`, `rowid` | The neighbour, one row per distinct endpoint identity (name plus definition), not per name. |
| `edge_class` | `'call'` for a synchronous call, or `'key'` for a shared-key dataflow hop. `callers` returns both. |
| `source` | Which layer found it: doxygen xrefs, tree-sitter, function-pointer resolution, binding, and so on. |
| `confidence` | `exact`, `resolved` or `fuzzy`. The vocabulary says this is "how precisely the callee rowid was resolved (NOT how likely the call is real)" (`clew/vocabulary.py`, `CALL_MATCH`). |
| `implementors` | Known overrides of a virtual endpoint, from doxygen's `reimplements`. This is an annotation, not an edge. |
| `via_macro` | The macro and its expansion, when the call is written as a macro invocation and so does not appear in the caller's text. |
| `key_name`, `dispatch_mode`, `crosses_thread`, `to_thread`, `strength` | Present on `'key'` rows only. |

Through `dossier`, the same answer also carries the body, brief, both edge directions, locks, thread, requirements, `gated_by` (the `#if` gates covering the function), and `callers_unresolved` (`clew/query/dossier.py:640`).

**What makes it wrong to read as a list of call sites**

1. **`'key'` rows are not calls.** A writer of a key the function reads appears in `callers` with no call connecting them. It may run asynchronously or on another thread. Check `edge_class` before reading "calls".
2. **`fuzzy` is not filtered here.** The query deliberately keeps fuzzy edges. The code says 21.3% of clew's own call edges are fuzzy, and 79.8% on a large C++ target. A fuzzy row is a candidate that may be the wrong function. Only `confidence` tells you which rows to distrust.
3. **`exact` and `resolved` do not mean "really called".** They describe how well the name was pinned down, not whether the call happens at runtime.
4. **An empty list is not "nothing calls it".** `callers_unresolved` counts call sites that named this function but did not resolve. `None` means the index predates that measurement, so the answer is unknown, not zero. The `unresolved_inbound` table is the basis for this (`clew/query/symbols.py:348`).
5. **Same-named functions can blur together.** `name_ambiguity` (`clew/query/symbols.py:1959`) reports when neighbours arrive through a shared name. The `qualified` selector narrows the focal side only, and dataflow rows are not narrowed.
6. **Virtual dispatch is not resolved.** A call to a base method does not say which override runs. `implementors` lists the candidates, and the confidence stays on the call.
7. **Function-pointer callers can be missing.** When a callback is registered out of repo, it is recorded as a terminus, not as a caller edge. A function invoked only through a pointer can therefore show no callers.
8. **It is one hop, and the graph reflects one configuration.** Code the preprocessor excluded is not in the graph, which is why `gated_by` exists. Liveness (reachability) is a separate layer, so a caller being listed does not mean the caller runs.
9. **The index can be stale or truncated.** A stale query refreshes first. New cross-file calls in Python and Rust need a full rebuild. The MCP boundary applies a response byte budget, so long lists may be cut.

**Practical reading:** treat `callers` as candidate causal predecessors. Filter on `edge_class == 'call'` and `confidence != 'fuzzy'` when you need a confident call list. Check `callers_unresolved` before believing an empty result, and go to source for anything that matters.

I read the code and docs but did not run the tool against a database, so the behaviour above comes from the source and its comments, not from a live query.