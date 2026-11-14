The answer is a set of edges with provenance, not a list of call sites. I checked this on `_answering_with_refresh` (`clew/mcp_server/server.py:519-570`).

**What the reply contains**

- **Identity:** signature, file and line range, brief, `@version` (4), liveness, and the requirement it implements (REQ-DDB-MCP-004).
- **`callers`:** one row, `register_query_tools` in the same file, tagged `doxygen_sqlite` / `exact`. It gives the enclosing function's name and file, with no line number.
- **`callees`:** one row, `refused` in `freshness.py`, tagged `ast` / `resolved`.
- **`external_callees`:** names clew could not resolve to a definition, each with the line numbers where the call happens. Here that is `before` (line 549) and `ToolError` (line 566).
- **Counters:** `callers_unresolved: 0`, `context_undecidable: 0`. These say what the index failed to resolve. Zero is a measurement.
- **Body:** the verbatim source, with inline comments. Much of the behaviour is only here.

**What makes it wrong to read as a list of call sites**

1. **Caller rows are not sites.** You get the calling function, not the line it calls from. Only the unresolved callees carry `call_lines`.
2. **Indirect invocation is invisible.** The body calls `bound` through `functools.partial` inside `anyio.to_thread.run_sync`. That is not a direct call edge, so `bound` does not appear in `callees`. The real runtime caller is the MCP SDK, which invokes the returned `answering` wrapper through tool registration. No edge shows that. The one caller listed is the registration site.
3. **Empty or short does not mean unused.** Closures, decorators, function pointers, registration tables and SDK dispatch are all paths the caller list can miss. A one-row answer here reflects that the wrapper is applied at registration, not that the wrapper has one call site.
4. **Confidence differs by source.** `exact` from doxygen depends on documentation. `resolved` from the AST depends on the parser. An absent edge can mean "parser could not see it," and the `*_unresolved` counters are the only signal for that.
5. **The meaning sits in the body.** The `before` callee is the pre-answer refresh hook, which the name does not reveal. Reading the caller and callee lists alone would miss that the wrapper refreshes a stale index before answering, and that it keys the refresh on both `target` and `sub_index`.
6. **Snapshot.** The reply carries `staleness` only when the index is stale, and this one did not. The answer reflects the index at build time, not the working tree at the moment you read it.

Short version: `callers` and `callees` tell you which named functions are linked, with a provenance tag on each link. For where and how a call happens at runtime, use the body and the `external_callees` lines.