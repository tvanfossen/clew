The answer is a set of graph edges with provenance and confidence attached, plus a few signals about what the index could not see. It is not a verified list of call sites.

**What a `callers` entry carries** (`clew/query/models.py` `CallEdge`, `clew/query/symbols.py` `_direct_call_edges`)

- **Endpoint identity**, one per distinct function identity rather than per name. Doxygen splits one function across declaration and definition rows, and the code merges them.
- **`source`**: which layer found the edge. The vocabulary is `doxygen_sqlite` (doxygen xrefs), `ast` (bare-identifier call found by tree-sitter), `ast_member` (member or qualified call unwrapped to its tail name), `fnptr` (call through a registered function pointer), `macro_hop`, `declared_dispatch`, and `binding`.
- **`confidence`**: `exact`, `resolved` (unique name match) or `fuzzy` (several candidates share the name, so the class was never confirmed).
- **`implementors`**: an annotation on an existing edge, listing concrete overrides when doxygen records them. It is not a new edge.
- **`edge_class`**: `call` or `key`. Shared-key dataflow edges share the same type. Check the class before reading an entry as a call.

**What the dossier adds around it**

- `unresolved_inbound`: a count of callers that exist but did not resolve to a symbol. It is `None` when the table is absent, which means "unmeasured", not zero.
- `candidates`: the namesakes, populated only when the name is an overload or shares its name with other functions.
- `overrides` and `overridden_by`: virtual-dispatch relations. Callers that reach the function through a base pointer appear here, not in `callers`.
- `locks_held`, `threads`, `termini`, `external_callees`, `liveness`, `staleness`.

**What makes it wrong to read `callers` as a list of call sites**

1. **Fuzzy edges are included.** The code does not filter them for `callers`. Its own comment says 21.3% of this repo's call edges are fuzzy and 79.8% of entropic's (C++). Many C++ member-call edges are fuzzy by construction. A fuzzy caller may be a different function with the same name. `chain_trace` filters fuzzy edges; the flat neighbour list does not.
2. **Empty does not mean nobody calls it.** Callers can exist and fail resolution. That is what `unresolved_inbound` is for. The gh#15 incident was a reader who followed the only resolved caller, a test helper, and drew the wrong conclusion.
3. **It is one hop and static.** `callers` lists direct edges. Transitive reach needs a separate walk, and that walk filters fuzzy edges. A listed caller can also be dead code or a test. Liveness is a separate reachability answer.
4. **Coverage has known holes.**
   - Function-pointer calls resolve only for the registration-then-dispatch pattern (`GLOBAL = PARAM;` then `GLOBAL(...)`).
   - On Python and Rust, a newly added cross-file call waits for a full rebuild.
   - The self-edge guard deletes self-edges that lack a bare or self-rooted call shape, so some real recursion may not appear.
   - Calls through virtual dispatch and macros are only partly represented.
5. **Staleness.** Queries auto-refresh when sources have moved, but a refresh that cannot splice (the cross-file limit above) leaves the answer stale until a full rebuild.
6. **Key edges are not calls.** A `key` entry means a shared-key write/read with no call. It may be asynchronous and cross a thread boundary.

**Bottom line:** read each caller with its `source` and `confidence`, treat an empty list as "unknown until `unresolved_inbound` is checked", and treat the list as one-hop, static, and possibly fuzzy. I read the code for this answer and did not run clew against this repository.