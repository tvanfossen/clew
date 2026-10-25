**What's in the answer.** `dossier` on a function returns its `callers` as a list of `CallEdge` rows. Each row names the caller, its source (`doxygen_sqlite` or `ast`), a `confidence` (`exact` or `resolved`), and an `edge_class`. The list is not only calls. `callers()` at `clew/query/symbols.py:756` is documented as "everything that causally precedes `fn`": it returns direct call edges (`edge_class='call'`) and also the shared-key writers whose values `fn` reads (`edge_class='key'`). A `key` row does not call `fn` and may run on another thread. The reply also carries `callers_unresolved`, the number of call sites that named something `fn` could be but did not resolve to it, and a `callers_note` when that count is nonzero. The same reply includes `callees`, `threads`, `requirements`, and the verbatim body.

**What makes it wrong to read as a list of call sites:**

1. **Empty does not mean uncalled.** `callers` on `callers` itself returns `[]` with `callers_unresolved: 16`. The note says those 16 sites may be real callers the index could not pin down, such as member calls through a pointer or reference whose declared type doesn't fix the class. An empty list plus a nonzero unresolved count is "unknown," not "nothing calls this."

2. **Constructors are invisible.** `_empty_callers_note` (`clew/mcp_server/tools_query.py:632`) exists because a reporter read `dossier("ProgressBar")` as having two production callers when it had one, and four brace-initialised construction sites were never call edges. If a name resolves as both a function and a class, the empty list is a modelling gap. The note is only added when the index measured a refusal or the name is a constructor. A measured zero gets no note, which is intended.

3. **Dataflow rows are not callers.** A `key` row means "this function reads a value that this other function writes." Counting rows as call sites overstates the call graph and can point you at a function on another thread.

4. **`qualified` only narrows part of the list.** Passing `qualified` to pick one of several same-named functions filters `call` rows but not `key` rows, so the result can mix the chosen function's callers with unrelated writers.

5. **Edges are inferred, not read.** Function-pointer dispatch is recorded as a resolved edge (a test checks that `handle_cloud_command` appears via `event_bus_dispatch`), but the edge exists only where the pointer's binding resolved. Self-edges (`caller == callee`) are a mix of real recursion and extraction artefacts, which is why `_self_edge_callers` exists.

6. **Confidence varies by row.** `exact` and `resolved` are different claims. Before treating a caller as a real call site, check its `source` and `confidence`.

**How to read it:** treat the list as a lower bound on causal predecessors, not a census. Check `edge_class`, check `callers_unresolved`, and for a name that is also a type, search the name or read the body at the reported lines before concluding that nothing uses it. A quick `search` on the name catches the cases the index cannot resolve.