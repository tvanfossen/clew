In this build, the answer is not a list of call sites. Each row is a caller **function** with provenance attached, and several things can make it misleading if read as "these lines call this."

I read the source here, not a live index. The `callers`/`callees` tools were folded into `dossier` (`clew/mcp_server/descriptions/_templates/ambiguous.json`), but the underlying `callers()` query still exists in `clew/query/symbols.py`.

**What a row contains** (`CallEdge`, `clew/query/models.py`, and `_direct_call_edges` in `symbols.py`)

| Field | Meaning |
|---|---|
| `name`, `rowid` | The caller function, identified by rowid, not by name |
| `source` | Which extraction layer found it: doxygen xref, macro hop, AST, AST member, fnptr, declared dispatch, or binding |
| `confidence` | `exact` / `resolved` / `fuzzy`. This is how precisely the callee was resolved, not how likely the call is real |
| `edge_class` | `call` (synchronous, same thread) or `key` (a shared-state writer, not a caller) |
| `implementors` | Concrete overrides, annotated onto a virtual-method edge |
| `via_macro`, `via_macro_expansion` | The macro the call goes through, if any |

**What makes it wrong to read as call sites**

1. **One row per caller function, not per call site.** `_endpoint_identities` collapses duplicates. A function that calls `fn` five times appears once, with no line numbers.
2. **`key` rows are not callers.** `callers()` appends shared-key writers whose values `fn` reads. Those may run asynchronously on another thread. The docstring says to check `edge_class` on every row.
3. **Name collisions.** Without `qualified`, the focal side is resolved by identity (gh#26), but the `key` half is still unioned by bare name, and this gap is documented in `_call_edges`. The `ambiguous` block warns that neighbour rows may be shared across same-named functions.
4. **`exact` does not mean right.** The gh#26 case in the code: three same-named `_classify` functions produced rows reading `confidence: exact`, one of them a fabricated self-edge, because every layer resolved by name.
5. **Fuzzy edges are kept.** `callers` deliberately does not filter `fuzzy`. The code cites 21.3% of clew's own call edges and 79.8% on a large C++ target (entropic) as fuzzy. `chain_trace` filters them because it expands each hop.
6. **Empty is not "nobody calls it."** `_direct_call_edges` returns `[]` when the `call_edges` table is absent or the identity does not resolve. That is the same answer as "no callers," which is the "absence is not emptiness" trap the project's own AGENTS.md warns about.
7. **Coverage is partial by design.** Calls from non-function contexts, and calls through unresolved names, do not appear as callers. Only the indexed-function graph is shown, with `external_callees` covering the unresolved callee side.
8. **Virtual dispatch.** A call to a base virtual method lists the base as the callee. Concrete targets appear only as `implementors` annotations on that edge.
9. **Staleness.** Rows reflect the last build. `dossier` sets `anchor_mismatch: true` when the file has changed since, and the line data is then wrong.

**How to read it:** treat `callers` as a candidate list of functions that may reach `fn`, filtered by `edge_class` and `confidence`, and verify the actual call site in source before relying on it. I did not run clew here: no clew tool is loaded in this session, so the above is from reading the code.