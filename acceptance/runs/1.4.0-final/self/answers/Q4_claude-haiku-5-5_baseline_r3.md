Clew's answer is a resolved call graph, one edge per caller-callee pair, each tagged with how it was found and how sure clew is. It is not a list of every line that invokes the function. I read the code for this (`clew/query/symbols.py`, `clew/query/models.py`, `clew/call_edges.py`, `clew/vocabulary.py`, `clew/query/dossier.py`) but did not run clew against this repo, so the behaviour below is from the source.

**What each neighbour carries**

- `name`, `rowid`: the resolved function on the other end.
- `source`: which layer found it. The values are `doxygen_sqlite`, `ast`, `ast_member`, `fnptr`, `declared_dispatch`, `binding` and `macro_hop`.
- `confidence`: `exact`, `resolved` or `fuzzy`. Doxygen edges are `exact`. Unique-name AST matches are `resolved`. Ambiguous names are `fuzzy`.
- `implementors`: for a virtual endpoint, the bodies doxygen says reimplement it. This is an annotation, not an edge.
- `macro_hop` expansion: when the call is written as a macro, the expansion is shown verbatim.

**What makes it wrong to read as call sites**

1. **Edges are per pair, not per site.** Two calls from `f` to `g` on different lines give one edge. The reply names no line of the call. Line numbers belong to the function's own extent, not to the call.
2. **Fuzzy and `ast_member` edges are name matches.** `ast_member` unwraps a qualified or member callee to its tail name, so `x.close()` can attach to several unrelated `close` functions. Filter on `confidence` before trusting an edge.
3. **Dispatch and pointer edges are inferred.** `declared_dispatch`, `fnptr` and `binding` edges mean "this can reach that body", not "this runs". The reply names implementors without claiming which one executes.
4. **An empty `callers` is not proof of no callers.** Calls that fail resolution are counted in `unresolved_inbound`. `null` means that count was never measured, and it must not be read as zero.
5. **Self-edges are deleted unless the body shows a self-directed call.** Otherwise a fabricated self-loop could show up as a caller. Unparseable callers are left alone and reported as unverifiable.
6. **Dataflow is not a call.** `key` edges, where a function writes a value another reads with no call between them, are kept out of the dossier's `callers`. Where they appear, `edge_class='key'` marks them. Same-named functions can merge in that layer.
7. **Stale index.** `anchor_mismatch: true` means the file changed after the build and the recorded lines may be wrong.
8. **Outside the index.** Calls into libc or vendored code appear only as `external_callees` on the callee side, and calls from code that was never indexed do not appear at all.

**How to use it**

Treat `callers` as a navigation aid: the set of plausible callers, labelled by how strong each link is. Before concluding anything about a call site, check the edge's `confidence` and `source`, check `unresolved_inbound`, and grep or read the caller's body (the dossier includes it verbatim) to confirm the call is really there.