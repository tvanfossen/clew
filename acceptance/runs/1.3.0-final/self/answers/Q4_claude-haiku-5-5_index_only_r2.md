**What's in the answer**

`callers(db, fn, qualified)` in `clew/query/symbols.py:756` returns a list of `CallEdge` rows. Despite the name, it is not only call sites. It is "everything that causally precedes `fn`": direct call edges (`edge_class='call'`) plus writers of shared keys whose values `fn` reads (`edge_class='key'`). A `'key'` row does not call `fn` and may run on another thread. The docstring tells you to check `edge_class` on every row, so reading the list as calls is the first mistake to avoid.

Each row also carries the layer that produced it and a confidence. The dossier for `callers` shows `_call_edges` (doxygen_sqlite, exact) and `connect` (ast, resolved). `_callers_of` in `clew/dispatch_edges.py:194` shows the same caller can appear once per extraction layer, and the strongest confidence is kept. Virtual and function-pointer dispatch appear as synthetic edges whose confidence is the weakest link in their premise, so a high-confidence-looking edge can rest on a fuzzy name match.

`qualified` selects among same-named functions, but it narrows only the `'call'` rows, not the `'key'` rows.

**What would make it wrong to read it as a list of call sites**

1. **Key rows are not callers.** A `'key'` row means a value flows from that writer to `fn`. It says nothing about who invokes `fn`.
2. **Empty is not a negative.** `callers: []` means "nothing recorded", not "nothing calls this". The `callers` function itself is a live example: its dossier returns `callers: []` with `callers_unresolved: 16`, meaning 16 call sites named a function that did not resolve to a specific one. The file `tests/test_unresolved_inbound.py` exists for this exact reading (gh#15). An empty list with `callers_unresolved: 0` is a measured negative. Without that count, the empty list cannot be taken as absence.
3. **Edges are only as good as their resolution.** Member calls through pointers or references resolve only when the receiver's declared type pins the class. Callers reached through function pointers or callbacks are missed or appear only via dispatch edges. The reachability note also says functions with no non-fuzzy callers are "likely library APIs or callbacks".
4. **Scope is the index.** A caller outside the indexed file set is not in the list. `test_a_callee_outside_the_index_records_nothing` covers this.
5. **Same-name collisions.** Without `qualified`, same-named functions can merge. Use `candidates` to see which identity you have.
6. **Noise exists in the raw layer.** The `test_self_edges.py` note records that of 37 self-edge `callers` rows in one measurement, only 10 were genuine. The rest were `obj.name()` on another object or `super().__init__()`. Caller rows are measurements with known false positives, not verified sites.

**Reading it correctly:** check `edge_class`, check `confidence` and the layer, and check `callers_unresolved` before treating an empty list as meaningful. For a specific call site, read the body at the reported line range rather than trusting the list alone.

I answered from the index only, so I have not checked these edges against the source text.