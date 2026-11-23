The answer is a dossier, not a bare list of call sites. I checked it on `_answering_with_refresh` (`clew/mcp_server/server.py:519`), a wrapper that adds a pre-query refresh to the MCP query tools.

**What the answer contains**

- **Identity and source:** signature, file and line range, version, the doxygen brief, and liveness (`live`).
- **Callers:** each one carries a `source` and a `confidence`. Here the single caller is `register_query_tools`, from `doxygen_sqlite` at `exact` confidence.
- **Callees:** indexed calls out of the body, with their own provenance. Here `refused` appears from `ast` at `resolved` confidence.
- **External callees:** calls to things the index does not know, with the line numbers where they occur. Here that is `before` (line 549) and `ToolError` (line 566).
- **Requirements, covering tests, threads, reads and writes:** each reported as its own field. Here `covering_tests` is empty and `writes`/`reads` are empty.
- **Body:** the verbatim source, with inline comments.
- **Counters:** `callers_unresolved` and `context_undecidable`, both 0 here.

**What would make it wrong to read it as a list of call sites**

1. **The callers are registration, not invocation.** `register_query_tools` wraps the tool once, at registration time. It does not call the wrapper per request. The SDK calls the wrapper later, and the index has no edge for that. Read as "who calls this," the answer misstates when and how often it runs.

2. **The wrapped function is not a callee.** The body calls `before(...)` and then runs `bound` through `anyio.to_thread.run_sync(functools.partial(bound, ...))`. The query being protected is `bound`, a parameter, so it does not appear in `callees` at all. `before` is listed only as an external call with no target. `run_sync` and `partial` are not listed either. I did not check why the parser dropped them, but the consequence is that the most important call in the function is missing from the call graph.

3. **Absence is not zero.** `callers_unresolved: 0` means the index resolved every caller edge it found. It does not prove there are no dynamic callers. A reader who sees an empty or short caller list should not conclude nothing calls the function.

4. **Confidence varies by edge.** `exact` from doxygen, `resolved` from AST, and external entries are different claims. Doxygen edges depend on the docs being present, and AST edges depend on the parser recovering the symbol.

5. **The call list says nothing about ordering or concurrency.** The body's own comments say the query runs in a worker thread so it does not block the event loop, and that refresh and query must key on the same `target` and `sub_index`. Those facts are in the body and the thread and lock layers, not in the caller list.

6. **Liveness is reachability in the index, not execution.** `live` says the index can reach the symbol. It does not say the code runs in production.

7. **Empty `covering_tests` means no recorded test link, not no test.** Tests reach a function through edges the index may not have.

The short version: treat the caller and callee lists as the index's resolved static edges, with their provenance, and check the body and the external-callee entries for dispatch that the edges cannot show.