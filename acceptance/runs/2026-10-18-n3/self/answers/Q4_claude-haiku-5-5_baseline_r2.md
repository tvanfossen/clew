**What the answer contains**

`clew` answers "who calls X" from `call_edges`, a table of `(caller, callee, source, confidence)` rows, one per distinct endpoint identity (`clew/query/symbols.py`, around line 392). Each row is a function-to-function edge, not a call site:

- **`source`** records which layer found it. The values are `doxygen_sqlite` (inline xrefs), `ast` (bare-identifier call), `ast_member` (member/qualified callee unwrapped to its tail name), `fnptr` (registration then dispatch through a function pointer), `macro_hop`, `declared_dispatch` (synthesized from a `.clew.yaml` declaration) and `binding`. See `clew/call_edges.py`, lines 1–30.
- **`confidence`** is `exact`, `resolved` or `fuzzy`. `fuzzy` means the name matched without confirming the class.
- **Dossier extras** (`clew/query/dossier.py`): body excerpt, brief, locks, thread, requirements and covering tests, liveness, and `callers_unresolved`, a count of inbound edges that were refused. `name_ambiguity` adds a warning when a common name has fuzzy member neighbours.

**What makes it wrong to read as a list of call sites**

1. **Rows are inferences, not observed call sites.** `fnptr` edges come from registration-plus-dispatch matching. `macro_hop` edges are composed from two observations. `declared_dispatch` edges are author-stated. `doxygen_sqlite` inline xrefs are described in the code as "the closest proxy for a call edge", so a reference can land there too.

2. **Fuzzy edges are not filtered in the flat list.** `symbols.py` says so explicitly: 21.3% of clew's own edges and 79.8% of entropic's C++ edges are fuzzy, and the flat `callers` list keeps them. A fuzzy `ast_member` caller may be calling a different class's method with the same name. Meanwhile `traversal.py` and `reachability.py` drop fuzzy edges, so the same graph gives different answers on different surfaces.

3. **An empty `callers` does not mean nothing calls it.** The `callers_unresolved` count exists for this. It is `None` (not 0) on an index built before the measurement existed, so a missing value is not a clean bill of health.

4. **Self-edges can be deleted or kept by shape.** The self-edge guard keeps a `caller == callee` row only when the caller's body contains a bare or self-rooted call to that name. It fails closed, so an unparseable caller keeps its edges.

5. **"Live" is not "called".** `symbol_liveness` is a BFS from seeds that include name-shape guesses (`%init%`, `%handler%`, `%task%`) and every function with zero non-fuzzy callers. A function with no callers is marked live by construction.

6. **Coverage has known holes.** Calls through function pointers with no visible registration are missed. Cross-file calls newly added in Python or Rust wait for a full rebuild. Callers outside the indexed repo are not visible, except through the terminus layer. Dossier batches are capped at 8 symbols, and the MCP boundary caps rows by response size (`RESPONSE_BUDGET_BYTES`). The row cap is lossy, so a long caller list can be silently shortened.

7. **Freshness.** Queries refresh a stale index first, and the `staleness` block appears only when the index is actually stale. A refresh that fails or is skipped would leave edges describing old code.

**Practical reading:** treat the callers list as a ranked set of candidates. Check `confidence`, `source` and `callers_unresolved` before trusting a negative, and open the body at each caller before claiming a call site.

I read the README, the docs and the query and edge-building code. I did not run clew against a target, so the behaviour above is what the code and docstrings say, not measured output.