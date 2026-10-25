**What the answer contains.** For `_build_function_indexes` (`clew/call_edges.py:277`), `dossier` returned:

- **`callers`**: 10 entries, each a function name plus `source` (`ast` or `doxygen_sqlite`), `confidence` (`resolved` or `exact`), and `edge_class` (`call`). Caller entries carry no line numbers.
- **`callees`**: resolved callees only. Here it was empty, because the one call it makes, to `_FuncRanges`, did not resolve to an indexed function. That call went to `external_callees` with `call_lines: [308]`. Line numbers appear only in that unresolved list.
- **Gap counters**: `callers_unresolved`, `context_undecidable`, `gates_unplaceable`. These say how many edges the index could not place. Zero here, but they are the place to look when a list seems short.
- **Context around the call graph**: verbatim body, file and line span, `liveness`, `threads`, `requirements`, `covering_tests`, `writes`/`reads`, `overrides`/`overridden_by`, and the doc comment.

**What makes it wrong to read as a list of call sites:**

1. **Caller rows are enclosing functions, not sites.** A caller row says "this function contains a call to the target", not where or how many times. Attribution depends on picking the enclosing function by body range. The docstring I got back says that a declaration in one file and a definition in another can make the wrong function win, and it reports a live case of this. Treat a caller row as a claim to verify against the body.
2. **Two provenances merged into one list.** `doxygen_sqlite`/`exact` and `ast`/`resolved` are different evidence with different strength, and the flat list does not weight them. Each row's `source` and `confidence` must be read.
3. **`edge_class` is not always `call`.** The field exists so that non-call edges, such as callback registrations, can appear in the same list. Filter on it before counting "callers".
4. **Empty does not mean unused.** `dossier` returned no callers, and its own note says the name also resolves to a class, so this is probably a constructor. Brace-initialised construction is not modelled as a call edge. Virtual dispatch is a separate relation (`overridden_by`), not a caller.
5. **Same-name collisions.** If a bare name matches several functions, neighbour rows are shared across them. Use `candidates`/`qualified` before attributing any row to one overload.
6. **Staleness.** Both replies came back with `anchor_mismatch: true`, meaning the file changed since the index was built. Line numbers and body text may not match the current file, and the caller and callee sets reflect the build, not the working tree.

**Short version:** the answer is a set of function-level edges with provenance, confidence, and unresolved counts, plus the surrounding context. It is not a complete, located list of call sites. Use it to find which functions to read, then confirm the sites in the source. Check `source`, `edge_class`, the unresolved counters, and `anchor_mismatch` before trusting an absence.