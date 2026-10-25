**Short answer:** clew's answer is a graded, provenance-tagged set of name-resolved neighbours, with some adjacent facts attached. It is not a verified list of call sites, and reading it that way gives false confidence in both directions.

I answered from the source and docs (`clew/query/models.py`, `clew/call_edges.py`, `clew/query/externcalls.py`, `clew/dispatch_edges.py`, `docs/CORE_HYPOTHESIS.md`). I did not run clew against this repo.

**What a `dossier` reply contains.** The tool is `dossier(subject=NAME)`. Per the README and `CallEdge`, one reply carries:

- The symbol's body excerpt and brief.
- Both edge directions. Each entry is a `CallEdge` with `name`, `rowid`, `source` (which layer found it), `confidence`, and `edge_class`.
- Dataflow neighbours, which are `edge_class='key'` rows (see below).
- Locks held, the thread it runs on, requirements, and liveness.
- A list of callees the index holds no function for, recovered from the body (`ExternalCallee`).

**What makes it wrong to read as a list of call sites:**

1. **Not every neighbour is a call.** `edge_class='key'` means "writes a key that the neighbour reads, with no call between them." Those rows may be asynchronous and may land on another thread. Only `'call'` rows are synchronous calls on the caller's thread.

2. **`confidence` is about the name match, not the call.**
   - `exact` and `resolved` mean the call site was verified (for example, a unique bare identifier or a receiver type that checks out).
   - `fuzzy` means a function of that name exists and the specific one was never confirmed.
   - `ast_member` edges are mostly fuzzy. In one measured case, 1,762 such edges were stamped `resolved` and only 1 of 34 callers of `store` was real. They were demoted to `fuzzy` (`call_edges.py`, `_ast_record_call_edge`).
   - Reachability and thread BFS traverse only non-fuzzy edges, so a fuzzy caller can appear in `callers` without feeding liveness.

3. **One row per endpoint, strongest evidence only.** Each call is found by two doxygen layers, and the rows are collapsed. `source` and `confidence` describe the strongest evidence, so the reply does not show every way the edge was found.

4. **An empty or short list does not mean there are no calls.**
   - A call to an unindexed function (libc, pthread, a Python builtin) cannot be stored as an edge, because `callee_rowid` is `NOT NULL`. `callees` silently omits it. The separate `ExternalCallee` list recovers bare-identifier names only, capped at 24 names and 6 lines each, and excludes member calls.
   - Inbound calls that could not be resolved are counted, not named.
   - On Python and Rust, a newly added cross-file call is not picked up by incremental refresh and waits for a full rebuild.

5. **Virtual and function-pointer dispatch are partial.**
   - A callback caller appears only when registration-to-dispatch resolution succeeded.
   - `implementors` names the possible overrides of a virtual endpoint. It is an annotation, not an edge, and it does not say which one runs.

6. **Macro-written calls.** A call written as a macro invocation appears as an edge with no matching text in the caller's body. The `via_macro` field names the macro and its expansion. The expansion is doxygen's text, not an interpretation.

7. **Caps.** Neighbour lists are depth-capped, and the external-callee list is capped as above.

**How to read it:** treat `exact` and `resolved` non-fuzzy call edges as the reliable core. Treat `fuzzy` edges as candidate names to verify with a read of the caller. Treat `key` rows as a separate question about shared state. Treat an empty result as "not established," not "none." The README's own framing (`dossier` gives one reply, not a proof) supports this reading.