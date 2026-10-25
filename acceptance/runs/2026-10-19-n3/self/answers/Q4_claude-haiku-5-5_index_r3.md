For `_answering_with_refresh` (clew/mcp_server/server.py:519), the reply has one caller, `register_query_tools`, with `source: doxygen_sqlite` and `confidence: exact`. Its one resolved callee is `refused`, from `ast`. `before` (line 549) and `ToolError` (line 566) appear only under `external_callees`, with their call lines. `covering_tests` is empty and `liveness` is `live`.

So the answer is a set of edges, each tagged with where it came from and how sure clew is. It is not a list of every place the function runs. Reading it as one is wrong in these ways:

- **The caller is the registration site, not the invoker.** `register_query_tools` wraps the tool and hands it to the MCP SDK. At runtime the SDK calls the wrapper, and that dispatch doesn't appear as a call edge. The "caller" means "statically references and wires this up".
- **Parameters and callbacks are invisible as callees.** `before` is a parameter, so clew can't resolve it. It lands in `external_callees` rather than `callees`. An empty `callees` list therefore doesn't mean the function calls nothing.
- **Lists are capped and can be incomplete.** `max_neighbors` defaults to 8, and depth 1 is only immediate neighbours. Transitive paths need `depth` ≥ 2, which returns a bounded `chain`. Check the unresolved counts (`callers_unresolved`, `context_undecidable`) before trusting that a list is complete.
- **Provenance and confidence vary per row.** A row from `doxygen_sqlite` and one from `ast` are different kinds of evidence. `exact` and `resolved` are not the same grade.
- **Name-based resolution can collide.** An `ambiguous` block means several signatures share the name, and the neighbour rows are shared across them. Re-ask with `qualified` before attributing a caller to one overload.
- **Empty `covering_tests` is a measurement, not a verdict.** It means no linked test was found. It doesn't mean the function is untested, and it depends on requirement and test links being recorded.
- **Staleness can make it describe old code.** `anchor_mismatch: true` means the file changed since the build, so those line numbers are no longer this function.

I checked this on one symbol, so the behaviour of the other fields (`ambiguous`, the unresolved counts, `chain`) is taken from the tool's documented contract, not from a reply I inspected here.