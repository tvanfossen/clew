The answer is a list of **caller/callee relationships**, one row per neighbouring function, not a list of call sites. Reading it as call sites gives wrong answers in several ways. This is from reading the source (`clew/query/symbols.py`, `models.py`, `vocabulary.py`, `externcalls.py`), not from running clew against this repo.

**What a row contains** (`CallEdge`, `symbols.py` `_direct_call_edges`)

- The neighbour's name, its identity (rowid, definition location, whether it has a body), and whether it is a declaration or a definition.
- `source`: which extraction layer found it. Layers are ranked `declared_dispatch` > `doxygen_sqlite` > `macro_hop` > `ast` > `binding` > `ast_member` > `fnptr`.
- `confidence`: `exact`, `resolved` or `fuzzy`.
- `implementors`: concrete overrides, as an annotation on the row.
- A macro expansion, where the call came through a macro.
- For `callers`/`callees` only, `edge_class='key'` rows: shared-key dataflow, not calls.

**What makes it wrong to read as call sites**

1. **One row per endpoint, not per site.** `DISTINCT` on the endpoint identity means a function that calls `f` three times appears once. Counting rows does not count call sites.
2. **`'key'` rows are not calls.** A key neighbour writes or reads a shared value with no call between them. It may run asynchronously and on another thread. `CallEdge` says this explicitly.
3. **Fuzzy edges are kept in `callers`/`callees`.** The source says 21.3% of clew's own call edges are fuzzy, and 79.8% on a large C++ target. `chain_trace` filters them out; the flat list does not. Weigh `confidence` yourself.
4. **Same-name ambiguity.** `callers(fn)` without `qualified` unions every function with that name. `name_ambiguity()` reports when that is happening. The source cites a real case where `dossier("_classify")` mixed in another module's function.
5. **An empty list does not mean nothing calls it.** Some callers may fail to resolve. `unresolved_inbound_for_rowids()` returns the count of refused call sites, or `None` if the index predates that measurement. Empty `callees` has the same problem: `call_edges.callee_rowid` is NOT NULL, so calls into unindexed code such as libc are not representable. `externcalls` recovers bare-identifier names for those, but not as edges.
6. **Presence is not reachability.** A row says a call exists in the graph. It says nothing about whether that path runs. Function-pointer hops are the weakest layer.

**Working rule:** treat the answer as a candidate set with provenance. Check `edge_class`, `confidence`, `source` and `qualified`, and whether an unresolved count is present. Use the `unresolved` count and `externcalls` to judge what is missing.