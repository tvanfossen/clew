The answer is a one-hop, name-resolved list of causal neighbours, not a list of call sites. I read this from the source (`clew/query/symbols.py`, `clew/query/models.py`, `clew/mcp_server/tools_query.py`) and did not run clew against the repo.

**What `callers(fn)` returns**

Each row is a `CallEdge`, and the fields are:

- `name`, `rowid`: the neighbouring function, resolved by identity.
- `edge_class`: `'call'` or `'key'`. This is the field to check first.
- `source`, `confidence`: for `'call'` rows, the doxygen layer that found the edge and `exact`/`resolved`/`fuzzy`.
- `strength`, `key_name`, `edge_kind`, `dispatch_mode`, `edge_triggered`, `crosses_thread`, `to_thread`: for `'key'` rows, the shared-key details.
- `implementors`: on a virtual endpoint, the overrides doxygen's `reimplements` relation names. It annotates the edge and is not an edge of its own.

There is no file, line or call-site location in the row. You learn who is on the other end, not where the call happens. One row is kept per endpoint identity, not per layer, so the two doxygen layers do not double-count an edge.

**What makes it wrong to read as a list of call sites**

1. **`'key'` rows do not call `fn`.** `callers()` deliberately merges in functions that write a shared key `fn` reads, with no call between them. The docstring says such a neighbour "does NOT call `fn` and may run on another thread". Counting every row as a caller overstates the call graph.

2. **Fuzzy edges are not filtered.** `callers` keeps `confidence='fuzzy'` rows. The code comment gives 21.3% of clew's own call edges and 79.8% of a C++ target's (entropic) as fuzzy. Traversal code filters them, but the flat list does not, so the consumer has to weigh `confidence`.

3. **An empty list is not a measured "no callers".** `_empty_callers_note` and `_refusal_note` exist because of this:
   - A constructor appears as an empty caller list when brace-initialisation sites are not call edges (gh#4). A name that is also a class is flagged.
   - Calls through pointer or reference receivers resolve only when the declared type pins the class. Refused sites are counted in `callers_unresolved`, and a non-zero count means the empty list is not a negative.
   - `None` for that count means the index predates the measurement, not "zero refusals".

4. **Same-named functions can merge.** Without `qualified=`, overloads or same-named functions can share a result. Member-call rows recovered from an unqualified tail can belong to several of them at once. The `qualified` selector narrows `'call'` rows but not `'key'` rows, because the key join is on `memberdef.name` (a known gh#26-shaped gap). A `'key'` row is therefore the union over every function with that name.

5. **It is one hop.** `callers` is a flat neighbour list. Multi-hop `chain_trace` follows different rules, and it filters fuzzy edges because each hop expands.

**How to read it**

Split the rows by `edge_class`. Treat `'call'`/`exact` and `'call'`/`resolved` as the call sites. Treat `'call'`/`fuzzy` as candidates to check by reading the body. Treat `'key'` rows as data-flow neighbours that may be asynchronous. Treat an empty result as "not established" whenever `callers_unresolved` is positive, the name is also a class, or the name is ambiguous.