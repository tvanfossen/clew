The answer is a list of **caller functions**, not call sites. I checked this against one real reply, `dossier` on `_ast_parse_one_file` (`clew/harvest.py`, depth 1). It returned 12 callers, each with `name`, `source`, `confidence` and `edge_class`. Nothing in a caller row gives a line number, a call count or the expression used at the call.

**What the answer contains**

- **Caller and callee names**, with the file and line span of the target itself.
- **Provenance per edge.** Some edges came from `ast` (tree-sitter) with `confidence: resolved`. Others came from `doxygen_sqlite` with `confidence: exact`. The two sources are different evidence and don't carry the same weight.
- **`edge_class`.** Every edge here was `call`, but the tool also describes `shared-key` edges. A caller row is not guaranteed to mean a direct call.
- **Test functions mixed in with production code.** Two of the 12 callers are tests, so the list does not separate "what ships" from "what checks it".
- **Unresolved counts.** `callers_unresolved: 0` is a useful signal that nothing was left dangling. It does not say the list is complete.

**What would make it wrong to read as a list of call sites**

1. **Stale anchor.** The reply had `anchor_mismatch: true`, so the file has changed since the index was built. The body and line span may not match the current source, and the caller set may describe an older version.
2. **No call-site detail.** You know that `_harvest_file` calls it, not on which line, how many times, or under which condition.
3. **Indirect calls may be missing.** Calls through function pointers, callback tables or dynamic dispatch only appear if the parser resolves them. An empty or short caller list does not prove there are no indirect callers.
4. **Cap ambiguity.** `max_neighbors` was 8, but 12 callers came back and the reply carried no `truncated` marker for them. I can't tell from this reply whether the list is complete, so I wouldn't treat it as exhaustive.
5. **Depth 1 is direct callers only.** Transitive reach needs `depth` 2–6, which adds a `chain`.
6. **Name collisions.** A same-named function elsewhere could be conflated. The `ambiguous` block and `qualified` parameter exist for this, and this reply did not trigger it.
7. **`live` is not reachability.** `liveness: live` describes the function's status in the index, not whether any entry point reaches it.

**How to use it**

Treat the caller list as a starting set of places to read. Check the anchor and refresh the index if it is stale, confirm each `doxygen_sqlite` versus `ast` disagreement by reading the source, and separate test callers from production callers before drawing conclusions about impact.