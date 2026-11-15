The answer is a list of **caller functions**, not call sites. Each row names the calling function's file and symbol. The dossier gives no line number for the call and no argument text.

I checked this with `dossier` on `_callers_of` in `clew/dispatch_edges.py`. Its `callers` field is a single row, `_interface_edges`, and each row carries only a name and file. The per-edge metadata sits beside the rows as `edge_defaults` (here `source: doxygen_sqlite`, `confidence: exact`, `edge_class: call`). The function's body and the `_callers_of` docstring show how the edges are built:

- **Each row is a deduplicated caller-callee pair.** `call_edges` holds one row per extraction layer, so one caller can appear several times. The index keeps the strongest confidence. A row therefore means "an edge exists, at this confidence", not "this call happens at this line".
- **Confidence is a property of the edge, not the call.** A synthetic edge built on a fuzzy premise carries that weakness. The docstring names this case: a conclusion drawn from a low-confidence premise must not be reported as resolved.
- **Virtual and function-pointer calls are split.** Static layers stop at the interface method. Dispatch-edge stages extend the chain, so a caller reached through an interface may show up only through a synthetic edge, which is weaker than a direct one.

Reading an empty list as "nothing calls this" is wrong. The reply itself flags several cases:

- **Unresolved callers** are counted separately (`callers_unresolved`). A list can be short because callers failed to resolve, not because there are none.
- **Constructors** are a known gap. Brace-initialised construction is not modelled as a call edge. The reply says so when a name also resolves to a class. `QueryTools.dossier` returned `callers: []`, which in this index means "not linked", not "unused", since it is an MCP entry point.
- **Dataflow is mixed in at other depths.** The `callers` brief in `clew/query/symbols.py` says the answer is "callers plus the writers it reads from". At depth 1 the `callers` field is call-only. At depth 2 and above, `chain` walks both call edges and shared-key (dataflow) edges.
- **Lists are capped.** `max_neighbors` defaults to 8, and a cut list reports `_limited` with `total_available`. Ignoring that gives an incomplete list that looks complete.
- **Staleness.** `anchor_mismatch: true` means the lines have changed since indexing, so the body and its row positions may not match the working tree.

So a caller list is a set of resolved, deduplicated caller-to-callee edges with their confidence and gaps. To know whether a given call site exists, read the source at the caller, or use `dossier` on the caller and check its body.