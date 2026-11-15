**Short answer:** the callers answer is a list of *functions that have an edge into the focal function*, each tagged with how that edge was found. It is not a list of call sites. Several things in it can make a reader wrong about how many calls exist, whether each one is real, and whether an empty list means anything. I read the source here and did not run clew against an index, so the rendered JSON shape is unverified.

**What one caller entry carries**

The stored `call_edges` row is `(caller_rowid, callee_rowid, source, confidence)` (`clew/call_edges.py:1-30`). Dossier builds one `CallEdge` per endpoint identity, not per call (`clew/query/symbols.py`, `_direct_call_edges`). Each entry has:

- `name`, `definition`, `rowid`, and whether it has a body.
- `source`: which layer found it. `doxygen_sqlite` is exact. `ast` is a bare-identifier callee. `ast_member` is a member, qualified or template callee reduced to its tail name. `fnptr` is a call through a registered function pointer. `binding` is a function handed to a framework as a keyword argument, not called. `macro_hop` comes from a call inside a macro expansion.
- `confidence`: `exact`, `resolved` or `fuzzy`. When several layers found the same edge, the strongest one wins.
- `implementors`, when doxygen's override relation names concrete overrides. This is an annotation, not extra edges.

**Ways to misread it as a call-site list**

| Reading | What is actually true |
|---|---|
| "N callers = N calls" | One entry per calling function. Five calls from one function is one caller. |
| "Each caller really calls this" | Fuzzy rows are not filtered on this surface. 21.3% of this repo's edges and 79.8% of the C++ corpus measured were fuzzy. An `ast_member` edge matches by unqualified tail, so `obj.close()` can attach to every `close`. |
| "Same name = same function" | Identity is keyed by bare name plus qualified name. A `name_ambiguity` block flags when one name matches several signatures, and the shared rows belong to all of them. |
| "Every entry is a direct call" | `fnptr` and `binding` edges are indirect or handed-off references. `macro_hop` edges sit inside a macro body. |
| "Empty `callers` means nothing calls it" | Refused inbound sites are counted separately (`callers_unresolved`, `clew/query/dossier.py:640`). A class name often shows `callers: []` because constructor edges are missing. An index older than the refusal measurement reports `None`, not zero. |
| "The graph is complete" | Coverage depends on the layers that ran. Doxygen gives the exact layer. The AST layers cover what tree-sitter parses. Calls through unknown pointers, runtime dispatch and non-indexed code are invisible. |
| "Transitive callers" | Dossier is depth 1 and keeps fuzzy rows. `chain_trace` and `traversal._call_hops` drop fuzzy edges and cap depth and fan-out (`clew/query/traversal.py:124-148`). The two can disagree about the same function. |
| "Self-edges are real" | The self-edge guard prunes fabricated ones at build time, so a missing self-edge can be deliberate. |

**Bottom line:** treat the answer as "these functions have an edge into this one, found by these layers, at this confidence, and here is what the build could not resolve." Use `confidence` and `source` to decide whether an edge is real. Use the refusal count before trusting an empty list. Don't count entries as call sites.