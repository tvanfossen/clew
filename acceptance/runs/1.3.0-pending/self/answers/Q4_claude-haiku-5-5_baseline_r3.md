**What the answer contains**

A `callers` entry is a function-to-function edge, not a call site. The record is `call_edges(caller_rowid, callee_rowid, source, confidence)` (`clew/call_edges.py`). Each neighbour carries:

- **`name`, `rowid`**: the other function.
- **`source`**: which layer produced it. The values are `doxygen_sqlite`, `ast`, `ast_member`, `fnptr`, `macro_hop`, `declared_dispatch` and `binding`.
- **`confidence`**: `exact` (doxygen cross-reference), `resolved` (one name match) or `fuzzy` (several candidates share the name).
- **`edge_class`**: `call` or `key`. A `key` row is a shared-key dataflow edge with no call between the two functions, and it may run on another thread (`clew/query/models.py`, `CallEdge`).
- **`implementors`, `macro`**: for a virtual endpoint, the known overrides are attached as an annotation. For a macro-written call, the macro and its expansion are attached.
- **`callers_unresolved`** (in `dossier`): how many call sites named this function and did not resolve. `0` is a measured "none were refused". `None` means the index is too old to say.

There are no line numbers in the edge table.

**What makes it wrong to read as a list of call sites**

1. **Namesake fan-out.** The AST layers resolve by name. When several functions share a name, one call fans out to all of them as `fuzzy`. The repo's own `_table_exists` is defined in four modules, so an unqualified name can list callers that could never see the function. `clew/dominated_edges.py` deletes fan-out rows only when a stronger layer already named a different callee. Unanchored fuzzy rows survive.

2. **A unique name is not evidence about the receiver.** `resolved` means the name matched once. For `x.f()` in C++ or Python, the receiver's type may be unknown. `clew/critical_sections.py` states this rule explicitly.

3. **Empty does not mean no callers.** Unresolved sites are counted in `callers_unresolved`, but only where that field exists. Other unresolved calls are simply absent from the list.

4. **Not every neighbour is a call.** `key` rows are dataflow, not calls. `fnptr` rows come from registration patterns of one shape. `macro_hop` rows exist where no call text appears in the caller body. `declared_dispatch` rows are multi-candidate on purpose, so they are the answer rather than a guess.

5. **Virtual dispatch is annotated, not resolved.** A base-class call keeps its own confidence even when the real target is a derived override. The override appears only in `implementors`.

6. **Staleness and coverage.** Cross-file calls added to Python or Rust are not picked up by incremental refresh and wait for a full rebuild. Code outside the indexed set, ignored paths and generated code that was never present are all invisible.

**How to read it**

Treat `callers` as a graded candidate set. Check `source` and `confidence`, read `callers_unresolved`, and confirm the important edges against the source body. Use it to decide where to look, not as a complete census of call sites.

I did not build an index or run clew here. These points come from reading the code and its documentation. I did not verify them by querying a real index.