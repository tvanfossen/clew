The answer is a list of edges, not a list of call sites, and it can also be empty for reasons that have nothing to do with absence. I checked this against the index for this repo, using `callers` (`clew/query/symbols.py:756`) and `_empty_callers_note` (`clew/mcp_server/tools_query.py:632`) as examples.

**What is in the answer**

Each row is a `CallEdge` with these fields:

- **`edge_class`**: `'call'` means a direct caller. `'key'` means a function that writes a shared key the target reads. A `'key'` row does not call the target and may run on another thread. The docstring says to check this on every row.
- **`confidence`**: `exact` means the edge was resolved to a specific function. `resolved` means the AST pass resolved it. Both are edges the index can stand behind.
- **`source`**: `doxygen_sqlite` or `ast`, which shows which extractor produced the edge.
- **`file`** and the line span, for reading the caller.
- **`qualified`**: an optional argument that selects one of several same-named functions. It filters `'call'` rows but not `'key'` rows.

So the answer mixes causal predecessors of two kinds: callers and shared-data writers. It is an ordering and dataflow answer, not a complete census of invocations.

**What makes it wrong to read as a list of call sites**

1. **Empty does not mean uncalled.** `callers` itself returns `[]` in this index, but its reply carries `callers_unresolved: 16`. That means 16 call sites named a function this could be and did not resolve to one. The reply says so in `callers_note`. An empty list is a measurement only when that count is zero.
2. **Constructors are invisible to call edges.** The `_empty_callers_note` docstring records a real case. `ProgressBar` showed no callers, but its construction sites were brace-initialised, not calls. A reporter counted the class as having two callers when it had one. The note exists because "how many callers" decides whether a shared primitive is safe to change.
3. **Name ambiguity.** `callers` also resolves as a variable in `tests/test_wire.py`. Without `kind`, or without re-asking with `qualified`, the rows may be shared across candidates. The `ambiguous` block exists for this.
4. **Pointer and reference receivers.** A member call through a pointer or reference resolves only when the receiver's declared type pins the class. Otherwise the edge is missing, and the index does not flag that per call.
5. **Dispatch depends on what the extractor sees.** Function-pointer dispatch is recorded as a resolved edge; there is a test for `handle_cloud_command` through `event_bus_dispatch`. Anything that reaches the target through an unresolved path does not appear.
6. **Indexing runs the repo's code.** Doxygen and the build are part of the pipeline, so the edge set reflects the index's build state. A stale index can be missing edges, which is why `staleness` is reported on replies.

**How to use it**

Read `edge_class` and `confidence` on each row. Treat zero rows as "no recorded callers" and check `callers_unresolved` and `callers_note` before concluding nothing calls the function. For a constructor or a shared primitive, `search` the name or read the body at the reported lines before deciding the blast radius.