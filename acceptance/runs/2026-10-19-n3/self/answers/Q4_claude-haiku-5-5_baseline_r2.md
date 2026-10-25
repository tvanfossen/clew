The answer is a set of **caller functions with a provenance label on each edge**, not a list of call sites. Reading it as call sites is wrong in several specific ways.

I answered from the source and docs in this repo. I did not run `clew` against an index.

**What a caller row contains**

`clew` no longer has a separate `callers` tool. Its `dossier` reply carries `callers` and `callees` fields, plus the body, threads, locks, liveness and requirements for the same symbol. Each edge is stored as `call_edges(caller_rowid, callee_rowid, source, confidence)` (`clew/call_edges.py:4`). So an edge is a pair of functions plus two labels:

- **`source`** says which layer found it: `ast` (bare identifier), `ast_member` (member call recovered by unwrapping), `doxygen_sqlite`, `macro_hop`, `fnptr`, `declared_dispatch`, and others.
- **`confidence`** is `exact`, `resolved` or `fuzzy`. `fuzzy` means the callee name matched several indexed functions and the edge was fanned out to each of them.

The reply also carries `callers_unresolved`, a count of call sites that could not be attached to any indexed function. It returns `None`, not 0, when the index predates that measurement.

**What makes it wrong to read as a call-site list**

1. **Rows are function-to-function, not line-to-line.** The table has no line column, and it is unique on (caller, callee, source). A caller that invokes the target five times is one row.

2. **`fuzzy` is a name guess.** When several functions share a name, each namesake gets a row. A later pass (`clew/dominated_edges.py`) deletes some of these when a stronger layer already named the real callee, but only where such an anchor exists. Surviving fuzzy rows are still guesses.

3. **Shared names pool the neighbours.** If a name matches several signatures, the `ambiguous` block says the rows are shared across all of them. Re-ask with `qualified` before attributing a caller to one function.

4. **An empty `callers` is not "nothing calls this".** Possible causes include unresolved inbound sites (`callers_unresolved`), calls through function pointers, virtual dispatch, macros, and code outside the indexed tree. Check `callers_unresolved` before trusting an empty list.

5. **`exact` is only as good as the layer that produced it.** Member-call edges are graded `resolved` only after receiver narrowing succeeds. Otherwise they stay `fuzzy`.

6. **Coverage depends on language and index age.** Python and Rust do not pick up new cross-file calls until a full rebuild. A stale index is refreshed automatically on query, but only what was indexed is answered.

7. **It is one hop.** `callers` shows direct edges. The README's "transitively, across a function-pointer boundary" claim depends on other tools or walks that I did not trace in this build.

In short: read each row as "this function, by this layer, at this confidence, plausibly calls the target." Treat `fuzzy` rows as candidates to verify, and treat an empty list as "not found in the index", not as "no callers".