The answer is a list of **caller symbols with provenance**, not a list of call sites. Each entry carries only a name, file, `source` (the extraction layer, e.g. `doxygen_sqlite`), `confidence` (e.g. `exact`) and `edge_class` (e.g. `call`). No line numbers, no argument positions, no call-site text. I checked this against `dossier` on `_callers_of`, which returns one caller, `_interface_edges`, with those fields only.

**What else the answer carries**

| Field | Meaning |
|---|---|
| `callers` | Direct upstream neighbours, capped by `max_neighbors` (default 8) |
| `edge_class` | Distinguishes a call from other causal edges. `callers` is documented as "callers plus the writers it reads from", so a writer can appear in the list. |
| `confidence` | Strongest incoming edge kept when several layers recorded the same caller |
| `callers_unresolved` | Count of inbound references that failed to resolve. Not returned as call sites. |
| `callers_note` / `_empty_callers_note` | Warns when an empty list is a modelling gap, not a real absence |
| `candidates` | Set when the name matches several symbols. Neighbour rows are then shared across them. |
| `overrides` / `overridden_by` | Virtual-dispatch relations |

**What would make it wrong to read as call sites**

1. **Empty does not mean unused.** Brace-initialised construction (`T x{...}`) is not modelled as a call edge. The `callers_note` says so for constructors. `T(...)` and `make_unique<T>` do resolve. An empty list can also mean every inbound reference failed to resolve, which is what `callers_unresolved` and the empty-list note exist to separate.
2. **It is a symbol-level graph.** You get "function A calls B", not "A calls B at file:line". Multiple call sites inside A collapse to one entry.
3. **Mixed edge kinds.** A writer that shares a key with the subject is in the same list as a true caller. Filter on `edge_class` before counting.
4. **Confidence is the weakest link, not a runtime fact.** A synthetic edge through an interface method carries the confidence of its premise. An `exact` label means the static extraction is exact, not that the call happens at runtime.
5. **Virtual and function-pointer calls are edges only after resolution.** A virtual call lands on the interface method and is continued by a later dispatch stage. Function-pointer dispatch is covered by a test (`test_callers_includes_fnptr_dispatch`).
6. **Truncation.** The default cap is 8 neighbours. I did not confirm from these replies whether a truncation marker appears on `callers`, so check `max_neighbors` before treating a short list as complete.
7. **Depth.** These are direct callers. Transitive callers need `depth >= 2` with `direction='back'`, which adds a `chain`.
8. **Namesakes.** If `candidates` is present, the callers belong to a resolved identity only if you pass `qualified`. Otherwise the list may belong to a different overload.

In short: read the answer as "these symbols have a recorded inbound edge of this kind, at this confidence, from this layer". An empty or short list is evidence only after checking `callers_unresolved`, the constructor note, `candidates` and the cap.