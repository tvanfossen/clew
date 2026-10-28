**What the answer contains**

`callers(fn)` (surfaced through `dossier`'s `callers` field) returns a list of `CallEdge` rows, one per neighbouring function, not one per call site. Each row carries:

- `name` and `rowid`: the neighbouring function, resolved by name.
- `edge_class`: `'call'` for a direct call, or `'key'` for a shared-key dataflow edge.
- `source`: which extraction layer found it (`doxygen_sqlite`, `macro_hop`, `ast`, `ast_member`, `fnptr`, …).
- `confidence`: `exact`, `resolved`, or `fuzzy`, describing the strongest evidence for that endpoint. It is `None` on `'key'` rows.
- For `'key'` rows: `key_name`, `edge_kind`, `dispatch_mode`, `crosses_thread`, `strength`.
- `implementors`: on a virtual endpoint, the known overriders from doxygen's `reimplements` relation. This is an annotation, not a synthetic edge.
- `macro_hop` detail: the macro and its expansion, when a macro is what produces the hop.

Rows are sorted by name, then edge class, then key name.

**Why it is wrong to read it as a list of call sites**

1. **There is no call-site line.** `CallEdge` has no field for where in the caller the call is written. You get the other function's identity, not the line that calls `fn`. Getting to a site means reading the caller's body.

2. **`'key'` rows are not calls.** They are functions that write or read a shared key `fn` touches, with no call between them. They may run asynchronously on another thread. The `callers` docstring says a `'key'` neighbour "does NOT call `fn`", and `callees` has the mirror problem.

3. **`fuzzy` is included, not filtered.** The surface does not drop fuzzy edges. The descriptions tell a reader to weigh `confidence`, and `ast_member` edges are mostly fuzzy. The provenance notes say `ast_member` is the sole evidence for 77.7% of logical edges on the large C++ target, so dropping it would remove most of the graph.

4. **Same-name rows are shared.** If a name matches several signatures, every namesake's neighbour list carries the same rows. The `ambiguous` block reports this. The template's example is `size` on the public entropic index, where 331 caller rows are returned and 330 are shared with eight namesakes. Those rows are not attributable to one overload until you re-ask with `qualified`. Even then, the `'key'` half is not narrowed, because `_key_edge_rows` joins on `memberdef.name` (a known gap, gh#26-shaped).

5. **An empty list is not a measured zero.** Some calls through a pointer or reference receiver do not resolve unless the receiver's type is pinned. Brace-initialised constructions are not call edges at all. `callers_unresolved` records refused sites per symbol, and `_refusal_note` says so when it is positive. An unmeasured index reports `None`, not zero, and the code is careful not to treat that as clean.

6. **`callees` is not a complete call list.** Call sites that do not resolve to an indexed function are reported as `external_callees`, so `callees` can legitimately be empty while the body makes calls.

7. **Staleness.** `anchor_mismatch: true` means the file changed after the build, so the line ranges no longer belong to that function. Edges reflect the index's build, not the working tree.

**Practical reading**

Treat `callers` as "functions that causally precede `fn`, by name, with a confidence rating and a layer label". Check `edge_class` before anything else, then `confidence`, then the `ambiguous` and refusal notes. Before concluding nothing calls `fn`, read the body at the reported range or search the name.