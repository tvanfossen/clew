The answer is not a list of call sites. It is a list of **caller functions**, each tagged with how clew found the link and how sure it is. Read the tags before counting anything.

**What `dossier` returns for callers**

`dossier` is the only tool that answers "who calls this". There is no separate `callers` tool in the served surface (README, "The four tools"). Its `callers` field is a list of `CallEdge` rows (`clew/query/models.py:145`), and each row carries:

- `name` and `rowid`: the caller function, resolved by identity.
- `source`: the layer that found the edge, such as `doxygen_sqlite`, `ast`, `ast_member`, `fnptr` or `macro_hop`.
- `confidence`: `exact`, `resolved` or `fuzzy`, describing the strongest evidence for that endpoint.
- `edge_class`: always `'call'` in `dossier`. Dataflow neighbours go to the separate `writes`/`reads` fields.
- `implementors`: present only when doxygen records overrides of the endpoint. It is an annotation, not an extra edge.

The reply also has `callers_unresolved`, the count of call sites that named the function but failed resolution. It is `None` when the index predates that measurement, and `0` is a real measured zero.

**What makes it wrong to read as a call-site list**

1. **Rows are per caller function, not per call.** `_direct_call_edges` keeps one row per endpoint identity. Five calls from one function are one row. The row count is not a call count.

2. **`fuzzy` is not filtered here.** Unlike `chain_trace`, this surface keeps fuzzy edges on purpose. The code comment says 21.3% of clew's own call edges are fuzzy, and 79.8% on a large C++ codebase. A fuzzy caller is a name match that was never confirmed against the receiver's class. You have to weigh `confidence` on every row.

3. **Macro hops are not textual calls.** A `macro_hop` edge means the caller reaches the callee through a macro. The caller's body may never name the callee. The table stores `via_macro_rowid`, but I did not confirm that it reaches the `dossier` wire output.

4. **An empty list is not a proof of no callers.** It can mean the true caller is outside `index_scope`, or that resolution refused the site. Check `callers_unresolved` before believing an empty result. Function-pointer callers exist only if the registration was harvested (`fnptr`).

5. **Same-name functions are separated, but only by identity.** Callers are selected by resolved rowid (gh#26), so `dossier("_classify")` does not mix up three unrelated functions. If the name is ambiguous, `candidates` lists the alternatives, and you must re-query with `qualified`. Otherwise you may be reading callers of the wrong overload.

**Caveat on this answer:** I read the code and the README and did not run clew against this repository. The claims above come from the source comments and the code paths I read (`call_edges.py`, `query/symbols.py`, `query/dossier.py`, `query/models.py`).