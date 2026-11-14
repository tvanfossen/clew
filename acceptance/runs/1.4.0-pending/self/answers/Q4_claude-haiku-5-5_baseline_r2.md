**Short answer:** the answer is a list of *claimed* caller relationships, each labelled with the layer that produced it and how sure clew is. It is not a list of verified call sites, and an empty list does not mean nothing calls the function.

**Where the answer lives.** The standalone `callers` tool is gone. `dossier` (`clew/mcp_server/descriptions/dossier.json`, `clew/query/dossier.py:578`) returns `callers` and `callees` as fields alongside the body, brief, locks and requirements. The README says so explicitly.

**What each row contains**

- **One row per distinct caller identity**, not per call site. `_direct_call_edges` (`clew/query/symbols.py:389`) collapses duplicates that two layers both found.
- **`source`**, the extraction layer: `doxygen_sqlite`, `ast`, `ast_member`, `fnptr`, `declared_dispatch`, `macro_hop`, or `binding` (`clew/vocabulary.py:216`).
- **`confidence`**: `exact` (doxygen stated it), `resolved` (a unique name match or a join clew made itself), or `fuzzy` (several indexed functions share the name, so the edge fans out to all of them).
- **Annotations** such as `implementors` (overrides, from doxygen's `reimplements`) and macro-expansion markers.
- **A sibling field, `callers_unresolved`**, which counts refused inbound calls. It is `None` when the index predates the measurement. `unresolved_inbound_for_rowids` (`clew/query/symbols.py:348`) exists so that an empty `callers` can be read correctly.

**What makes it wrong to read as a list of call sites**

1. **Not all rows are observed calls.** `declared_dispatch` edges are synthetic: a repo owner's manifest says "this registrar connects to that handler" (`clew/dispatch_edges.py`). `fnptr` edges come from a pattern match on `GLOBAL = PARAM;` registration. Both are real information, but they are inferences or assertions, not call sites.

2. **Fuzzy rows are name matches.** A call to `size` with nine namesakes produces up to 331 caller rows, most shared with eight other functions. The `ambiguous` block (`clew/mcp_server/descriptions/_templates/ambiguous.json`) warns about this, and you should re-ask with `qualified` before attributing the rows to one function. Fuzzy rows are kept in `callers` on purpose: this repo has 21.3% fuzzy edges, and entropic has 79.8%. The `dominated_edges.py` pass only removes fan-out when a stronger layer already named a different function at that call site.

3. **Empty does not mean unused.** Several things make a real caller invisible:
   - Callers outside the indexed scope, or in an external nested repo.
   - Code behind an unsatisfied preprocessor guard. Its `gated_by` field and `gates_unplaceable` record this.
   - Macro-mediated calls where the macro's defining header is outside the index scope. `macro_hop` is then empty and nothing says so.
   - Calls the parser could not resolve at all. `callees` cannot hold these, which is why `external_callees` exists on the callee side. The `callers_unresolved` field is the caller-side counterpart.

4. **Virtual and indirect dispatch.** A caller of a base-class method may not show derived overrides except through the `implementors` annotation, and function-pointer calls are only found when the registration shape matches one of the recognised patterns. A container-held pointer registered by a method call is missed unless a dispatch manifest declares it.

5. **Staleness.** The answer reflects the last build. If a file has changed, `anchor_mismatch` on the body flags it, but nothing flags stale caller rows.

6. **Dataflow is separate.** Readers and writers of shared keys (`shared_key_edges`) are not in `callers`. They appear as `writes`/`reads`, and `include_dataflow` is deliberately off for dossier.

**How I checked this.** I answered from the source and the descriptions, not from a live query. The repository has no built index I ran against, so I did not verify the output on a real target.